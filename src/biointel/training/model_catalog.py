from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from biointel.utils.atomic_io import atomic_write_json

VALID_STATES = {"candidate", "active", "archived"}


@dataclass(frozen=True)
class ModelCatalogEntry:
    filename: str
    state: str
    is_default: bool
    notes: str
    updated_at_utc: str


def _catalog_path(models_directory: str | Path) -> Path:
    root = Path(models_directory).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root / "catalog.json"


def _load_raw(models_directory: str | Path) -> dict[str, dict[str, object]]:
    path = _catalog_path(models_directory)
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _save_raw(
    models_directory: str | Path,
    payload: dict[str, dict[str, object]],
) -> None:
    atomic_write_json(_catalog_path(models_directory), payload)


def sync_model_catalog(
    models_directory: str | Path,
) -> list[ModelCatalogEntry]:
    root = Path(models_directory).resolve()
    payload = _load_raw(root)
    existing = {path.name for path in root.glob("*.joblib") if path.is_file()}
    changed = False

    for filename in existing:
        if filename not in payload:
            payload[filename] = {
                "state": "candidate",
                "is_default": False,
                "notes": "",
                "updated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
            }
            changed = True

    for filename in list(payload):
        if filename not in existing:
            del payload[filename]
            changed = True

    defaults = [name for name, entry in payload.items() if bool(entry.get("is_default"))]
    if len(defaults) > 1:
        keep = sorted(defaults)[0]
        for name in defaults:
            payload[name]["is_default"] = name == keep
        changed = True

    if changed:
        _save_raw(root, payload)

    return list_model_catalog(root)


def list_model_catalog(
    models_directory: str | Path,
) -> list[ModelCatalogEntry]:
    payload = _load_raw(models_directory)
    entries = []
    for filename, data in payload.items():
        state = str(data.get("state", "candidate"))
        if state not in VALID_STATES:
            state = "candidate"
        entries.append(
            ModelCatalogEntry(
                filename=filename,
                state=state,
                is_default=bool(data.get("is_default", False)),
                notes=str(data.get("notes", "")),
                updated_at_utc=str(data.get("updated_at_utc", "")),
            )
        )
    return sorted(
        entries,
        key=lambda entry: (
            not entry.is_default,
            entry.state == "archived",
            entry.filename,
        ),
    )


def update_model_catalog(
    models_directory: str | Path,
    filename: str,
    state: str | None = None,
    is_default: bool | None = None,
    notes: str | None = None,
    enforce_quality: bool = False,
) -> ModelCatalogEntry:
    root = Path(models_directory).resolve()
    model_path = (root / Path(filename).name).resolve()
    if model_path.parent != root or not model_path.is_file():
        raise ValueError("Model file is not present in the trusted directory.")
    if state is not None and state not in VALID_STATES:
        raise ValueError("state must be candidate, active or archived")

    if enforce_quality and (state == "active" or is_default is True):
        metadata_path = model_path.with_suffix(".json")
        if not metadata_path.is_file():
            raise ValueError("Model metadata sidecar is required before activation.")
        from biointel.quality.model_audit import audit_model_metadata

        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("Model metadata sidecar is invalid.") from exc
        audit = audit_model_metadata(metadata, model_file=model_path.name)
        if not audit.release_eligible:
            raise ValueError(
                "Model cannot be activated or set as default: " + " ".join(audit.blockers)
            )

    payload = _load_raw(root)
    now = datetime.now(UTC).isoformat(timespec="seconds")
    current = payload.get(
        model_path.name,
        {
            "state": "candidate",
            "is_default": False,
            "notes": "",
            "updated_at_utc": now,
        },
    )

    if state is not None:
        current["state"] = state
    if notes is not None:
        current["notes"] = notes.strip()
    if is_default is not None:
        if is_default:
            for entry in payload.values():
                entry["is_default"] = False
            current["is_default"] = True
            if current.get("state") == "archived":
                current["state"] = "active"
        else:
            current["is_default"] = False

    current["updated_at_utc"] = now
    payload[model_path.name] = current
    _save_raw(root, payload)
    sync_model_catalog(root)

    return next(entry for entry in list_model_catalog(root) if entry.filename == model_path.name)


def default_model_path(
    models_directory: str | Path,
    *,
    require_compatible: bool = False,
) -> Path | None:
    root = Path(models_directory).resolve()
    sync_model_catalog(root)

    def accepted(path: Path) -> bool:
        if not path.is_file():
            return False
        if not require_compatible:
            return True
        from biointel.training.model_artifact import load_model_artifact_cached

        try:
            load_model_artifact_cached(path, trusted_root=root)
            return True
        except Exception:
            return False

    for entry in list_model_catalog(root):
        if entry.is_default and entry.state != "archived":
            path = root / entry.filename
            if accepted(path):
                return path
    for entry in list_model_catalog(root):
        if entry.state == "active":
            path = root / entry.filename
            if accepted(path):
                return path
    return None


def catalog_json(
    models_directory: str | Path,
) -> str:
    return json.dumps(
        [asdict(entry) for entry in list_model_catalog(models_directory)],
        indent=2,
        sort_keys=True,
    )
