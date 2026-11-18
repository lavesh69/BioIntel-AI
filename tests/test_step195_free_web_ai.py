from __future__ import annotations

from pathlib import Path

import pytest

from biointel.connected.free_web_ai import (
    DEFAULT_OLLAMA_URL,
    FreeWebAIConfigurationError,
    FreeWebCopilot,
    OllamaClient,
    SearxNGClient,
    WebSearchRecord,
    WebSearchResult,
    _validate_ollama_url,
    _validate_searxng_base_url,
    infer_entity_type,
)


def test_ollama_is_loopback_only() -> None:
    assert _validate_ollama_url("http://localhost:11434") == DEFAULT_OLLAMA_URL
    with pytest.raises(FreeWebAIConfigurationError):
        _validate_ollama_url("https://example.com")
    with pytest.raises(FreeWebAIConfigurationError):
        _validate_ollama_url("http://127.0.0.1:8080")


def test_local_searxng_url_is_allowed() -> None:
    assert _validate_searxng_base_url("http://127.0.0.1:8080") == "http://127.0.0.1:8080"


def test_entity_inference() -> None:
    assert infer_entity_type("find EGFR protein structure") == "structure"
    assert infer_entity_type("current recruiting cancer trial") == "clinical trial"
    assert infer_entity_type("BRCA1 variant") == "variant"


def test_ollama_diagnostic_reports_model(monkeypatch: pytest.MonkeyPatch) -> None:
    client = OllamaClient(model="gemma3:1b")
    monkeypatch.setattr(client, "list_models", lambda: ["gemma3:1b"])
    result = client.diagnostic()
    assert result["available"] is True
    assert result["model_visible"] is True


def test_searxng_uses_first_working_candidate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = SearxNGClient(tmp_path)
    monkeypatch.setattr(client, "_directory_candidates", lambda: ["https://one.example", "https://two.example"])

    def fake_request(url: str, query: str, limit: int) -> WebSearchResult:
        if "one" in url:
            raise RuntimeError("down")
        return WebSearchResult(
            query=query,
            instance_url=url,
            records=(WebSearchRecord("r1", "Title", "Summary", "https://source.example"),),
            elapsed_ms=1.0,
        )

    monkeypatch.setattr(client, "_request_search", fake_request)
    result = client.search("bioinformatics")
    assert result.instance_url == "https://two.example"
    assert len(result.records) == 1


def test_free_web_copilot_combines_web_and_provider_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = FreeWebCopilot(tmp_path, model="gemma3:1b")

    class FakeSearx:
        def search(self, query: str, *, limit: int = 8) -> WebSearchResult:
            return WebSearchResult(
                query=query,
                instance_url="https://search.example",
                records=(
                    WebSearchRecord(
                        "web1", "Web result", "Web summary", "https://source.example"
                    ),
                ),
                elapsed_ms=2.0,
            )

    class FakeOllama:
        model = "gemma3:1b"

        def chat(self, *, system: str, prompt: str):
            assert "[searxng:web1]" in prompt
            assert "[ncbi:1]" in prompt
            return "Grounded answer [searxng:web1] [ncbi:1]", {
                "input_tokens": 12,
                "output_tokens": 8,
            }

    runner.searxng = FakeSearx()  # type: ignore[assignment]
    runner.ollama = FakeOllama()  # type: ignore[assignment]

    from biointel.connected import free_web_ai as module

    monkeypatch.setattr(
        module.ConnectedProviderService,
        "universal_search",
        lambda self, *args, **kwargs: {
            "provider_results": [
                {
                    "provider": "ncbi",
                    "records": [
                        {
                            "provider": "ncbi",
                            "record_id": "1",
                            "record_type": "literature",
                            "title": "Provider result",
                            "summary": "Provider summary",
                            "source_url": "https://pubmed.ncbi.nlm.nih.gov/1/",
                        }
                    ],
                }
            ]
        },
    )
    result = runner.run(
        "What is new?",
        allowed_providers=["ncbi"],
        use_web_search=True,
        use_scientific_providers=True,
    )
    assert result.mode == "ollama_searxng_scientific_providers"
    assert result.input_tokens == 12
    assert "Retrieved sources" in result.answer
    assert len(result.evidence) == 2


def test_free_web_copilot_allows_provider_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = FreeWebCopilot(tmp_path, model="gemma3:1b")

    class FakeOllama:
        model = "gemma3:1b"

        def chat(self, *, system: str, prompt: str):
            return "Answer [ncbi:1]", {"input_tokens": 1, "output_tokens": 1}

    runner.ollama = FakeOllama()  # type: ignore[assignment]
    from biointel.connected import free_web_ai as module

    monkeypatch.setattr(
        module.ConnectedProviderService,
        "universal_search",
        lambda self, *args, **kwargs: {
            "provider_results": [
                {
                    "provider": "ncbi",
                    "records": [
                        {
                            "record_id": "1",
                            "title": "A",
                            "summary": "B",
                            "source_url": "https://pubmed.ncbi.nlm.nih.gov/1/",
                        }
                    ],
                }
            ]
        },
    )
    result = runner.run(
        "question",
        allowed_providers=["ncbi"],
        use_web_search=False,
        use_scientific_providers=True,
    )
    assert result.answer.startswith("Answer")


def test_default_model_is_lightweight() -> None:
    assert OllamaClient().model == "gemma3:1b"


def test_step195_release_and_two_step_installer_contract() -> None:
    root = Path(__file__).resolve().parents[1]
    assert (root / "VERSION").read_text(encoding="utf-8").strip() in {"15.2.0", "15.3.0", "15.4.0"}
    install = (root / "INSTALL_WINDOWS.bat").read_text(encoding="utf-8-sig")
    run = (root / "RUN_BOTH_WINDOWS.bat").read_text(encoding="utf-8-sig")
    installer = (root / "scripts" / "install_windows_step195.py").read_text(encoding="utf-8-sig")
    assert ("step195_part%%P.ok" in install or "step196_part%%P.ok" in install)
    assert ("install_windows_step195.py" in install or "install_windows_step196.py" in install)
    assert ("run_biointel_step195.py" in run or "run_biointel_step196.py" in run)
    assert "setup_free_web_ai_windows.py" in installer
    assert "--deep-hashes" in installer


def test_release_metadata_check_is_read_only() -> None:
    root = Path(__file__).resolve().parents[1]
    script = (root / "scripts" / "repair_step195_release_metadata.py").read_text(encoding="utf-8-sig")
    assert "package_files_modified\": False" in script
    assert ".write_text(json.dumps(active_payload" not in script
    assert "EXPECTED_STEP = 195" in script
    assert 'EXPECTED_VERSION = "15.2.0"' in script
