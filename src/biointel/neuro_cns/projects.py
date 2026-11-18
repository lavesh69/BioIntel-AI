from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_SCHEMA = "biointel.neuro-cns.project.v2"


def default_project_directory() -> Path:
    configured = os.environ.get("BIOINTEL_NEURO_PROJECT_DIR")
    return Path(configured).expanduser() if configured else Path.home() / ".biointel" / "neuro_cns" / "projects"


def _slug(value: str) -> str:
    token = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "").strip()).strip("-._")
    if not token:
        raise ValueError("Project name must contain at least one letter or number.")
    return token[:80]


def serialise(value: Any) -> Any:
    if isinstance(value, pd.DataFrame):
        return {"__type__": "dataframe", "columns": [str(column) for column in value.columns], "records": value.to_dict(orient="records")}
    if isinstance(value, pd.Series):
        return {"__type__": "series", "name": str(value.name or ""), "values": value.tolist()}
    if isinstance(value, dict):
        return {str(key): serialise(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [serialise(item) for item in value]
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    if hasattr(value, "tolist"):
        try:
            return value.tolist()
        except Exception:
            pass
    return value


def deserialise(value: Any) -> Any:
    if isinstance(value, dict) and value.get("__type__") == "dataframe":
        return pd.DataFrame(value.get("records", []), columns=value.get("columns"))
    if isinstance(value, dict) and value.get("__type__") == "series":
        return pd.Series(value.get("values", []), name=value.get("name"))
    if isinstance(value, dict):
        return {key: deserialise(item) for key, item in value.items()}
    if isinstance(value, list):
        return [deserialise(item) for item in value]
    return value


def project_payload(name: str, results: dict[str, Any], *, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "schema": PROJECT_SCHEMA,
        "project_name": name,
        "saved_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "metadata": metadata or {},
        "results": serialise(results),
    }


def project_json(name: str, results: dict[str, Any], *, metadata: dict[str, Any] | None = None) -> str:
    return json.dumps(project_payload(name, results, metadata=metadata), indent=2, sort_keys=True, default=str)


def load_project_bytes(data: bytes | str) -> dict[str, Any]:
    text = data.decode("utf-8") if isinstance(data, bytes) else str(data)
    payload = json.loads(text)
    if payload.get("schema") != PROJECT_SCHEMA:
        raise ValueError("Unsupported or invalid Neuro/CNS project schema.")
    payload["results"] = deserialise(payload.get("results", {}))
    payload["path"] = None
    return payload


def save_project(
    name: str,
    results: dict[str, Any],
    *,
    metadata: dict[str, Any] | None = None,
    directory: str | Path | None = None,
) -> Path:
    folder = Path(directory) if directory else default_project_directory()
    folder.mkdir(parents=True, exist_ok=True)
    destination = folder / f"{_slug(name)}.json"
    payload = project_payload(name, results, metadata=metadata)
    temporary = destination.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    os.replace(temporary, destination)
    return destination


def load_project(path_or_name: str | Path, *, directory: str | Path | None = None) -> dict[str, Any]:
    candidate = Path(path_or_name)
    if not candidate.exists():
        folder = Path(directory) if directory else default_project_directory()
        candidate = folder / f"{_slug(str(path_or_name))}.json"
    payload = load_project_bytes(candidate.read_bytes())
    payload["path"] = str(candidate)
    return payload


def list_projects(directory: str | Path | None = None) -> pd.DataFrame:
    folder = Path(directory) if directory else default_project_directory()
    rows: list[dict[str, Any]] = []
    if not folder.exists():
        return pd.DataFrame(columns=["project_name", "saved_at_utc", "module_results", "path"])
    for path in sorted(folder.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("schema") != PROJECT_SCHEMA:
                continue
            results = payload.get("results", {})
            rows.append({
                "project_name": payload.get("project_name", path.stem),
                "saved_at_utc": payload.get("saved_at_utc"),
                "module_results": len(results) if isinstance(results, dict) else 0,
                "path": str(path),
            })
        except Exception:
            rows.append({"project_name": path.stem, "saved_at_utc": None, "module_results": None, "path": str(path), "error": "unreadable"})
    return pd.DataFrame(rows)
