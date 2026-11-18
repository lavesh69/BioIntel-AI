from __future__ import annotations

import io
import json
import shutil
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
TEST_TEMP_ROOT = ROOT / ".test-tmp"
TEST_TEMP_ROOT.mkdir(exist_ok=True)
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.shiro.api.schemas import ChatRequest
from biointel.shiro.core.language import detect_language
from biointel.shiro.core.orchestrator import ShiroOrchestrator
from biointel.shiro.exceptions import ExternalAccessDisabledError, ProviderUnavailableError
from biointel.shiro.exports import conversation_docx, conversation_json, conversation_markdown, conversation_pdf
from biointel.shiro.generation.providers.gemini import GeminiProvider
from biointel.shiro.generation.providers.ollama import OllamaLocalProvider
from biointel.shiro.generation.providers.openrouter import OpenRouterProvider
from biointel.shiro.ingestion.extractors import extract_document
from biointel.shiro.integrations.tools import suggest_actions
from biointel.shiro.models import SourceRecord
from biointel.shiro.runtime_config import MODE_LABELS, ShiroRuntimeConfig
from biointel.shiro.secure_store import ShiroSecretStore


class _FakeProvider:
    external = False

    def __init__(self, name: str = "ollama", model: str = "test-model", answer: str = "Shiro test answer") -> None:
        self.name = name
        self.model = model
        self.answer = answer
        self.calls: list[dict[str, object]] = []

    def generate(self, question, evidence, citations, language, *, history=(), attachments=(), cancelled=None):
        self.calls.append({
            "question": question,
            "evidence": tuple(evidence),
            "history": tuple(history),
            "attachments": tuple(attachments),
            "language": language.code,
        })
        return self.answer


class _FailingProvider(_FakeProvider):
    def generate(self, *args, **kwargs):
        raise ProviderUnavailableError("provider unavailable")


class _FakeHTTPResponse:
    status = 200

    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class ShiroFreeAIIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = TEST_TEMP_ROOT / ("shiro-free-ai-" + uuid4().hex)
        self.root.mkdir()
        self.service = ShiroOrchestrator(self.root, self.root / "shiro-data")
        self.service.repository.upsert_project("P1", "Project One")

    def tearDown(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def test_runtime_defaults_cover_all_public_modes(self) -> None:
        config = ShiroRuntimeConfig.load(self.root / "runtime")
        self.assertEqual(config.mode, "auto")
        self.assertEqual(config.local_model, "qwen3:4b")
        self.assertEqual(config.local_vision_model, "gemma3:4b")
        self.assertEqual(config.local_reasoning_model, "deepseek-r1:8b")
        self.assertEqual(config.openrouter_model, "openrouter/free")
        self.assertEqual(set(MODE_LABELS), {"auto", "local_private", "online_enhanced", "offline_evidence"})

    def test_runtime_config_round_trip_and_invalid_mode_fails_safe(self) -> None:
        config = ShiroRuntimeConfig(mode="local_private", max_history_messages=33, temperature=0.4)
        config.save(self.root / "runtime")
        loaded = ShiroRuntimeConfig.load(self.root / "runtime")
        self.assertEqual(loaded.mode, "local_private")
        self.assertEqual(loaded.max_history_messages, 33)
        path = self.root / "runtime" / "provider-settings.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["mode"] = "untrusted"
        path.write_text(json.dumps(payload), encoding="utf-8")
        self.assertEqual(ShiroRuntimeConfig.load(self.root / "runtime").mode, "auto")

    def test_runtime_config_invalid_numeric_values_fail_safe(self) -> None:
        runtime_dir = self.root / "runtime-invalid"
        runtime_dir.mkdir()
        (runtime_dir / "provider-settings.json").write_text(
            json.dumps({
                "max_history_messages": "not-a-number",
                "max_output_tokens": None,
                "temperature": {"unexpected": True},
            }),
            encoding="utf-8",
        )
        loaded = ShiroRuntimeConfig.load(runtime_dir)
        self.assertEqual(loaded.max_history_messages, 20)
        self.assertEqual(loaded.max_output_tokens, 2048)
        self.assertEqual(loaded.temperature, 0.2)

    def test_secret_store_round_trip_and_delete(self) -> None:
        store = ShiroSecretStore(self.root / "secrets")
        store.update(gemini_api_key="secret-one", openrouter_api_key="secret-two")
        self.assertEqual(store.get("gemini_api_key"), "secret-one")
        self.assertNotIn(b"secret-one", store.path.read_bytes())
        store.update(gemini_api_key="")
        self.assertEqual(store.get("gemini_api_key"), "")
        self.assertEqual(store.get("openrouter_api_key"), "secret-two")

    def test_general_chat_uses_multi_turn_local_provider(self) -> None:
        provider = _FakeProvider()
        self.service.ollama_provider = provider
        first = self.service.chat("P1", "Hello Shiro, explain genomics simply.", provider="auto")
        second = self.service.chat("P1", "Give one example.", conversation_id=first.conversation_id, provider="auto")
        self.assertTrue(first.general_knowledge)
        self.assertEqual(first.provider, "ollama")
        self.assertEqual(second.provider_route, ("ollama",))
        history = provider.calls[1]["history"]
        self.assertEqual([item["role"] for item in history], ["user", "assistant"])
        self.assertIn("Hello Shiro", history[0]["content"])

    def test_cloud_provider_requires_two_explicit_consent_flags(self) -> None:
        provider = _FakeProvider(name="gemini", model="online-test")
        provider.external = True
        self.service.gemini_provider = provider
        self.service.runtime.cloud_eligibility_confirmed = True
        with self.assertRaises(ExternalAccessDisabledError):
            self.service.chat("P1", "Explain TP53", provider="gemini", external_requested=True, cloud_consent=False)
        result = self.service.chat("P1", "Explain TP53", provider="gemini", external_requested=True, cloud_consent=True)
        self.assertEqual(result.provider, "gemini")
        self.assertEqual(result.provider_route, ("gemini",))

    def test_auto_mode_falls_back_without_crashing(self) -> None:
        self.service.ollama_provider = _FailingProvider()
        result = self.service.chat("P1", "Hello there", provider="auto")
        self.assertEqual(result.provider_route, ("ollama", "local"))
        self.assertEqual(result.provider, "local")
        self.assertIn("offline evidence mode", result.answer)

    def test_image_evidence_is_indexable_for_vision_attachment(self) -> None:
        from PIL import Image

        stream = io.BytesIO()
        Image.new("RGB", (48, 32), "white").save(stream, format="PNG")
        extracted = extract_document(stream.getvalue(), "figure.png", 1024 * 1024)
        self.assertEqual(extracted.source_type, "image_evidence")
        self.assertEqual(extracted.mime_type, "image/png")
        self.assertIn("48 x 32", extracted.sections[0].text)

    def test_module_action_is_available_only_for_real_page(self) -> None:
        actions = suggest_actions("Please analyse this FASTA sequence", ROOT)
        self.assertTrue(actions)
        self.assertEqual(actions[0].action_id, "sequence-analyzer")
        self.assertTrue((ROOT / actions[0].page).is_file())

    def test_conversation_exports_generate_valid_files(self) -> None:
        messages = [
            {"role": "user", "content": "Explain TP53"},
            {"role": "assistant", "content": "TP53 is a research-relevant tumour suppressor.", "citations": []},
        ]
        self.assertIn("# Test", conversation_markdown("Test", messages))
        self.assertEqual(json.loads(conversation_json(messages))[0]["role"], "user")
        docx_bytes = conversation_docx("Test", messages)
        pdf_bytes = conversation_pdf("Test", messages)
        self.assertTrue(docx_bytes.startswith(b"PK"))
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        self.assertGreater(len(docx_bytes), 1000)
        self.assertGreater(len(pdf_bytes), 1000)

    def test_api_schema_accepts_new_modes_and_attachment_ids(self) -> None:
        value = ChatRequest(project_id="P1", message="Hello", provider="online_enhanced", external_requested=True, cloud_consent=True, attachment_source_ids=["SRC-1"])
        self.assertEqual(value.provider, "online_enhanced")
        self.assertEqual(value.attachment_source_ids, ["SRC-1"])

    def test_gemini_provider_builds_multi_turn_request(self) -> None:
        provider = GeminiProvider("test-key", "gemini-test")
        captured: dict[str, object] = {}

        def fake_urlopen(request, timeout=0):
            captured["url"] = request.full_url
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            return _FakeHTTPResponse({"candidates": [{"content": {"parts": [{"text": "online ok"}]}}]})

        with patch("biointel.shiro.generation.providers.gemini.urlopen", side_effect=fake_urlopen):
            result = provider.generate(
                "second question", (), (), detect_language("second question"),
                history=({"role": "user", "content": "first question"}, {"role": "assistant", "content": "first answer"}),
            )
        self.assertEqual(result, "online ok")
        self.assertIn("gemini-test:generateContent", captured["url"])
        contents = captured["payload"]["contents"]
        self.assertEqual([item["role"] for item in contents], ["user", "model", "user"])

    def test_openrouter_provider_uses_free_router_contract(self) -> None:
        provider = OpenRouterProvider("test-key", "openrouter/free")
        captured: dict[str, object] = {}

        def fake_urlopen(request, timeout=0):
            captured["headers"] = dict(request.header_items())
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            return _FakeHTTPResponse({"choices": [{"message": {"content": "backup ok"}}]})

        with patch("biointel.shiro.generation.providers.openrouter.urlopen", side_effect=fake_urlopen):
            result = provider.generate("hello", (), (), detect_language("hello"))
        self.assertEqual(result, "backup ok")
        self.assertEqual(captured["payload"]["model"], "openrouter/free")
        self.assertIn("Authorization", captured["headers"])

    def test_ollama_switches_vision_per_request_then_returns_to_chat_model(self) -> None:
        image_path = self.root / "vision.png"
        from PIL import Image
        Image.new("RGB", (16, 16), "white").save(image_path)
        source = SourceRecord(
            "SRC-1", "P1", "vision.png", "image_evidence", "image/png", image_path.stat().st_size,
            "abc", "2026-01-01T00:00:00Z", file_path=str(image_path),
        )
        provider = OllamaLocalProvider("qwen3:4b", vision_model="gemma3:4b", reasoning_model="deepseek-r1:8b")
        sent_models: list[str] = []

        def fake_urlopen(request, timeout=0):
            payload = json.loads(request.data.decode("utf-8"))
            sent_models.append(payload["model"])
            return _FakeHTTPResponse({"message": {"content": "ok"}})

        language = detect_language("hello")
        with patch("biointel.shiro.generation.providers.ollama.urlopen", side_effect=fake_urlopen):
            provider.generate("hello", (), (), language)
            provider.generate("describe image", (), (), language, attachments=(source,))
            provider.generate("hello again", (), (), language)
        self.assertEqual(sent_models, ["qwen3:4b", "gemma3:4b", "qwen3:4b"])
        self.assertEqual(provider.chat_model, "qwen3:4b")


if __name__ == "__main__":
    unittest.main(verbosity=2)
