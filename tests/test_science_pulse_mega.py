from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest

from biointel.science_pulse import api as pulse_api
from biointel.science_pulse.models import MIGRATION_VERSION, PulseRecord
from biointel.science_pulse.providers import (
    ADAPTERS,
    BUILTIN_SOURCES,
    FeedAdapter,
    FetchResult,
    ProviderRegistry,
)
from biointel.science_pulse.scheduler import SciencePulseScheduler
from biointel.science_pulse.security import (
    HttpPayload,
    PulseSecurityError,
    SafeHttpClient,
    clean_text,
    safe_xml,
    validate_remote_url,
)
from biointel.science_pulse.service import SciencePulseService
from biointel.science_pulse.store import SciencePulseStore
from biointel.science_pulse.taxonomy import TOPIC_RULES, classify


ROOT = Path(__file__).resolve().parents[1]


def public_resolver(host, port, **kwargs):
    return [(2, 1, 6, "", ("93.184.216.34", port))]


def fixture_transport(url: str, headers: dict[str, str], timeout: float) -> HttpPayload:
    if "esearch.fcgi" in url:
        payload = {"esearchresult": {"idlist": ["123"]}}
    elif "esummary.fcgi" in url:
        payload = {
            "result": {
                "123": {
                    "title": "PubMed CRISPR study",
                    "authors": [{"name": "Ada Scientist"}],
                    "articleids": [{"idtype": "doi", "value": "10.1000/pubmed"}],
                    "pubdate": "2026 Jul 01",
                    "fulljournalname": "Journal of Fixtures",
                }
            }
        }
    elif "europepmc" in url:
        payload = {
            "resultList": {
                "result": [
                    {
                        "id": "EPMC1",
                        "pmid": "44",
                        "doi": "10.1000/epmc",
                        "title": "Europe PMC biology",
                        "authorString": "A. One, B. Two",
                        "firstPublicationDate": "2026-07-01",
                    }
                ]
            },
            "nextCursorMark": "next-epmc",
        }
    elif "api.crossref.org" in url:
        payload = {
            "message": {
                "items": [
                    {
                        "DOI": "10.1000/crossref",
                        "title": ["Crossref biology"],
                        "abstract": "<p>Evidence</p>",
                        "author": [{"given": "A", "family": "One"}],
                        "URL": "https://doi.org/10.1000/crossref",
                        "published": {"date-parts": [[2026, 7, 1]]},
                        "container-title": ["Fixture Journal"],
                        "subject": ["Biology"],
                    }
                ],
                "next-cursor": "next-crossref",
            }
        }
    elif "api.openalex.org" in url:
        payload = {
            "results": [
                {
                    "id": "https://openalex.org/W1",
                    "doi": "https://doi.org/10.1000/openalex",
                    "display_name": "OpenAlex genomics",
                    "abstract_inverted_index": {"Genome": [0], "study": [1]},
                    "primary_location": {
                        "landing_page_url": "https://openalex.org/W1",
                        "source": {"display_name": "Open Journal"},
                    },
                    "authorships": [{"author": {"display_name": "Open Author"}}],
                    "publication_date": "2026-07-01",
                    "topics": [{"display_name": "Genomics"}],
                }
            ],
            "meta": {"next_cursor": "next-openalex"},
        }
    elif "api.biorxiv.org" in url:
        payload = {
            "collection": [
                {
                    "doi": "10.1101/fixture",
                    "title": "Preprint biotechnology",
                    "abstract": "Biotechnology evidence",
                    "authors": "One A; Two B",
                    "date": "2026-07-01",
                    "category": "bioinformatics",
                    "version": "1",
                }
            ],
            "messages": [{"total": 1}],
        }
    elif "clinicaltrials.gov" in url:
        payload = {
            "studies": [
                {
                    "protocolSection": {
                        "identificationModule": {
                            "nctId": "NCT0001",
                            "briefTitle": "Clinical gene therapy",
                        },
                        "descriptionModule": {"briefSummary": "Trial summary"},
                        "conditionsModule": {"conditions": ["Cancer"]},
                        "armsInterventionsModule": {
                            "interventions": [{"name": "Gene therapy"}]
                        },
                        "statusModule": {
                            "studyFirstPostDateStruct": {"date": "2026-07-01"}
                        },
                    }
                }
            ],
            "nextPageToken": "trial-next",
        }
    elif "api.datacite.org" in url:
        payload = {
            "data": [
                {
                    "id": "10.1000/data",
                    "attributes": {
                        "doi": "10.1000/data",
                        "titles": [{"title": "Biology dataset"}],
                        "descriptions": [{"description": "Dataset abstract"}],
                        "url": "https://example.org/data",
                        "publisher": "Fixture Repository",
                        "creators": [{"name": "Data Author"}],
                        "published": "2026-07-01",
                        "subjects": [{"subject": "Biology"}],
                    },
                }
            ]
        }
    elif "api.eventdata.crossref.org" in url:
        payload = {
            "message": {
                "events": [
                    {
                        "id": "event-1",
                        "subj": {
                            "title": "Crossref scholarly event",
                            "url": "https://example.org/event",
                        },
                        "occurred-at": "2026-07-01",
                        "relation-type-id": "references",
                    }
                ],
                "next-cursor": "event-next",
            }
        }
    elif "export.arxiv.org" in url:
        data = b"""<?xml version="1.0"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
          <entry><id>https://arxiv.org/abs/1</id><title>arXiv biology</title>
          <summary>Preprint evidence</summary><published>2026-07-01T00:00:00Z</published>
          <author><name>Arxiv Author</name></author>
          <link rel="alternate" href="https://arxiv.org/abs/1"/><category term="q-bio"/></entry>
        </feed>"""
        return HttpPayload(data, url, "application/atom+xml", 200)
    else:
        raise AssertionError(f"Unexpected fixture URL: {url}")
    return HttpPayload(json.dumps(payload).encode(), url, "application/json", 200)


@pytest.fixture
def client():
    return SafeHttpClient(
        resolver=public_resolver, transport=fixture_transport, timeout=1
    )


@pytest.fixture
def store(tmp_path):
    return SciencePulseStore(tmp_path, db_path=tmp_path / "pulse.sqlite")


@pytest.fixture
def service(store):
    return SciencePulseService(tmp_path := store.root, store=store)


def test_01_pubmed_adapter(client):
    result = ADAPTERS["pubmed"].fetch(client, "crispr", 5)
    assert result.records[0].pmid == "123"
    assert result.records[0].doi == "10.1000/pubmed"


def test_02_europe_pmc_adapter(client):
    result = ADAPTERS["europe_pmc"].fetch(client, "biology", 5)
    assert result.records[0].provider_key == "europe_pmc"
    assert result.checkpoint == "next-epmc"


def test_03_crossref_adapter(client):
    result = ADAPTERS["crossref"].fetch(client, "biology", 5)
    assert result.records[0].title == "Crossref biology"
    assert result.checkpoint == "next-crossref"


def test_04_openalex_adapter(client):
    result = ADAPTERS["openalex"].fetch(client, "genomics", 5)
    assert result.records[0].abstract == "Genome study"
    assert result.checkpoint == "next-openalex"


def test_05_biorxiv_adapter(client):
    result = ADAPTERS["biorxiv"].fetch(client, "", 5)
    assert result.records[0].content_type == "preprint"
    assert result.records[0].provider_key == "biorxiv"


def test_06_medrxiv_adapter(client):
    result = ADAPTERS["medrxiv"].fetch(client, "", 5)
    assert result.records[0].provider_key == "medrxiv"


def test_07_arxiv_adapter(client):
    result = ADAPTERS["arxiv"].fetch(client, "biology", 5)
    assert result.records[0].title == "arXiv biology"
    assert result.records[0].canonical_url.startswith("https://")


def test_08_clinicaltrials_adapter(client):
    result = ADAPTERS["clinicaltrials"].fetch(client, "gene therapy", 5)
    assert result.records[0].external_id == "NCT0001"
    assert result.records[0].content_type == "clinical_trial"


def test_09_datacite_adapter(client):
    result = ADAPTERS["datacite"].fetch(client, "biology", 5)
    assert result.records[0].doi == "10.1000/data"
    assert result.records[0].content_type == "dataset"


def test_10_crossref_event_data_adapter(client):
    result = ADAPTERS["crossref_event_data"].fetch(client, "biology", 5)
    assert result.records[0].content_type == "event"
    assert result.checkpoint == "event-next"


def _feed_client(data: bytes, mime: str = "application/rss+xml"):
    return SafeHttpClient(
        resolver=public_resolver,
        transport=lambda url, headers, timeout: HttpPayload(data, url, mime, 200),
    )


def test_11_rss_parsing():
    data = b"""<rss><channel><item><guid>n1</guid><title>Biology news</title>
    <description><![CDATA[<p>Evidence only</p>]]></description>
    <link>https://example.org/news</link><pubDate>2026-07-01</pubDate></item></channel></rss>"""
    result = FeedAdapter("https://example.org/feed.xml", "Fixture News").fetch(
        _feed_client(data), "", 10
    )
    assert result.records[0].title == "Biology news"
    assert "<p>" not in result.records[0].abstract


def test_12_atom_parsing():
    data = b"""<feed xmlns="http://www.w3.org/2005/Atom"><entry>
    <id>a1</id><title>Atom biology</title><summary>Summary</summary>
    <link href="https://example.org/a1"/><updated>2026-07-01</updated></entry></feed>"""
    result = FeedAdapter("https://example.org/feed.atom", "Atom Fixture").fetch(
        _feed_client(data, "application/atom+xml"), "", 10
    )
    assert result.records[0].title == "Atom biology"


def test_13_malicious_feed_rejected():
    with pytest.raises(PulseSecurityError, match="DTD"):
        safe_xml(b'<!DOCTYPE rss [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><rss/>')


def test_14_ssrf_localhost_rejected():
    with pytest.raises(PulseSecurityError):
        validate_remote_url("https://127.0.0.1/feed")


def test_15_ssrf_dns_rebinding_rejected():
    resolver = lambda *args, **kwargs: [(2, 1, 6, "", ("10.0.0.5", 443))]
    with pytest.raises(PulseSecurityError):
        validate_remote_url("https://example.org/feed", resolver=resolver)


def test_16_mime_validation():
    bad = SafeHttpClient(
        resolver=public_resolver,
        transport=lambda url, headers, timeout: HttpPayload(
            b"<html/>", url, "text/html", 200
        ),
    )
    with pytest.raises(PulseSecurityError, match="MIME"):
        bad.get("https://example.org/feed")


def test_17_response_size_limit():
    bad = SafeHttpClient(
        resolver=public_resolver,
        max_bytes=1024,
        transport=lambda url, headers, timeout: HttpPayload(
            b"x" * 1025, url, "application/json", 200
        ),
    )
    with pytest.raises(PulseSecurityError, match="size"):
        bad.get("https://example.org/feed")


def test_18_html_sanitization():
    assert clean_text("<script>alert(1)</script><p>Safe &amp; useful</p>") == "Safe & useful"


def test_19_pagination_checkpoint(client):
    result = ADAPTERS["crossref"].fetch(client, "biology", 1, "cursor-before")
    assert result.checkpoint == "next-crossref"


class FixtureRegistry:
    def __init__(self):
        self.calls = 0

    def fetch(self, source, *, query="", limit=50):
        self.calls += 1
        return FetchResult(
            [
                classify(
                    PulseRecord(
                        provider_key=str(source["source_key"]),
                        external_id=f"id-{self.calls}",
                        doi="10.1000/incremental",
                        title="Incremental genomics record",
                        canonical_url="https://example.org/item",
                        published_at=datetime.now(timezone.utc).date().isoformat(),
                        provenance={"fixture": True},
                    )
                )
            ],
            checkpoint=f"cursor-{self.calls}",
        )


def fixture_service(store):
    return SciencePulseService(store.root, store=store, providers=FixtureRegistry())


def test_20_incremental_sync(store):
    pulse = fixture_service(store)
    result = pulse.sync_source("pubmed", idempotency_key="incremental-1")
    assert result["inserted"] == 1
    assert next(s for s in pulse.source_status() if s["source_key"] == "pubmed")[
        "checkpoint"
    ] == "cursor-1"


def test_21_checkpoint_recovery(store):
    pulse = fixture_service(store)
    pulse.sync_source("pubmed", idempotency_key="checkpoint-1")
    pulse.sync_source("pubmed", idempotency_key="checkpoint-2")
    assert next(s for s in pulse.source_status() if s["source_key"] == "pubmed")[
        "checkpoint"
    ] == "cursor-2"


def test_22_duplicate_publication_by_doi(store):
    first, operation1 = store.upsert_item(
        PulseRecord("a", "1", "Shared paper", "https://example.org/1", doi="10.1/x")
    )
    second, operation2 = store.upsert_item(
        PulseRecord("b", "2", "Shared paper elsewhere", "https://example.org/2", doi="10.1/x")
    )
    assert first == second
    assert (operation1, operation2) == ("inserted", "updated")


def test_23_duplicate_news_by_normalized_title(store):
    first, _ = store.upsert_item(
        PulseRecord("rss_a", "1", "Major Biology News!", "https://example.org/1", content_type="news")
    )
    second, _ = store.upsert_item(
        PulseRecord("rss_b", "2", "Major Biology News", "https://example.org/2", content_type="news")
    )
    assert first == second


def test_24_story_cluster_preserves_all_sources(store):
    first, _ = store.upsert_item(
        PulseRecord("rss_a", "1", "Shared story", "https://example.org/1", content_type="news")
    )
    store.upsert_item(
        PulseRecord("rss_b", "2", "Shared story", "https://example.org/2", content_type="news")
    )
    assert len(store.get_item(first)["sources"]) == 2


def test_25_scheduler_offline_cache_mode(store, monkeypatch):
    monkeypatch.setenv("BIOINTEL_RUNTIME_SMOKE_TEST", "1")
    scheduler = SciencePulseScheduler(store.root, service=fixture_service(store), worker_id="one")
    assert scheduler.tick(force=True)["status"] == "offline_cache_only"
    scheduler.shutdown()


def test_26_hourly_schedule_registry():
    nature = next(source for source in BUILTIN_SOURCES if source.key == "rss_nature_biotechnology")
    assert nature.schedule_seconds == 3600
    assert nature.high_priority


def test_27_daily_retraction_schedule_registry():
    events = next(source for source in BUILTIN_SOURCES if source.key == "crossref_event_data")
    assert events.schedule_seconds == 86_400


def test_28_restart_recovery(store):
    pulse = fixture_service(store)
    run = store.begin_sync("pubmed", trigger="scheduled", idempotency_key="stale")
    with store.connect() as connection:
        connection.execute(
            "UPDATE sp_sync_runs SET started_at='2000-01-01T00:00:00+00:00' WHERE run_id=?",
            (run,),
        )
    scheduler = SciencePulseScheduler(store.root, service=pulse, worker_id="restart")
    assert scheduler.recover_stale_runs() == 0
    with store.connect() as connection:
        assert connection.execute(
            "SELECT status FROM sp_sync_runs WHERE run_id=?", (run,)
        ).fetchone()[0] == "recovered_after_restart"


def test_29_duplicate_job_prevention(store):
    fixture_service(store)
    first = store.begin_sync("pubmed", trigger="scheduled", idempotency_key="same")
    second = store.begin_sync("pubmed", trigger="scheduled", idempotency_key="same")
    assert first and second is None


def test_30_rate_limit_spacing(client):
    waits = []
    registry = ProviderRegistry(client, sleeper=waits.append)
    source = {
        "source_key": "crossref",
        "kind": "api",
        "checkpoint": "",
    }
    registry.fetch(source, query="biology", limit=1)
    registry.fetch(source, query="biology", limit=1)
    assert waits and waits[-1] <= 0.2


def test_31_provider_timeout_retries():
    calls = []

    def fail(url, headers, timeout):
        calls.append(url)
        raise TimeoutError("fixture timeout")

    registry = ProviderRegistry(
        SafeHttpClient(resolver=public_resolver, transport=fail), sleeper=lambda _: None
    )
    with pytest.raises(RuntimeError, match="3 attempts"):
        registry.fetch({"source_key": "crossref", "kind": "api", "checkpoint": ""})
    assert len(calls) == 3


def test_32_circuit_breaker(store):
    fixture_service(store)
    for index in range(4):
        run = store.begin_sync(
            "pubmed", trigger="scheduled", idempotency_key=f"failure-{index}"
        )
        store.finish_sync(
            run,
            source_key="pubmed",
            status="failed",
            duration_ms=1,
            error="fixture failure",
        )
    source = next(value for value in store.list_sources() if value["source_key"] == "pubmed")
    assert source["status"] == "CIRCUIT_OPEN"
    assert source["circuit_open_until"]


def _item(store, tenant="local", title="CRISPR fixture"):
    return store.upsert_item(
        classify(
            PulseRecord(
                "fixture",
                f"id-{tenant}-{title}",
                title,
                "https://example.org/item",
                abstract="CRISPR evidence",
                published_at=datetime.now(timezone.utc).date().isoformat(),
            )
        ),
        tenant,
    )[0]


def test_33_confirmed_notification_delivery(store):
    pulse = fixture_service(store)
    item_id = _item(store)
    store.create_alert("u", name="a", query="CRISPR", channels=["in_app"])
    assert pulse.evaluate_alerts(item_id)["delivered"] == 1
    assert store.notifications("u")[0]["delivery_state"] == "delivered"


def test_34_unconfigured_channel_not_delivered(store):
    pulse = fixture_service(store)
    item_id = _item(store)
    store.create_alert("u", name="a", query="CRISPR", channels=["email"])
    pulse.evaluate_alerts(item_id)
    assert store.notifications("u")[0]["delivery_state"] == "configuration_required"


def test_35_quiet_hours_suppress_delivery(store):
    pulse = fixture_service(store)
    item_id = _item(store)
    store.save_preferences(
        "u", {"quiet_start": "00:00", "quiet_end": "00:00", "timezone": "UTC"}
    )
    store.create_alert("u", name="a", query="CRISPR", channels=["in_app"])
    assert pulse.evaluate_alerts(item_id)["suppressed"] == 1


def test_36_invalid_timezone_falls_back_safely(store):
    pulse = fixture_service(store)
    store.save_preferences(
        "u", {"quiet_start": "00:00", "quiet_end": "00:00", "timezone": "Invalid/Zone"}
    )
    assert pulse._quiet("u", "local")


def test_37_digest_generation(store):
    pulse = fixture_service(store)
    _item(store)
    result = pulse.generate_digest("u", frequency="daily")
    assert result["status"] == "ready"
    assert "Original" not in result["body"]
    assert "Link:" in result["body"]


def test_38_retraction_update_preserves_history(store):
    pulse = fixture_service(store)
    item_id = _item(store)
    store.toggle_bookmark("u", item_id)
    pulse.integration_draft(
        item_id, user_id="u", destination="research", action="cite"
    )
    result = pulse.update_trust(item_id, "retracted", verified=True)
    assert result["history_preserved"]
    assert result["notifications"] == 1
    assert store.get_item(item_id)["trust_state"] == "retracted"


def test_39_offline_cached_search(store):
    item_id = _item(store)
    reopened = SciencePulseStore(store.root, db_path=store.path)
    assert reopened.search_items("CRISPR")[0]["item_id"] == item_id


def test_40_search_and_structured_filters(store):
    _item(store, title="Cancer genomics publication")
    rows = store.search_items("Cancer", content_type="publication", category="Genomics")
    assert len(rows) == 1


def test_41_tenant_isolation(store):
    _item(store, tenant="tenant-a")
    _item(store, tenant="tenant-b")
    assert len(store.search_items(tenant_id="tenant-a")) == 1
    assert len(store.search_items(tenant_id="local")) == 0


def test_42_role_permission_denies_non_admin():
    request = SimpleNamespace(
        state=SimpleNamespace(
            api_identity=SimpleNamespace(client_id="reader", role="reader"),
            tenant=SimpleNamespace(tenant_id="local"),
        )
    )
    with pytest.raises(Exception) as error:
        pulse_api._admin(request)
    assert getattr(error.value, "status_code", None) == 403


def test_43_shiro_context_is_evidence_bounded(store):
    pulse = fixture_service(store)
    item_id = _item(store)
    context = pulse.shiro_context([item_id], level="school")
    assert context["full_text_available"] is False
    assert "metadata/excerpts" in context["instruction"]


@pytest.mark.parametrize(
    "destination", ["classroom", "academy", "studio", "research", "shiro"]
)
def test_44_integration_drafts_require_approval(store, destination):
    pulse = fixture_service(store)
    item_id = _item(store, title=f"{destination} source")
    result = pulse.integration_draft(
        item_id, user_id="teacher", destination=destination, action="create draft"
    )
    assert result["state"] == "approval_required"
    assert result["payload"]["human_approval_required"] is True


def test_45_connect_notification_confirms_database_write(store, monkeypatch):
    monkeypatch.setenv("BIOINTEL_USER_DATA_DIR", str(store.root / "userdata"))
    pulse = fixture_service(store)
    item_id = _item(store)
    store.create_alert("u", name="a", query="CRISPR", channels=["connect"])
    result = pulse.evaluate_alerts(item_id)
    assert result["delivered"] == 1
    assert store.notifications("u")[0]["delivery_reference"].startswith("msg_")


def test_46_windows_worker_is_silent_and_integrated():
    background = (ROOT / "src" / "biointel" / "step101" / "background.py").read_text(
        encoding="utf-8"
    )
    worker = (ROOT / "scripts" / "background_job_worker.py").read_text(encoding="utf-8")
    supervisor = (ROOT / "scripts" / "runtime_supervisor_step206.py").read_text(
        encoding="utf-8"
    )
    assert "CREATE_NO_WINDOW" in background
    assert "DETACHED_PROCESS" in background
    assert "SciencePulseScheduler" in worker
    assert "BIOINTEL_RUNTIME_SMOKE_TEST" in supervisor


def test_47_streamlit_local_database_smoke(tmp_path, monkeypatch):
    monkeypatch.setenv("BIOINTEL_USER_DATA_DIR", str(tmp_path / "userdata"))
    script = f"""
from biointel.science_pulse.ui import render_science_pulse
render_science_pulse(r'{str(ROOT)}', user_id='smoke', tenant_id='local')
"""
    rendered = AppTest.from_string(script, default_timeout=30).run(timeout=30)
    assert not rendered.exception


def test_48_database_migration_is_idempotent(store):
    second = SciencePulseStore(store.root, db_path=store.path)
    with second.connect() as connection:
        rows = connection.execute(
            "SELECT version FROM sp_schema_migrations WHERE version=?", (MIGRATION_VERSION,)
        ).fetchall()
    assert len(rows) == 1


def test_49_source_provenance_and_live_demo_separation(store):
    live = _item(store)
    demo_record = PulseRecord(
        "demo_fixture",
        "demo-1",
        "Demo biology",
        "https://example.org/demo",
        live_state="DEMO",
        provenance={"fixture": "demo"},
    )
    demo, _ = store.upsert_item(demo_record)
    assert store.get_item(live)["live_state"] != "DEMO"
    assert store.get_item(demo)["provenance"]["fixture"] == "demo"


def test_50_api_health_and_tenant_scoped_items(store, monkeypatch):
    pulse = fixture_service(store)
    _item(store)
    monkeypatch.setattr(pulse_api, "_SERVICE", pulse)
    app = FastAPI()
    app.include_router(pulse_api.router)
    response = TestClient(app).get("/api/v1/science-pulse/health")
    assert response.status_code == 200
    assert response.json()["migration_version"] == MIGRATION_VERSION


def test_51_taxonomy_covers_required_science_domains():
    required = {
        "General Biology",
        "Molecular Biology",
        "Genetics",
        "Genomics",
        "Bioinformatics",
        "Biotechnology",
        "Microbiology",
        "Virology",
        "Immunology",
        "Neuroscience",
        "Cancer Biology",
        "Scientific Policy",
        "Research Funding",
        "Scientific Conferences",
    }
    assert required.issubset(TOPIC_RULES)


def test_52_builtin_registry_has_real_adapters_or_secure_feed():
    for source in BUILTIN_SOURCES:
        assert source.base_url.startswith("https://")
        assert source.key in ADAPTERS or source.kind == "rss"


def test_53_legacy_facade_writes_canonical_store(tmp_path, monkeypatch):
    monkeypatch.setenv("BIOINTEL_USER_DATA_DIR", str(tmp_path / "userdata"))
    from biointel.education.science_pulse_service import SciencePulseService as Legacy

    legacy = Legacy(str(tmp_path))
    article_id = legacy.add_article(
        {"article_id": "legacy-1", "title": "Legacy migration fixture", "source": "PubMed"}
    )
    assert article_id == "legacy-1"
    assert legacy.list_articles()[0]["article_id"] == "legacy-1"
    with legacy._service.store.connect() as connection:
        tables = {
            row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        }
    assert "sp_items" in tables
