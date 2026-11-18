from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from urllib.error import URLError
from urllib.request import Request

import pytest

from biointel.science_pulse.providers import BUILTIN_SOURCES, FeedAdapter
from biointel.science_pulse.security import (
    HttpPayload,
    PulseSecurityError,
    SafeHttpClient,
    _LimitedRedirectHandler,
)


ROOT = Path(__file__).resolve().parents[1]


def public_resolver(host, port, **kwargs):
    return [(2, 1, 6, "", ("93.184.216.34", port))]


RSS_RDF = b"""<?xml version="1.0" encoding="UTF-8"?>
<rdf:RDF
    xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
    xmlns="http://purl.org/rss/1.0/"
    xmlns:dc="http://purl.org/dc/elements/1.1/">
  <item rdf:about="https://news.example/article-2">
    <title><a>Nested biomedical headline</a></title>
    <link>https://news.example/article-2</link>
    <dc:identifier>news-2</dc:identifier>
    <dc:creator>NIH Reporter</dc:creator>
    <dc:date>2026-07-30</dc:date>
    <description>Live biomedical evidence.</description>
  </item>
  <item rdf:about="https://news.example/article-1">
    <title>Earlier headline</title>
    <link>https://news.example/article-1</link>
    <dc:identifier>news-1</dc:identifier>
  </item>
</rdf:RDF>
"""


def test_rss_rdf_namespaces_nested_titles_and_source_identity_are_preserved():
    client = SafeHttpClient(
        resolver=public_resolver,
        transport=lambda *_: HttpPayload(
            RSS_RDF,
            "https://news.example/feed",
            "application/rss+xml",
            200,
        ),
    )
    adapter = FeedAdapter(
        "https://news.example/feed",
        "Official Biomedical News",
        "rss_official_biomedical",
    )

    result = adapter.fetch(client, "", 10)

    assert [record.external_id for record in result.records] == ["news-2", "news-1"]
    assert result.records[0].title == "Nested biomedical headline"
    assert result.records[0].authors == ["NIH Reporter"]
    assert result.records[0].provider_key == "rss_official_biomedical"
    assert result.records[0].source_name == "Official Biomedical News"
    assert result.records[0].original_source == "Official Biomedical News"
    assert result.records[0].provenance["format"] == "rss"
    assert result.records[0].provenance["network_route"] == "injected_test_transport"
    assert result.checkpoint == "news-2"


def test_feed_checkpoint_stops_before_already_processed_items():
    client = SafeHttpClient(
        resolver=public_resolver,
        transport=lambda *_: HttpPayload(
            RSS_RDF,
            "https://news.example/feed",
            "application/rss+xml",
            200,
        ),
    )
    result = FeedAdapter(
        "https://news.example/feed",
        "Official Biomedical News",
        "rss_official_biomedical",
    ).fetch(client, "", 10, checkpoint="news-2")

    assert result.records == []
    assert result.checkpoint == "news-2"


class _FakeHeaders:
    @staticmethod
    def get_content_type() -> str:
        return "application/rss+xml"


class _FakeResponse:
    status = 200
    headers = _FakeHeaders()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    @staticmethod
    def read(_limit):
        return b"<rss/>"

    @staticmethod
    def geturl():
        return "https://news.example/feed"


def test_auto_proxy_failure_retries_direct_with_a_fresh_request(monkeypatch):
    client = SafeHttpClient(resolver=public_resolver, proxy_mode="auto")
    requests: list[Request] = []
    direct_flags: list[bool] = []

    def fake_open(request, _context, _approved_hosts, *, direct):
        requests.append(request)
        direct_flags.append(direct)
        if len(requests) == 1:
            request.set_proxy("127.0.0.1:9", "http")
            raise URLError("broken proxy")
        return _FakeResponse()

    monkeypatch.setattr(client, "_open", fake_open)
    payload = client.get(
        "https://news.example/feed",
        approved_hosts={"news.example"},
        accept="application/rss+xml",
    )

    assert direct_flags == [False, True]
    assert requests[0] is not requests[1]
    assert requests[1].host == "news.example"
    assert payload.network_route == "direct_fallback"


def test_redirect_target_is_validated_before_following():
    handler = _LimitedRedirectHandler(
        approved_hosts=None,
        resolver=public_resolver,
    )
    with pytest.raises(PulseSecurityError, match="Local or internal"):
        handler.redirect_request(
            SimpleNamespace(),
            None,
            302,
            "Found",
            {},
            "https://localhost/private",
        )


def test_validated_official_live_news_sources_are_registered():
    sources = {source.key: source for source in BUILTIN_SOURCES}

    assert sources["rss_nature_biotechnology"].base_url.startswith("https://")
    assert sources["rss_sciencedaily_biology"].base_url.startswith("https://")
    assert sources["rss_nibib_news"].ownership == "U.S. NIH/NIBIB"
    assert sources["rss_nlm_news"].ownership == "U.S. National Library of Medicine"


def test_streamlit_ui_queues_background_verification_without_network_call():
    ui_source = (ROOT / "src/biointel/science_pulse/ui.py").read_text(
        encoding="utf-8"
    )

    assert "Queue live verification" in ui_source
    assert "service.test_connection" not in ui_source
