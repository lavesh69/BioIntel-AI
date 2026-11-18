from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from biointel.connected.providers import PROVIDERS, ConnectedProviderService

ENTITY_ENUM = [
    "auto", "gene", "protein", "compound", "structure", "variant",
    "literature", "clinical trial", "pathway", "protein interaction",
    "expression study", "sequence",
]


def tool_definitions(allowed_providers: list[str] | None = None) -> list[dict[str, Any]]:
    allowed = set(allowed_providers or PROVIDERS.keys())
    tools: list[dict[str, Any]] = []
    for provider in sorted(allowed):
        if provider not in PROVIDERS:
            continue
        spec = PROVIDERS[provider]
        tools.append(
            {
                "type": "function",
                "name": f"search_{provider}",
                "description": (
                    f"Search the official {spec.name} API. {spec.description} "
                    "Use exact identifiers/accessions when available and preserve returned record IDs."
                ),
                "strict": True,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Scientific search term, exact identifier or accession. Keep it concise.",
                        },
                        "entity_type": {
                            "type": "string",
                            "enum": ENTITY_ENUM,
                        },
                        "limit": {"type": "integer", "minimum": 1, "maximum": 15},
                    },
                    "required": ["query", "entity_type", "limit"],
                    "additionalProperties": False,
                },
            }
        )
    return tools


def dispatch_tool(
    project_root: str | Path,
    name: str,
    arguments: dict[str, Any],
    *,
    allowed_providers: list[str] | None = None,
) -> dict[str, Any]:
    if not name.startswith("search_"):
        raise ValueError(f"Unsupported Copilot tool: {name}")
    provider = name.removeprefix("search_")
    allowed = set(allowed_providers or PROVIDERS.keys())
    if provider not in allowed:
        raise PermissionError(f"Provider {provider} is not enabled for this Copilot run.")
    service = ConnectedProviderService(project_root)
    result = service.search(
        provider,
        str(arguments.get("query", "")).strip(),
        entity_type=str(arguments.get("entity_type", "auto")),
        limit=min(15, max(1, int(arguments.get("limit", 8)))),
    )
    return result.to_dict()


def compact_tool_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Remove bulky raw payloads before provider evidence is sent to OpenAI."""
    compact_records: list[dict[str, Any]] = []
    for record in payload.get("records", [])[:15]:
        if not isinstance(record, dict):
            continue
        compact_records.append(
            {
                "citation": f"[{record.get('provider', payload.get('provider', 'provider'))}:{record.get('record_id', '')}]",
                "provider": record.get("provider", payload.get("provider", "")),
                "record_id": record.get("record_id", ""),
                "record_type": record.get("record_type", ""),
                "title": record.get("title", ""),
                "summary": str(record.get("summary", ""))[:1200],
                "source_url": record.get("source_url", ""),
                "score": record.get("score"),
            }
        )
    return {
        "provider": payload.get("provider"),
        "query": payload.get("query"),
        "entity_type": payload.get("entity_type"),
        "retrieved_at_utc": payload.get("retrieved_at_utc"),
        "source_url": payload.get("source_url"),
        "sha256": payload.get("sha256"),
        "cache_status": payload.get("cache_status"),
        "warnings": payload.get("warnings", []),
        "records": compact_records,
    }


def compact_tool_output(payload: dict[str, Any]) -> str:
    return json.dumps(compact_tool_payload(payload), ensure_ascii=False, sort_keys=True, default=str)[:80_000]
