from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from biointel.connected.http import ConnectedServiceError
from biointel.connected.providers import ConnectedProviderService, PROVIDERS


def contextual_provider_search(
    project_root: str | Path,
    query: str,
    *,
    provider_entity_types: dict[str, str],
    limit: int = 5,
) -> dict[str, Any]:
    clean_query = " ".join(str(query).strip().split())
    if not clean_query:
        raise ValueError("A scientific query is required.")
    selected = [provider for provider in provider_entity_types if provider in PROVIDERS]
    if not selected:
        raise ValueError("Select at least one official scientific provider.")

    service = ConnectedProviderService(project_root)
    provider_results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []

    def _query_provider(provider: str) -> tuple[str, str, Any, Any]:
        entity_type = provider_entity_types.get(provider, "literature")
        try:
            res = service.search(provider, clean_query, entity_type=entity_type, limit=limit)
            return (provider, entity_type, res, None)
        except Exception as exc:
            return (provider, entity_type, None, exc)

    workers = min(len(selected), 12)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(_query_provider, p) for p in selected]
        for future in as_completed(futures):
            provider, entity_type, result, exc = future.result()
            if exc is not None:
                if isinstance(exc, ConnectedServiceError):
                    errors.append({
                        "provider": provider,
                        "entity_type": entity_type,
                        "error_type": exc.category,
                        "http_status": exc.status_code,
                        "retryable": exc.retryable,
                        "error": str(exc),
                    })
                else:
                    errors.append({
                        "provider": provider,
                        "entity_type": entity_type,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    })
            elif result is not None:
                payload = result.to_dict()
                provider_results.append(payload)
                records.extend(record.to_dict() for record in result.records)

    return {
        "schema": "biointel.contextual-provider-search.v1",
        "query": clean_query,
        "providers_requested": selected,
        "providers_completed": [row.get("provider", "") for row in provider_results],
        "provider_results": provider_results,
        "records": records,
        "errors": errors,
        "completed_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
    }
