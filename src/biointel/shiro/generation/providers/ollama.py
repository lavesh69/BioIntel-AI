from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from biointel.shiro.exceptions import GenerationTimeoutError, ProviderUnavailableError, UserCancellationError
from biointel.shiro.generation.providers.common import build_messages, image_payloads
from biointel.shiro.models import Citation, LanguageInfo, RetrievalResult, SourceRecord


class OllamaLocalProvider:
    name = "ollama"
    external = False

    def __init__(self, model: str, base_url: str = "http://127.0.0.1:11434", timeout: int = 60, *, vision_model: str = "gemma3:4b", reasoning_model: str = "deepseek-r1:8b", max_output_tokens: int = 2048, temperature: float = 0.2) -> None:
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ProviderUnavailableError("Shiro only permits a loopback local-intelligence URL.")
        self.chat_model = model.strip()
        self.model = self.chat_model
        self.vision_model = vision_model.strip() or self.chat_model
        self.reasoning_model = reasoning_model.strip() or self.chat_model
        if not self.chat_model:
            raise ProviderUnavailableError("Configure a Shiro Local Intelligence model.")
        self.base_url = base_url.rstrip("/")
        self.timeout = max(5, min(int(timeout), 300))
        self.max_output_tokens = max(128, min(int(max_output_tokens), 8192))
        self.temperature = max(0.0, min(float(temperature), 1.5))

    def health(self) -> dict[str, Any]:
        try:
            with urlopen(self.base_url + "/api/tags", timeout=min(self.timeout, 5)) as response:
                value = json.loads(response.read().decode("utf-8"))
            models = [str(item.get("name", "")) for item in value.get("models", [])]
            return {"healthy": True, "models": models, "selected_available": any(name == self.chat_model or name.startswith(self.chat_model + ":") for name in models)}
        except Exception as exc:
            return {"healthy": False, "models": [], "error": f"{type(exc).__name__}: {exc}"}

    @staticmethod
    def _is_reasoning_request(question: str) -> bool:
        value = question.casefold()
        return any(term in value for term in ("reason step", "deep reasoning", "derive", "complex plan", "compare hypotheses", "analyse deeply", "analyze deeply"))

    def generate(self, question: str, evidence: Sequence[RetrievalResult], citations: Sequence[Citation], language: LanguageInfo, *, history: Sequence[dict[str, Any]] = (), attachments: Sequence[SourceRecord] = (), cancelled: Callable[[], bool] | None = None) -> str:
        if cancelled and cancelled():
            raise UserCancellationError("Local generation was cancelled before transmission.")
        images = image_payloads(attachments)
        model = self.vision_model if images else (self.reasoning_model if self._is_reasoning_request(question) else self.chat_model)
        messages = build_messages(question, evidence, citations, language, history)
        if images:
            messages[-1]["images"] = [data for _, data in images]
        payload = json.dumps({
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": self.temperature, "num_predict": self.max_output_tokens},
        }).encode("utf-8")
        request = Request(self.base_url + "/api/chat", data=payload, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urlopen(request, timeout=self.timeout) as response:
                value = json.loads(response.read().decode("utf-8"))
        except TimeoutError as exc:
            raise GenerationTimeoutError("Shiro Local Intelligence timed out.") from exc
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:800]
            raise ProviderUnavailableError(f"Shiro Local Intelligence returned HTTP {exc.code}: {detail}") from exc
        except (URLError, OSError, ValueError) as exc:
            raise ProviderUnavailableError("Shiro Local Intelligence is unavailable or returned an invalid response.") from exc
        if cancelled and cancelled():
            raise UserCancellationError("Local generation was cancelled.")
        answer = str(value.get("message", {}).get("content", "")).strip()
        if not answer:
            raise ProviderUnavailableError("Shiro Local Intelligence returned an empty response.")
        self.model = model
        return answer
