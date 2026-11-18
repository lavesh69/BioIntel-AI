from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from biointel.shiro.exceptions import GenerationTimeoutError, ProviderUnavailableError, UserCancellationError
from biointel.shiro.generation.providers.common import build_messages, image_payloads
from biointel.shiro.models import Citation, LanguageInfo, RetrievalResult, SourceRecord


class OpenRouterProvider:
    name = "openrouter"
    external = True

    def __init__(self, api_key: str, model: str = "openrouter/free", timeout: int = 60, max_output_tokens: int = 2048, temperature: float = 0.2) -> None:
        self.api_key = api_key.strip()
        self.model = model.strip() or "openrouter/free"
        self.timeout = max(5, min(int(timeout), 300))
        self.max_output_tokens = max(128, min(int(max_output_tokens), 8192))
        self.temperature = max(0.0, min(float(temperature), 1.5))
        if not self.api_key:
            raise ProviderUnavailableError("Shiro Backup Intelligence API key is missing.")

    def generate(self, question: str, evidence: Sequence[RetrievalResult], citations: Sequence[Citation], language: LanguageInfo, *, history: Sequence[dict[str, Any]] = (), attachments: Sequence[SourceRecord] = (), cancelled: Callable[[], bool] | None = None) -> str:
        if cancelled and cancelled():
            raise UserCancellationError("Backup generation was cancelled before transmission.")
        messages = build_messages(question, evidence, citations, language, history)
        images = image_payloads(attachments)
        if images:
            text = str(messages[-1]["content"])
            content: list[dict[str, Any]] = [{"type": "text", "text": text}]
            content.extend({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data}"}} for mime, data in images)
            messages[-1]["content"] = content
        payload = {"model": self.model, "messages": messages, "temperature": self.temperature, "max_tokens": self.max_output_tokens}
        request = Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}", "HTTP-Referer": "https://biointel.app", "X-Title": "BioIntel Shiro AI"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                value = json.loads(response.read().decode("utf-8"))
        except TimeoutError as exc:
            raise GenerationTimeoutError("Shiro Backup Intelligence timed out.") from exc
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:800]
            raise ProviderUnavailableError(f"Shiro Backup Intelligence returned HTTP {exc.code}: {detail}") from exc
        except (URLError, OSError, ValueError) as exc:
            raise ProviderUnavailableError("Shiro Backup Intelligence is unavailable or returned an invalid response.") from exc
        if cancelled and cancelled():
            raise UserCancellationError("Backup generation was cancelled.")
        try:
            answer = str(value["choices"][0]["message"]["content"]).strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderUnavailableError("Shiro Backup Intelligence returned an unexpected response.") from exc
        if not answer:
            raise ProviderUnavailableError("Shiro Backup Intelligence returned an empty response.")
        return answer
