from __future__ import annotations

import json

import pytest

from biointel.education.phase15_runtime.providers import fetch_provider


class Response:
    def __init__(self, payload: bytes):
        self.payload = payload
        self.status = 200
        self.headers = {"Content-Type": "application/json"}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, _limit=-1):
        return self.payload


def opener_for(payloads):
    queue = list(payloads)
    def opener(request, timeout=15):  # noqa: ANN001
        assert timeout == 15
        return Response(queue.pop(0))
    return opener


def test_crossref_parser_and_cursor():
    payload = json.dumps({"message": {"next-cursor": "next", "items": [{"DOI": "10.1/x", "title": ["Title"], "author": [{"given": "A", "family": "B"}], "URL": "https://doi.org/10.1/x", "type": "journal-article"}]}}).encode()
    rows, cursor = fetch_provider("crossref", "biology", opener=opener_for([payload]))
    assert cursor == "next" and rows[0]["doi"] == "10.1/x" and rows[0]["authors"] == ["A B"]


def test_europe_pmc_parser():
    payload = json.dumps({"nextCursorMark": "c2", "resultList": {"result": [{"id": "PMC1", "pmid": "1", "doi": "10.2/y", "title": "Study", "authorString": "A, B", "source": "MED", "firstPublicationDate": "2026-01-01"}]}}).encode()
    rows, cursor = fetch_provider("europe_pmc", "biology", opener=opener_for([payload]))
    assert cursor == "c2" and rows[0]["pmid"] == "1" and len(rows[0]["authors"]) == 2


def test_openalex_parser():
    payload = json.dumps({"meta": {"next_cursor": "c3"}, "results": [{"id": "https://openalex.org/W1", "doi": "https://doi.org/10.3/z", "title": "Open Study", "publication_date": "2026-02-01", "type": "article", "authorships": [{"author": {"display_name": "Researcher"}}], "cited_by_count": 4, "open_access": {"is_oa": True}}]}).encode()
    rows, cursor = fetch_provider("openalex", "biology", opener=opener_for([payload]))
    assert cursor == "c3" and rows[0]["external_id"] == "W1" and rows[0]["doi"] == "10.3/z"


def test_arxiv_parser():
    xml = b'''<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><entry><id>https://arxiv.org/abs/2601.00001</id><updated>2026-01-02T00:00:00Z</updated><published>2026-01-01T00:00:00Z</published><title>Genome model</title><summary>Evidence text.</summary><author><name>Ada</name></author></entry></feed>'''
    rows, cursor = fetch_provider("arxiv", "genome", cursor="0", opener=opener_for([xml]))
    assert cursor == "1" and rows[0]["external_id"] == "2601.00001" and rows[0]["record_type"] == "preprint"


def test_pubmed_two_stage_parser():
    search = json.dumps({"esearchresult": {"idlist": ["123"]}}).encode()
    summary = json.dumps({"result": {"123": {"title": "PubMed study", "pubdate": "2026", "authors": [{"name": "Ada"}], "articleids": [{"idtype": "doi", "value": "10.4/p"}]}}}).encode()
    rows, cursor = fetch_provider("pubmed", "genome", cursor="0", opener=opener_for([search, summary]))
    assert cursor == "1" and rows[0]["pmid"] == "123" and rows[0]["doi"] == "10.4/p"


def test_provider_validation():
    with pytest.raises(ValueError):
        fetch_provider("unknown", "x", opener=opener_for([]))


def test_biorxiv_and_medrxiv_fixture_parser():
    payload = json.dumps({
        "collection": [
            {
                "doi": "10.1101/2026.01.01.123456",
                "title": "CRISPR genome editing evidence",
                "abstract": "Genome editing in human cells.",
                "authors": "Ada Lovelace; Grace Hopper",
                "date": "2026-01-01",
            },
            {"doi": "10.1101/other", "title": "Unrelated paper", "abstract": "Other topic"},
        ]
    }).encode()
    for provider in ("biorxiv", "medrxiv"):
        rows, cursor = fetch_provider(provider, "CRISPR genome", limit=5, opener=opener_for([payload]))
        assert cursor == "2"
        assert len(rows) == 1
        assert rows[0]["record_type"] == "preprint"
        assert rows[0]["metadata"]["server"] == provider
        assert rows[0]["metadata"]["fixture"] is False
