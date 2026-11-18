from __future__ import annotations

from biointel.runtime_paths import runtime_reports_directory

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def build_legacy_model_authenticity_registry(root: str | Path) -> pd.DataFrame:
    project_root = Path(root).expanduser().resolve()
    models_root = project_root / "models"
    catalog_path = models_root / "catalog.json"
    catalog = _load_json(catalog_path)
    rows: list[dict[str, Any]] = []
    changed = False

    for artifact in sorted(models_root.glob("*.joblib")):
        sidecar = artifact.with_suffix(".json")
        metadata = _load_json(sidecar)
        synthetic = bool(metadata.get("synthetic_demo", False))
        dataset_hash = str(metadata.get("dataset_sha256") or "")
        robust_split = str(metadata.get("split_strategy") or "") in {
            "cold_drug",
            "cold_target",
            "cold_drug_and_target",
            "scaffold",
            "scaffold_group",
            "temporal",
            "protein_sequence_cluster",
        }
        external = bool(metadata.get("external_validation") or metadata.get("external_validation_report"))
        if synthetic:
            state = "demo-only-quarantined"
            blockers = ["Synthetic/demo training data", "Not eligible for default scientific inference"]
        elif not metadata:
            state = "unqualified-legacy"
            blockers = ["Missing machine-readable model metadata", "No immutable dataset binding"]
        else:
            blockers = []
            if len(dataset_hash) != 64:
                blockers.append("Invalid or missing dataset SHA-256")
            if not robust_split:
                blockers.append("Leakage-resistant split not documented")
            if not external:
                blockers.append("Independent external validation absent")
            state = "qualified-candidate" if not blockers else "research-candidate"
        entry = catalog.get(artifact.name, {}) if isinstance(catalog, dict) else {}
        if synthetic:
            note = str(entry.get("notes") or "").strip()
            prefix = "[DEMO-ONLY QUARANTINED]"
            while note.startswith(prefix):
                note = note[len(prefix):].strip()
            entry["notes"] = f"{prefix} {note}".strip()
            entry["updated_at_utc"] = datetime.now(UTC).isoformat(timespec="seconds")
            catalog[artifact.name] = entry
            changed = True
        rows.append(
            {
                "artifact": artifact.name,
                "artifact_sha256": _sha256(artifact),
                "metadata_present": sidecar.is_file(),
                "synthetic_demo": synthetic,
                "dataset_sha256_valid": len(dataset_hash) == 64,
                "robust_split_documented": robust_split,
                "independent_external_validation": external,
                "authenticity_state": state,
                "default_scientific_inference_allowed": state == "qualified-candidate",
                "blockers": " | ".join(blockers),
            }
        )

    if changed:
        catalog_path.write_text(json.dumps(catalog, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    frame = pd.DataFrame(rows)
    registry = {
        "schema": "biointel.step162.legacy-model-authenticity-registry.v1",
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "models": frame.to_dict(orient="records"),
        "summary": {
            "legacy_models": len(frame),
            "synthetic_demo_quarantined": int(frame["synthetic_demo"].astype(bool).sum()) if not frame.empty else 0,
            "qualified_candidates": int((frame["authenticity_state"] == "qualified-candidate").sum()) if not frame.empty else 0,
            "default_scientific_inference_allowed": int(frame["default_scientific_inference_allowed"].astype(bool).sum()) if not frame.empty else 0,
        },
    }
    (models_root / "authenticity_registry.json").write_text(
        json.dumps(registry, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    report_dir = runtime_reports_directory(project_root)
    report_dir.mkdir(parents=True, exist_ok=True)
    frame.to_csv(report_dir / "step162_legacy_model_authenticity.csv", index=False)
    return frame


def legacy_model_authenticity(root: str | Path) -> pd.DataFrame:
    path = Path(root).expanduser().resolve() / "models" / "authenticity_registry.json"
    payload = _load_json(path)
    records = payload.get("models", []) if isinstance(payload, dict) else []
    return pd.DataFrame(records)


def safe_scientific_model_paths(root: str | Path) -> list[Path]:
    project_root = Path(root).expanduser().resolve()
    frame = legacy_model_authenticity(project_root)
    paths: list[Path] = []
    if not frame.empty:
        for row in frame.loc[frame["default_scientific_inference_allowed"].astype(bool)].to_dict(orient="records"):
            path = project_root / "models" / str(row["artifact"])
            if path.is_file():
                paths.append(path)
    return paths


__all__ = [
    "build_legacy_model_authenticity_registry",
    "legacy_model_authenticity",
    "safe_scientific_model_paths",
]
