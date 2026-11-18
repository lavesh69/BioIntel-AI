from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from biointel.shiro.exceptions import GenerationTimeoutError, ProviderUnavailableError, UserCancellationError
from biointel.shiro.generation.providers.common import SYSTEM_PROMPT, evidence_context, image_payloads
from biointel.shiro.models import Citation, LanguageInfo, RetrievalResult, SourceRecord


class GeminiProvider:
    name = "gemini"
    external = True

    def __init__(self, api_key: str, model: str = "gemini-3.1-flash-lite", timeout: int = 60, max_output_tokens: int = 2048, temperature: float = 0.2) -> None:
        self.api_key = api_key.strip()
        self.model = model.strip()
        self.timeout = max(5, min(int(timeout), 300))
        self.max_output_tokens = max(128, min(int(max_output_tokens), 8192))
        self.temperature = max(0.0, min(float(temperature), 1.5))
        if not self.api_key:
            raise ProviderUnavailableError("Shiro Online Intelligence API key is missing.")

    def generate(self, question: str, evidence: Sequence[RetrievalResult], citations: Sequence[Citation], language: LanguageInfo, *, history: Sequence[dict[str, Any]] = (), attachments: Sequence[SourceRecord] = (), cancelled: Callable[[], bool] | None = None) -> str:
        if cancelled and cancelled():
            raise UserCancellationError("Online generation was cancelled before transmission.")
        contents: list[dict[str, Any]] = []
        for item in history[-20:]:
            role = "model" if str(item.get("role")) == "assistant" else "user"
            text = str(item.get("content", "")).strip()
            if text:
                contents.append({"role": role, "parts": [{"text": text[:12000]}]})
        context = evidence_context(evidence, citations)
        text = question + ("\n\nPROJECT EVIDENCE\n" + context if context else "\n\nNo project evidence was supplied for this turn.")
        parts: list[dict[str, Any]] = [{"text": text}]
        for mime_type, data in image_payloads(attachments):
            parts.append({"inlineData": {"mimeType": mime_type, "data": data}})
        contents.append({"role": "user", "parts": parts})
        payload = {
            "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT + f"\nRespond in {language.label}."}]},
            "contents": contents,
            "generationConfig": {"temperature": self.temperature, "maxOutputTokens": self.max_output_tokens},
        }
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{quote(self.model, safe='')}:generateContent"
        request = Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json", "x-goog-api-key": self.api_key}, method="POST")
        try:
            with urlopen(request, timeout=self.timeout) as response:
                value = json.loads(response.read().decode("utf-8"))
        except TimeoutError as exc:
            raise GenerationTimeoutError("Shiro Online Intelligence timed out.") from exc
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:800]
            raise ProviderUnavailableError(f"Shiro Online Intelligence returned HTTP {exc.code}: {detail}") from exc
        except (URLError, OSError, ValueError) as exc:
            raise ProviderUnavailableError("Shiro Online Intelligence is unavailable or returned an invalid response.") from exc
        if cancelled and cancelled():
            raise UserCancellationError("Online generation was cancelled.")
        try:
            answer = "".join(str(part.get("text", "")) for part in value["candidates"][0]["content"]["parts"]).strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderUnavailableError("Shiro Online Intelligence returned an unexpected response.") from exc
        if not answer:
            raise ProviderUnavailableError("Shiro Online Intelligence returned an empty response.")
        return answer
