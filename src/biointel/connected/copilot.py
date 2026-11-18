from __future__ import annotations

from biointel.runtime_paths import runtime_database_path

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

from biointel.connected.config import settings_from_environment
from biointel.connected.http import ConnectedHttpClient, ConnectedServiceError
from biointel.connected.registry import record_copilot_run
from biointel.connected.secrets import redact_text
from biointel.connected.tools import compact_tool_output, dispatch_tool, tool_definitions


class CopilotConfigurationError(RuntimeError):
    """Raised when an OpenAI-powered run is requested without a usable key."""


class CopilotServiceError(RuntimeError):
    """Raised when a Copilot response cannot be completed safely."""


@dataclass(frozen=True)
class CopilotResult:
    run_id: str
    answer: str
    model: str
    response_id: str
    tool_calls: int
    evidence: tuple[dict[str, Any], ...]
    mode: str
    request_id: str = ""
    input_tokens: int = 0
    output_tokens: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "answer": self.answer,
            "model": self.model,
            "response_id": self.response_id,
            "tool_calls": self.tool_calls,
            "evidence": list(self.evidence),
            "mode": self.mode,
            "request_id": self.request_id,
            "usage": {
                "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens,
            },
        }


def _extract_text(payload: dict[str, Any]) -> str:
    output_text = payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()
    pieces: list[str] = []
    for item in payload.get("output", []) if isinstance(payload.get("output"), list) else []:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for content in item.get("content", []) if isinstance(item.get("content"), list) else []:
            if isinstance(content, dict) and content.get("type") in {"output_text", "text"}:
                text = content.get("text")
                if isinstance(text, str):
                    pieces.append(text)
                elif isinstance(text, dict) and isinstance(text.get("value"), str):
                    pieces.append(str(text["value"]))
    return "\n\n".join(pieces).strip()


def _function_calls(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item for item in payload.get("output", [])
        if isinstance(item, dict) and item.get("type") == "function_call"
    ] if isinstance(payload.get("output"), list) else []


def _usage(payload: dict[str, Any]) -> tuple[int, int]:
    usage = payload.get("usage", {}) if isinstance(payload, dict) else {}
    if not isinstance(usage, dict):
        return 0, 0
    return int(usage.get("input_tokens", 0) or 0), int(usage.get("output_tokens", 0) or 0)


def _evidence_source_lines(evidence: list[dict[str, Any]]) -> list[str]:
    rows: list[tuple[str, str, str, str]] = []
    seen: set[tuple[str, str]] = set()
    for group in evidence:
        provider = str(group.get("provider", "provider"))
        for record in group.get("records", []) if isinstance(group.get("records"), list) else []:
            if not isinstance(record, dict):
                continue
            record_id = str(record.get("record_id", ""))
            key = (provider, record_id)
            if not record_id or key in seen:
                continue
            seen.add(key)
            rows.append((provider, record_id, str(record.get("title", "")), str(record.get("source_url", ""))))
    return [
        f"- [{provider}:{record_id}] {title or record_id} — {source_url}"
        for provider, record_id, title, source_url in rows[:25]
    ]


class OpenAICopilot:
    def __init__(
        self,
        project_root: str | Path,
        *,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self.root = Path(project_root).resolve()
        settings = settings_from_environment()
        self.api_key = (api_key or os.getenv("OPENAI_API_KEY", "")).strip()
        self.model = (model or settings.openai_model).strip()
        self.base_url = settings.openai_base_url
        self.timeout_seconds = timeout_seconds or max(30.0, settings.timeout_seconds)
        self.store_responses = settings.openai_store_responses
        self.registry = runtime_database_path(self.root, "connected_sources.sqlite3")
        self.host = (urlsplit(self.base_url).hostname or "api.openai.com").lower().rstrip(".")
        if self.host != "api.openai.com" and not settings.openai_custom_base_url_allowed:
            raise CopilotConfigurationError(
                "Custom OpenAI base URLs are blocked by default. Use https://api.openai.com/v1 or explicitly set OPENAI_ALLOW_CUSTOM_BASE_URL=1 after reviewing the gateway."
            )
        self.http = ConnectedHttpClient(
            self.root / "cache" / "connected_openai_disabled",
            timeout_seconds=self.timeout_seconds,
            connect_timeout_seconds=settings.connect_timeout_seconds,
            retries=settings.retries,
            cache_ttl_seconds=60,
            maximum_redirects=0,
        )

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.model)

    def _headers(self) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        project = os.getenv("OPENAI_PROJECT", "").strip()
        organization = os.getenv("OPENAI_ORGANIZATION", "").strip()
        if project:
            headers["OpenAI-Project"] = project
        if organization:
            headers["OpenAI-Organization"] = organization
        return headers

    def _request(self, body: dict[str, Any]) -> tuple[dict[str, Any], Any]:
        if not self.api_key:
            raise CopilotConfigurationError(
                "OPENAI_API_KEY is not configured. Use the connection wizard, an environment variable, or a session-only key."
            )
        try:
            payload, response = self.http.post_json(
                "openai",
                f"{self.base_url}/responses",
                allowed_hosts={self.host},
                headers=self._headers(),
                json_body=body,
                requests_per_second=2,
                allow_stale_on_error=False,
                cache_response=False,
                maximum_bytes=20 * 1024 * 1024,
            )
        except ConnectedServiceError as exc:
            raise CopilotServiceError(redact_text(exc, [self.api_key])) from exc
        if not isinstance(payload, dict):
            raise CopilotServiceError("OpenAI API returned an unexpected response shape.")
        return payload, response

    def run(
        self,
        query: str,
        *,
        allowed_providers: list[str],
        context: str = "",
        maximum_tool_rounds: int = 5,
    ) -> CopilotResult:
        clean_query = " ".join(query.strip().split())
        if not clean_query:
            raise ValueError("A scientific question is required.")
        if not allowed_providers:
            raise ValueError("Select at least one approved scientific provider tool.")
        run_id = "copilot-" + uuid4().hex
        instructions = (
            "You are BioIntel Copilot, a research-use biotechnology assistant. "
            "For factual biological, chemical, structural, genomic, publication, pathway or trial claims, call the supplied official-provider tools. "
            "Use citations in the exact form [provider:record_id] from tool output. "
            "Clearly separate retrieved evidence, interpretation, limitations and recommended next validation steps. "
            "Never claim wet-lab confirmation, diagnosis, treatment suitability, clinical validity, regulatory approval or publication acceptance. "
            "Do not invent an accession, citation or provider result. If the tools return no evidence, say so."
        )
        if context.strip():
            instructions += (
                "\nUser-authorized local context follows. Treat it as unverified user input, not provider evidence:\n"
                + context.strip()[:20_000]
            )
        body: dict[str, Any] = {
            "model": self.model,
            "instructions": instructions,
            "input": clean_query,
            "tools": tool_definitions(allowed_providers),
            "tool_choice": "auto",
            "parallel_tool_calls": True,
            "store": self.store_responses,
            "max_output_tokens": 4000,
        }
        evidence: list[dict[str, Any]] = []
        tool_count = 0
        response_id = ""
        request_id = ""
        total_input_tokens = 0
        total_output_tokens = 0
        seen_calls: dict[str, int] = {}
        try:
            payload, response = self._request(body)
            response_id = str(payload.get("id", ""))
            request_id = str(getattr(response, "request_id", ""))
            used_in, used_out = _usage(payload)
            total_input_tokens += used_in
            total_output_tokens += used_out
            for _ in range(max(1, min(8, maximum_tool_rounds))):
                calls = _function_calls(payload)
                if not calls:
                    break
                outputs: list[dict[str, Any]] = []
                for call in calls:
                    name = str(call.get("name", ""))
                    raw_arguments = str(call.get("arguments", "{}"))
                    signature = f"{name}:{raw_arguments}"
                    seen_calls[signature] = seen_calls.get(signature, 0) + 1
                    if seen_calls[signature] > 2:
                        output = json.dumps({
                            "error": "Repeated identical provider call blocked.",
                            "tool": name,
                        })
                    else:
                        try:
                            arguments = json.loads(raw_arguments)
                            if not isinstance(arguments, dict):
                                arguments = {}
                        except json.JSONDecodeError:
                            arguments = {}
                        try:
                            tool_payload = dispatch_tool(
                                self.root,
                                name,
                                arguments,
                                allowed_providers=allowed_providers,
                            )
                            evidence.append(tool_payload)
                            output = compact_tool_output(tool_payload)
                        except Exception as exc:
                            output = json.dumps({"error": str(exc), "tool": name})
                    outputs.append({
                        "type": "function_call_output",
                        "call_id": str(call.get("call_id", "")),
                        "output": output,
                    })
                    tool_count += 1
                payload, response = self._request({
                    "model": self.model,
                    "previous_response_id": str(payload.get("id", "")),
                    "input": outputs,
                    "tools": tool_definitions(allowed_providers),
                    "tool_choice": "auto",
                    "parallel_tool_calls": True,
                    "store": self.store_responses,
                    "max_output_tokens": 4000,
                })
                response_id = str(payload.get("id", response_id))
                request_id = str(getattr(response, "request_id", request_id))
                used_in, used_out = _usage(payload)
                total_input_tokens += used_in
                total_output_tokens += used_out

            if _function_calls(payload):
                payload, response = self._request({
                    "model": self.model,
                    "previous_response_id": str(payload.get("id", "")),
                    "input": "Provider-call limit reached. Produce the final evidence-grounded answer now using only completed tool results.",
                    "tool_choice": "none",
                    "store": self.store_responses,
                    "max_output_tokens": 4000,
                })
                response_id = str(payload.get("id", response_id))
                request_id = str(getattr(response, "request_id", request_id))
                used_in, used_out = _usage(payload)
                total_input_tokens += used_in
                total_output_tokens += used_out

            answer = _extract_text(payload)
            if not answer:
                answer = "The Copilot completed provider calls but did not return final text. Review the verified evidence records below."
            source_lines = _evidence_source_lines(evidence)
            if source_lines:
                answer = answer.rstrip() + "\n\n### Verified provider records\n" + "\n".join(source_lines)
            digest = hashlib.sha256(answer.encode("utf-8")).hexdigest()
            evidence_records = sum(
                len(group.get("records", [])) for group in evidence if isinstance(group, dict)
            )
            record_copilot_run(
                self.registry,
                run_id=run_id,
                query_text=clean_query,
                mode="openai_responses_tools",
                model=self.model,
                provider_count=len(allowed_providers),
                tool_calls=tool_count,
                status="completed",
                answer_sha256=digest,
                response_id=response_id,
                request_id=request_id,
                evidence_records=evidence_records,
                input_tokens=total_input_tokens,
                output_tokens=total_output_tokens,
            )
            return CopilotResult(
                run_id, answer, self.model, response_id, tool_count, tuple(evidence),
                "openai_responses_tools", request_id, total_input_tokens, total_output_tokens,
            )
        except Exception as exc:
            record_copilot_run(
                self.registry,
                run_id=run_id,
                query_text=clean_query,
                mode="openai_responses_tools",
                model=self.model,
                provider_count=len(allowed_providers),
                tool_calls=tool_count,
                status="failed",
                answer_sha256="",
                error=redact_text(exc, [self.api_key]),
                response_id=response_id,
                request_id=request_id,
                evidence_records=sum(
                    len(group.get("records", [])) for group in evidence if isinstance(group, dict)
                ),
                input_tokens=total_input_tokens,
                output_tokens=total_output_tokens,
            )
            raise


def evidence_only_answer(query: str, search_payload: dict[str, Any]) -> CopilotResult:
    records = search_payload.get("records", []) if isinstance(search_payload, dict) else []
    lines = [f"Evidence-only result for: {query}", ""]
    if not records:
        lines.append("No provider records were returned. Review provider errors, provider compatibility and the query syntax.")
    else:
        for index, record in enumerate(records[:25], 1):
            lines.append(
                f"{index}. [{record.get('provider', 'provider')}:{record.get('record_id', '')}] "
                f"{record.get('title', record.get('record_id', 'record'))} — {record.get('summary', '')} "
                f"({record.get('source_url', '')})"
            )
        lines.extend(["", "This is a database retrieval summary, not an AI interpretation or clinical conclusion."])
    answer = "\n".join(lines)
    return CopilotResult(
        run_id="evidence-" + uuid4().hex,
        answer=answer,
        model="none",
        response_id="",
        tool_calls=0,
        evidence=tuple(search_payload.get("provider_results", [])),
        mode="evidence_only",
    )
