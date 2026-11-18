from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest

from biointel.api.main import app
from biointel.connected.copilot import CopilotConfigurationError, OpenAICopilot
from biointel.connected.diagnostics import test_openai_connection as openai_connection_check
from biointel.connected.http import ConnectedHttpClient, ConnectedServiceError
from biointel.connected.providers import (
    PROVIDERS,
    ConnectedProviderService,
    provider_supports_entity,
)
from biointel.connected.registry import initialize_registry, registry_summary

ROOT = Path(__file__).resolve().parents[1]


def test_step52_provider_catalogue_contract() -> None:
    assert len(PROVIDERS) == 11
    assert provider_supports_entity("ncbi", "gene")
    assert provider_supports_entity("uniprot", "protein")
    assert not provider_supports_entity("uniprot", "compound")
    assert all(spec.documentation_url.startswith("https://") for spec in PROVIDERS.values())


def test_step52_registry_schema_and_summary(tmp_path: Path) -> None:
    path = initialize_registry(tmp_path / "connected.sqlite3")
    summary = registry_summary(path)
    assert summary["queries"] == 0
    assert summary["health_checks"] == 0
    assert summary["copilot_runs"] == 0


def test_step52_http_redacts_secrets_from_provenance_and_cache(tmp_path: Path) -> None:
    secret = "super-secret-ncbi-key"

    def handler(request: httpx.Request) -> httpx.Response:
        assert secret in str(request.url)
        return httpx.Response(200, json={"ok": True}, headers={"x-request-id": "req-123"})

    client = ConnectedHttpClient(
        tmp_path / "cache",
        retries=0,
        transport=httpx.MockTransport(handler),
    )
    payload, response = client.get_json(
        "ncbi",
        f"https://eutils.ncbi.nlm.nih.gov/test?api_key={secret}&term=TP53",
        allowed_hosts={"eutils.ncbi.nlm.nih.gov"},
    )
    assert payload == {"ok": True}
    assert secret not in response.url
    metadata = "\n".join(path.read_text(encoding="utf-8") for path in (tmp_path / "cache").glob("*.json"))
    assert secret not in metadata
    assert "REDACTED" in metadata


def test_step52_http_retries_429_and_respects_host_allowlist(tmp_path: Path) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, json={"error": "rate"}, headers={"retry-after": "0"})
        return httpx.Response(200, json={"ok": True})

    client = ConnectedHttpClient(
        tmp_path / "cache",
        retries=1,
        transport=httpx.MockTransport(handler),
    )
    payload, _ = client.get_json(
        "uniprot",
        "https://rest.uniprot.org/uniprotkb/search?query=TP53",
        allowed_hosts={"rest.uniprot.org"},
    )
    assert payload["ok"] is True
    assert calls == 2
    with pytest.raises(ConnectedServiceError, match="not approved"):
        client.get_json(
            "uniprot",
            "https://example.com/steal",
            allowed_hosts={"rest.uniprot.org"},
        )


class FakeResponse:
    def __init__(self, url: str):
        self.url = url
        self.sha256 = "b" * 64
        self.cache_status = "network"
        self.elapsed_ms = 12.5
        self.request_id = "req-fake"
        self.headers = {"etag": "v1"}


class AllProviderFakeClient:
    def get_json(self, provider: str, url: str, **kwargs):
        response = FakeResponse(url)
        if "esearch.fcgi" in url:
            return {"esearchresult": {"idlist": ["7157"]}}, response
        if "esummary.fcgi" in url:
            return {"result": {"uids": ["7157"], "7157": {"name": "TP53", "description": "tumor protein p53"}}}, response
        if "pubchem" in url:
            return {"PropertyTable": {"Properties": [{"CID": 2244, "Title": "Aspirin", "MolecularFormula": "C9H8O4", "MolecularWeight": "180.16"}]}}, response
        if "uniprotkb/search" in url:
            return {"results": [{"primaryAccession": "P04637", "uniProtkbId": "P53_HUMAN", "entryType": "UniProtKB reviewed (Swiss-Prot)", "proteinDescription": {"recommendedName": {"fullName": {"value": "Cellular tumor antigen p53"}}}, "organism": {"scientificName": "Homo sapiens"}, "sequence": {"length": 393}, "genes": [{"geneName": {"value": "TP53"}}]}]}, response
        if "/core/entry/" in url:
            return {"struct": {"title": "Hemoglobin"}, "exptl": [{"method": "X-RAY DIFFRACTION"}], "rcsb_entry_info": {"resolution_combined": [1.74]}}, response
        if "chembl/api/data/molecule/" in url:
            return {"molecule_chembl_id": "CHEMBL25", "pref_name": "ASPIRIN", "molecule_type": "Small molecule", "molecule_properties": {"full_mwt": 180.16}}, response
        if "lookup/" in url:
            return {"id": "ENSG00000141510", "display_name": "TP53", "biotype": "protein_coding", "seq_region_name": "17", "start": 1, "end": 2, "strand": -1}, response
        if "clinicaltrials" in url:
            return {"studies": [{"protocolSection": {"identificationModule": {"nctId": "NCT00000001", "briefTitle": "TP53 study"}, "statusModule": {"overallStatus": "RECRUITING"}, "designModule": {"studyType": "INTERVENTIONAL"}}}]}, response
        if "reactome" in url:
            return {"results": [{"entries": [{"stId": "R-HSA-1", "name": "TP53 pathway", "typeName": "Pathway"}]}]}, response
        if "string-db" in url:
            return [{"preferredName_A": "TP53", "preferredName_B": "BRCA1", "stringId_A": "9606.ENSP1", "score": 0.9}], response
        if "interpro" in url:
            return {"results": [{"metadata": {"accession": "IPR0001", "name": "p53 domain", "type": "domain"}}]}, response
        if "europepmc" in url:
            return {"resultList": {"result": [{"pmid": "123", "title": "CRISPR paper", "source": "MED", "authorString": "A Author", "journalTitle": "Journal", "pubYear": "2026"}]}}, response
        raise AssertionError(url)

    def post_json(self, provider: str, url: str, **kwargs):
        return {"result_set": [{"identifier": "4HHB", "score": 1.0}]}, FakeResponse(url)


def test_step52_all_provider_normalizers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NCBI_EMAIL", "test@example.com")
    service = ConnectedProviderService(tmp_path, client=AllProviderFakeClient())
    cases = [
        ("ncbi", "TP53", "gene"),
        ("pubchem", "aspirin", "compound"),
        ("uniprot", "P04637", "protein"),
        ("rcsb", "4HHB", "structure"),
        ("chembl", "CHEMBL25", "compound"),
        ("ensembl", "TP53", "gene"),
        ("clinicaltrials", "TP53", "clinical trial"),
        ("reactome", "TP53", "pathway"),
        ("string", "TP53 BRCA1", "protein interaction"),
        ("interpro", "P04637", "protein"),
        ("europepmc", "CRISPR", "literature"),
    ]
    for provider, query, entity in cases:
        result = service.search(provider, query, entity_type=entity, limit=1)
        assert result.records, provider
        assert result.request_id == "req-fake"
        assert result.elapsed_ms == 12.5


def test_step52_openai_missing_key_is_safe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    result = openai_connection_check(tmp_path)
    assert result["available"] is False
    assert result["status"] == "key_required"



def test_step52_custom_openai_gateway_requires_explicit_opt_in(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("OPENAI_ALLOW_CUSTOM_BASE_URL", "0")
    with pytest.raises(CopilotConfigurationError):
        OpenAICopilot(tmp_path, api_key="sk-test", model="gpt-test")
    diagnostic = openai_connection_check(tmp_path, api_key="sk-test", model="gpt-test")
    assert diagnostic["available"] is False
    assert diagnostic["status"] == "blocked_custom_base_url"


def test_step52_copilot_tool_loop_adds_verified_sources(tmp_path: Path) -> None:
    copilot = OpenAICopilot(tmp_path, api_key="sk-test", model="gpt-test")
    responses = iter([
        (
            {"id": "resp1", "output": [{"type": "function_call", "call_id": "call1", "name": "search_ncbi", "arguments": json.dumps({"query": "TP53", "entity_type": "gene", "limit": 1})}], "usage": {"input_tokens": 10, "output_tokens": 2}},
            FakeResponse("https://api.openai.com/v1/responses"),
        ),
        (
            {"id": "resp2", "output": [{"type": "message", "content": [{"type": "output_text", "text": "TP53 evidence [ncbi:7157]."}]}], "usage": {"input_tokens": 8, "output_tokens": 5}},
            FakeResponse("https://api.openai.com/v1/responses"),
        ),
    ])
    copilot._request = lambda body: next(responses)  # type: ignore[method-assign]

    original = ConnectedProviderService.search
    try:
        def fake_search(self, provider, query, *, entity_type="auto", limit=10):
            service = ConnectedProviderService(tmp_path, client=AllProviderFakeClient())
            return original(service, provider, query, entity_type=entity_type, limit=limit)
        ConnectedProviderService.search = fake_search  # type: ignore[assignment]
        result = copilot.run("What is TP53?", allowed_providers=["ncbi"])
    finally:
        ConnectedProviderService.search = original  # type: ignore[assignment]
    assert "Verified provider records" in result.answer
    assert "[ncbi:7157]" in result.answer
    assert result.input_tokens == 18
    assert result.output_tokens == 7


def test_step52_api_and_pages_render_without_network() -> None:
    client = TestClient(app)
    status = client.get("/v1/copilot/status")
    assert status.status_code == 200
    assert status.json()["secret_persistence"] is False
    providers = client.get("/v1/connectors/providers")
    assert providers.status_code == 200
    assert providers.json()["count"] == 11
    for source in (
        "pages/83_BioIntel_Copilot.py",
        "pages/84_Connected_Data_Explorer.py",
        "pages/85_Provider_Integration_Center.py",
    ):
        result = AppTest.from_file(str(ROOT / source), default_timeout=90).run(timeout=90)
        assert not result.exception, source
