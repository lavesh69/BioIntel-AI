from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest

from biointel.science_pulse import api as pulse_api
from biointel.science_pulse.models import PulseRecord
from biointel.science_pulse.news_ui import ACTION_LABELS, NEWS_CATEGORIES, NEWS_VIEWS
from biointel.science_pulse.service import CONTEXTUAL_ACTIONS, SciencePulseService
from biointel.science_pulse.store import SciencePulseStore
from biointel.science_pulse.ui import PRIMARY_NAVIGATION


ROOT = Path(__file__).resolve().parents[1]
TENANT = "local"
USER = "news-reader"


@pytest.fixture
def pulse(tmp_path: Path) -> SciencePulseService:
    store = SciencePulseStore(tmp_path)
    service = SciencePulseService(tmp_path, store=store)
    now = datetime.now(timezone.utc).isoformat()
    records = [
        PulseRecord(
            "rss_nature_biotechnology",
            "india-biotech",
            "India biotechnology team reports a new CRISPR platform",
            "https://example.org/india-biotech",
            content_type="news",
            source_name="Nature Biotechnology",
            original_source="Nature Biotechnology",
            abstract="Researchers in India reported a biotechnology platform for CRISPR delivery.",
            published_at=now,
            categories=["Biotechnology", "Genetics & Genomics"],
            genes=["CAS9"],
            technologies=["CRISPR"],
            provenance={"region": "India", "related_publication": "doi:10.1000/linked"},
            quality=0.92,
            live_state="LIVE",
        ),
        PulseRecord(
            "rss_sciencedaily_biology",
            "biology-global",
            "Global cell biology atlas released",
            "https://example.org/cell-atlas",
            content_type="news",
            source_name="ScienceDaily Biology",
            abstract="A global cell biology atlas was released with open metadata.",
            published_at=now,
            categories=["Biology", "Cell Biology"],
            provenance={"region": "Global"},
            quality=0.8,
            live_state="CACHED",
        ),
        PulseRecord(
            "demo_fixture",
            "demo-news",
            "Demo biology headline",
            "https://example.org/demo",
            content_type="news",
            source_name="Demo source",
            published_at=now,
            categories=["Biology"],
            provenance={"region": "Global"},
            live_state="DEMO",
        ),
        PulseRecord(
            "pubmed",
            "publication-one",
            "Peer reviewed oncology publication",
            "https://example.org/publication",
            content_type="publication",
            source_name="PubMed",
            published_at=now,
            categories=["Cancer Research"],
            doi="10.1000/publication",
            live_state="LIVE",
        ),
        PulseRecord(
            "biorxiv",
            "preprint-one",
            "Unreviewed biology preprint",
            "https://example.org/preprint",
            content_type="preprint",
            source_name="bioRxiv",
            published_at=now,
            categories=["Biology"],
            live_state="LIVE",
        ),
    ]
    for record in records:
        store.upsert_item(record, TENANT)
    store.upsert_item(
        PulseRecord(
            "rss_nibib_news",
            "same-story-second-source",
            "India biotechnology team reports a new CRISPR platform",
            "https://example.org/second-coverage",
            content_type="news",
            source_name="NIBIB",
            abstract="An institutional report about the India biotechnology CRISPR platform.",
            published_at=now,
            categories=["Biotechnology"],
            provenance={"region": "India"},
            live_state="LIVE",
        ),
        TENANT,
    )
    return service


def _news_id(pulse: SciencePulseService) -> str:
    return str(
        pulse.news_feed(
            tenant_id=TENANT, user_id=USER, query="India biotechnology", limit=10
        )["items"][0]["item_id"]
    )


def test_exact_information_architecture_and_central_category_matrix() -> None:
    assert PRIMARY_NAVIGATION == (
        "Overview", "Live Science News", "Publications", "Preprints",
        "Datasets & Protocols", "Trials & Regulatory", "Grants & Funding",
        "Patents & Translation", "Conferences & Events", "Databases & Tool Updates",
        "Canvas Studio", "Trends & Intelligence", "Saved Library", "Alerts", "Sources & Operations",
    )
    assert len(NEWS_CATEGORIES) == 33
    assert NEWS_CATEGORIES[0] == "All Science News"
    assert {"Biology", "Biotechnology", "Biomedical", "Bioinformatics", "India Science", "Global Science"} <= set(NEWS_CATEGORIES)
    assert NEWS_VIEWS == (
        "Featured", "Latest", "Breaking", "For You", "Trending",
        "Story Clusters", "Compact Headlines", "Timeline",
    )
    forbidden = {"Shiro AI", "Classroom", "Academy", "Connect", "BioIntel Studio", "Education Home"}
    assert forbidden.isdisjoint(PRIMARY_NAVIGATION)


def test_real_news_filters_pagination_and_demo_separation(pulse: SciencePulseService) -> None:
    all_news = pulse.news_feed(tenant_id=TENANT, user_id=USER, limit=1, offset=0)
    assert all_news["total"] == 2
    assert len(all_news["items"]) == 1
    second_page = pulse.news_feed(tenant_id=TENANT, user_id=USER, limit=1, offset=1)
    assert len(second_page["items"]) == 1
    assert second_page["items"][0]["item_id"] != all_news["items"][0]["item_id"]
    assert pulse.news_feed(tenant_id=TENANT, user_id=USER, category="Biotechnology")["total"] == 1
    assert pulse.news_feed(tenant_id=TENANT, user_id=USER, category="Biology")["total"] == 1
    assert pulse.news_feed(tenant_id=TENANT, user_id=USER, region="India")["total"] == 1
    assert pulse.news_feed(tenant_id=TENANT, user_id=USER, region="Global")["total"] == 2
    assert pulse.news_feed(tenant_id=TENANT, user_id=USER, live_only=True)["total"] == 1
    assert all(item["live_state"] != "DEMO" for item in all_news["items"] + second_page["items"])


def test_read_save_story_cluster_and_truthful_evidence_state(pulse: SciencePulseService) -> None:
    item_id = _news_id(pulse)
    clusters = pulse.news_feed(
        tenant_id=TENANT, user_id=USER, minimum_source_count=2, sort="trending"
    )
    assert clusters["total"] == 1
    assert clusters["items"][0]["source_count"] == 2
    backed = pulse.news_feed(tenant_id=TENANT, user_id=USER, research_backed=True)
    assert backed["total"] == 1
    detail = pulse.news_detail(item_id, user_id=USER, tenant_id=TENANT)
    assert detail["research_backed"] is True
    assert detail["evidence_state"] == "Evidence Relationship Uncertain"
    assert pulse.news_feed(tenant_id=TENANT, user_id=USER, unread_only=True)["total"] == 1
    assert pulse.store.toggle_bookmark(USER, item_id, tenant_id=TENANT) is True
    saved = pulse.news_feed(tenant_id=TENANT, user_id=USER, saved_only=True)
    assert saved["total"] == 1 and saved["items"][0]["is_saved"] is True
    unlinked_id = str(pulse.news_feed(tenant_id=TENANT, user_id=USER, category="Biology")["items"][0]["item_id"])
    unlinked = pulse.news_detail(unlinked_id, user_id=USER, tenant_id=TENANT, mark_read=False)
    assert unlinked["research_backed"] is False
    assert unlinked["evidence_state"] == "No Primary Research Linked"


def test_every_contextual_more_action_persists(pulse: SciencePulseService) -> None:
    item_id = _news_id(pulse)
    assert set(ACTION_LABELS) == set(CONTEXTUAL_ACTIONS)
    for action_key in CONTEXTUAL_ACTIONS:
        result = pulse.perform_contextual_action(
            item_id, user_id=USER, action_key=action_key, tenant_id=TENANT
        )
        assert result["state"] == "approval_required"
    with pulse.store.connect() as connection:
        count = int(connection.execute(
            "SELECT COUNT(*) FROM sp_integrations WHERE tenant_id=? AND user_id=?",
            (TENANT, USER),
        ).fetchone()[0])
    assert count == len(CONTEXTUAL_ACTIONS)
    assert pulse.follow_item(item_id, user_id=USER, kind="source", tenant_id=TENANT)["status"] == "followed"
    assert pulse.follow_item(item_id, user_id=USER, kind="topic", tenant_id=TENANT)["status"] == "followed"
    assert pulse.create_item_alert(item_id, user_id=USER, tenant_id=TENANT)["status"] == "created"


def test_news_fastapi_contract(pulse: SciencePulseService, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pulse_api, "_SERVICE", pulse)
    app = FastAPI()
    app.include_router(pulse_api.router)
    client = TestClient(app)
    response = client.get("/api/v1/science-pulse/news", params={"category": "Biotechnology"})
    assert response.status_code == 200 and response.json()["total"] == 1
    item_id = response.json()["items"][0]["item_id"]
    detail = client.get(f"/api/v1/science-pulse/news/{item_id}")
    assert detail.status_code == 200 and detail.json()["read_at"]
    action = client.post(
        f"/api/v1/science-pulse/news/{item_id}/action",
        json={"action_key": "connect_share"},
    )
    assert action.status_code == 201 and action.json()["destination"] == "connect"
    invalid = client.post(
        f"/api/v1/science-pulse/news/{item_id}/action",
        json={"action_key": "not-real"},
    )
    assert invalid.status_code == 422


def test_news_ui_has_required_actions_and_no_page_network_calls() -> None:
    news_source = (ROOT / "src/biointel/science_pulse/news_ui.py").read_text(encoding="utf-8")
    ui_source = (ROOT / "src/biointel/science_pulse/ui.py").read_text(encoding="utf-8")
    education_source = (ROOT / "src/biointel/education/ui.py").read_text(encoding="utf-8")
    for label in ("Read Full Story", "Save", "Share", "More", "Original Source", "AI-Generated Summary"):
        assert label in news_source
    assert "service.test_connection" not in news_source + ui_source
    assert "Queue safe refresh" in news_source
    pulse_block = education_source.split("def render_pulse", 1)[1].split("def render_academy", 1)[0]
    assert "render_workspace_context" not in pulse_block
    assert "render_role_snapshot" not in pulse_block


def test_packaged_science_pulse_page_boots_without_streamlit_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BIOINTEL_USER_DATA_DIR", str(tmp_path / "user-data"))
    page = ROOT / "pages" / "341_BioIntel_Science_Pulse.py"
    rendered = AppTest.from_file(str(page), default_timeout=60).run(timeout=60)
    assert not rendered.exception
