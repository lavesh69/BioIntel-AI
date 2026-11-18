from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest

from biointel.api.main import app
from biointel.connected.copilot import _extract_text, _function_calls
from biointel.connected.providers import PROVIDERS, ConnectedProviderService
from biointel.connected.registry import initialize_registry, registry_summary
from biointel.ui.navigation import PAGE_BY_KEY, PAGE_CATALOG

ROOT = Path(__file__).resolve().parents[1]


def test_step51_catalogue_and_pages() -> None:
    assert len(PAGE_CATALOG) >= 89
    assert {"biointel_copilot", "connected_data_explorer", "provider_integration_center"} <= set(PAGE_BY_KEY)
    assert len(PROVIDERS) == 11
    for key in ("biointel_copilot", "connected_data_explorer", "provider_integration_center"):
        assert (ROOT / PAGE_BY_KEY[key].path).is_file()


def test_step51_registry_initializes(tmp_path: Path) -> None:
    path = tmp_path / "connected.sqlite3"
    initialize_registry(path)
    assert registry_summary(path) == {
        "queries": 0,
        "records": 0,
        "providers_used": 0,
        "copilot_runs": 0,
        "health_checks": 0,
        "path": str(path.resolve()),
    }


def test_step51_copilot_response_parsing() -> None:
    payload = {
        "id": "resp_1",
        "output": [
            {"type": "function_call", "call_id": "call_1", "name": "search_ncbi", "arguments": "{}"},
            {"type": "message", "content": [{"type": "output_text", "text": "Evidence summary"}]},
        ],
    }
    assert _extract_text(payload) == "Evidence summary"
    assert _function_calls(payload)[0]["name"] == "search_ncbi"


def test_step51_api_status_and_catalogue() -> None:
    client = TestClient(app)
    providers = client.get("/v1/connectors/providers")
    assert providers.status_code == 200
    assert providers.json()["count"] == 11
    status = client.get("/v1/copilot/status")
    assert status.status_code == 200
    assert status.json()["secret_persistence"] is False
    assert len(client.get("/ui/catalog").json()["tools"]) == len(PAGE_CATALOG)


def test_step51_pages_render_without_network_calls() -> None:
    for source in (
        "pages/83_BioIntel_Copilot.py",
        "pages/84_Connected_Data_Explorer.py",
        "pages/85_Provider_Integration_Center.py",
    ):
        result = AppTest.from_file(str(ROOT / source), default_timeout=90).run(timeout=90)
        assert not result.exception, source


class _FakeResponse:
    def __init__(self, url: str, body: object):
        self.url = url
        self.sha256 = "a" * 64
        self.cache_status = "network"
        self.body = body


class _FakeClient:
    def get_json(self, provider: str, url: str, **kwargs):
        if "esearch.fcgi" in url:
            return {"esearchresult": {"idlist": ["7157"]}}, _FakeResponse(url, {})
        if "esummary.fcgi" in url:
            return {
                "result": {
                    "uids": ["7157"],
                    "7157": {"uid": "7157", "name": "TP53", "description": "tumor protein p53"},
                }
            }, _FakeResponse(url, {})
        if "/compound/name/" in url:
            return {
                "PropertyTable": {
                    "Properties": [
                        {
                            "CID": 2244,
                            "Title": "Aspirin",
                            "MolecularFormula": "C9H8O4",
                            "MolecularWeight": "180.16",
                        }
                    ]
                }
            }, _FakeResponse(url, {})
        raise AssertionError(url)

    def post_json(self, provider: str, url: str, **kwargs):
        return {"result_set": [{"identifier": "4HHB", "score": 1.0}]}, _FakeResponse(url, {})


def test_step51_ncbi_normalization_with_injected_transport(tmp_path: Path) -> None:
    service = ConnectedProviderService(tmp_path, client=_FakeClient())
    result = service.search_ncbi("TP53", database="gene", limit=1)
    assert result.records[0].record_id == "7157"
    assert result.records[0].title == "TP53"
    assert registry_summary(tmp_path / "reports" / "connected_sources.sqlite3")["records"] == 1


def test_step51_pubchem_normalization_with_injected_transport(tmp_path: Path) -> None:
    service = ConnectedProviderService(tmp_path, client=_FakeClient())
    result = service.search_pubchem("aspirin", limit=1)
    assert result.records[0].record_id == "2244"
    assert result.records[0].title == "Aspirin"
    assert result.records[0].payload["MolecularFormula"] == "C9H8O4"


def test_step51_rcsb_search_normalization_with_injected_transport(tmp_path: Path) -> None:
    service = ConnectedProviderService(tmp_path, client=_FakeClient())
    result = service.search_rcsb("hemoglobin", limit=1)
    assert result.records[0].record_id == "4HHB"
    assert result.records[0].score == 1.0
