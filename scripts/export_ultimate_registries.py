from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCE = str(ROOT / "src")
if SOURCE not in sys.path:
    sys.path.insert(0, SOURCE)

from biointel.product_registry import registry_as_dicts, registry_integrity  # noqa: E402


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _cell(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return " | ".join(str(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True, ensure_ascii=False)
    return value


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _cell(row.get(key, "")) for key in fields})


def _write_registry(output: Path, stem: str, schema: str, rows: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    payload = {
        "schema": schema,
        "release_version": "15.6.0",
        "release_step": 206,
        "generated_at_utc": _now(),
        "summary": summary,
        "records": rows,
    }
    (output / f"{stem}.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    _write_csv(output / f"{stem}.csv", rows)


def module_rows(root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = registry_as_dicts(root)
    integrity = registry_integrity(root)
    return rows, {
        **integrity,
        "functional": sum(row["development_status"] == "Functional" for row in rows),
        "external_asset_required": sum(row["full_analysis_requires_external_assets"] for row in rows),
        "with_sample_data": sum(bool(row["sample_data"]) for row in rows),
        "with_input_templates": sum(bool(row["input_templates"]) for row in rows),
    }


def _safe_ast_value(node: ast.AST) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, (ast.Tuple, ast.List)):
        return tuple(_safe_ast_value(item) for item in node.elts)
    if isinstance(node, ast.Dict):
        return {_safe_ast_value(key): _safe_ast_value(value) for key, value in zip(node.keys, node.values, strict=True)}
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "sys" and node.attr == "executable":
        return "python"
    raise ValueError(f"Unsupported engine-catalog expression: {ast.dump(node, include_attributes=False)[:300]}")


def _engine_definitions(root: Path) -> dict[str, dict[str, Any]]:
    source_path = root / "src" / "biointel" / "native" / "engines.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    assignment = next(
        node
        for node in tree.body
        if (
            isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "ENGINE_REGISTRY" for target in node.targets)
        )
        or (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "ENGINE_REGISTRY"
        )
    )
    if not isinstance(assignment.value, ast.Dict):
        raise ValueError("ENGINE_REGISTRY must be a dictionary literal.")
    fields = (
        "key",
        "label",
        "executables",
        "category",
        "capabilities",
        "version_args",
        "required_databases",
        "gpu_optional",
        "installation_note",
    )
    defaults: dict[str, Any] = {
        "version_args": ("--version",),
        "required_databases": (),
        "gpu_optional": False,
        "installation_note": "",
    }
    output: dict[str, dict[str, Any]] = {}
    for key_node, value_node in zip(assignment.value.keys, assignment.value.values, strict=True):
        key = str(_safe_ast_value(key_node))
        if not isinstance(value_node, ast.Call) or not isinstance(value_node.func, ast.Name) or value_node.func.id != "EngineSpec":
            raise ValueError(f"Engine {key} is not an EngineSpec call.")
        row = dict(defaults)
        for field, argument in zip(fields, value_node.args, strict=False):
            row[field] = _safe_ast_value(argument)
        for keyword in value_node.keywords:
            if keyword.arg:
                row[keyword.arg] = _safe_ast_value(keyword.value)
        output[key] = row
    return output


def engine_rows(root: Path) -> list[dict[str, Any]]:
    release = _read_json(root / "config" / "engine_platform_v196_release_manifest.json")
    pins = release.get("engines", {}) if isinstance(release, dict) else {}
    rows: list[dict[str, Any]] = []
    for key, spec in sorted(_engine_definitions(root).items()):
        pin = pins.get(key, {}) if isinstance(pins, dict) else {}
        rows.append(
            {
                "id": key,
                "name": spec["label"],
                "label": spec["label"],
                "category": spec["category"],
                "scientific_purpose": " | ".join(str(item) for item in spec["capabilities"]),
                "provider": "External scientific software provider; see licence URL and acquisition plan",
                "capabilities": list(spec["capabilities"]),
                "candidate_executables": list(spec["executables"]),
                "executable_path": "Resolved and validated at runtime; never hardcoded",
                "version_probe": list(spec["version_args"]),
                "required_databases": list(spec["required_databases"]),
                "gpu_optional": spec["gpu_optional"],
                "installation_note": spec["installation_note"],
                "pinned_version": str(pin.get("version", "")),
                "licence_url": str(pin.get("licence_url", "")),
                "artifact_sha256": str(pin.get("artifact_sha256", "")),
                "licence_sha256": str(pin.get("licence_sha256", "")),
                "qualification_status": str(pin.get("qualification_status", "external-not-installed")),
                "windows_native_evidence": str(pin.get("windows_evidence", "not-run")),
                "wsl2_evidence": str(pin.get("wsl2_evidence", "not-run")),
                "installation_type": "External Windows-native or WSL2/micromamba acquisition; not bundled",
                "cpu_requirements": "Engine-specific; qualify on target machine",
                "gpu_requirements": "Optional where declared" if spec["gpu_optional"] else "No bundled GPU claim; verify provider requirements",
                "memory_requirement": "Engine- and dataset-specific; qualify on representative workloads",
                "configuration": "Engine Control Center managed metadata and environment configuration",
                "test_command": list(spec["version_args"]),
                "expected_test_output": "Successful version probe matching the pinned release plus positive/negative smoke evidence",
                "last_test_date": "",
                "health_status": "Unavailable until runtime detection and target qualification pass",
                "failure_reason": "External artifact, licence, version or target-machine evidence incomplete",
                "fallback": "Disable engine-backed action and preserve bounded built-in/offline workflow where scientifically valid",
                "update_policy": "Explicit operator-approved update with checksum, licence and requalification",
                "bundled": False,
                "availability": "Detected at runtime; external engines are not claimed as bundled",
            }
        )
    return rows


def model_rows(root: Path) -> list[dict[str, Any]]:
    models = root / "models"
    catalog = _read_json(models / "catalog.json")
    authenticity = _read_json(models / "authenticity_registry.json")
    authenticity_records = authenticity.get("models", []) if isinstance(authenticity, dict) else []
    authenticity_rows = {
        str(row.get("artifact")): row
        for row in authenticity_records
        if isinstance(row, dict)
    }
    names = set(catalog if isinstance(catalog, dict) else {})
    names.update(path.name for path in models.glob("*.joblib"))
    rows: list[dict[str, Any]] = []
    for name in sorted(names):
        path = models / name
        entry = catalog.get(name, {}) if isinstance(catalog, dict) else {}
        auth = authenticity_rows.get(name, {})
        sidecar = _read_json(path.with_suffix(".json"))
        synthetic_demo = bool(auth.get("synthetic_demo", sidecar.get("synthetic_demo", False)))
        inference_allowed = bool(auth.get("default_scientific_inference_allowed", False))
        rows.append(
            {
                "model_id": name,
                "name": str(sidecar.get("model_name", name)),
                "version": str(sidecar.get("model_version", entry.get("version", "unversioned"))),
                "artifact": name,
                "scientific_task": str(sidecar.get("scientific_task", sidecar.get("task", "Not recorded; qualification blocked"))),
                "architecture": str(sidecar.get("algorithm", sidecar.get("architecture", "Not recorded"))),
                "provider": str(sidecar.get("provider", "BioIntel packaged artifact; provenance must be reviewed")),
                "weight_location": f"models/{name}",
                "present": path.is_file(),
                "size_bytes": path.stat().st_size if path.is_file() else 0,
                "sha256": _sha256(path) if path.is_file() else "",
                "licence": str(sidecar.get("licence", sidecar.get("license", "Not recorded; qualification blocked"))),
                "input_schema": sidecar.get("input_schema", "See model metadata and runtime schema gate"),
                "output_schema": sidecar.get("output_schema", "See model metadata and runtime schema gate"),
                "preprocessing": sidecar.get("preprocessing", "Versioned runtime pipeline; review artifact metadata"),
                "postprocessing": sidecar.get("postprocessing", "Schema/range/applicability checks required"),
                "hardware_requirements": sidecar.get("hardware_requirements", "CPU by default; artifact-specific GPU requirements must be qualified"),
                "training_data_provenance": sidecar.get("training_data_provenance", sidecar.get("dataset_sha256", "Not recorded")),
                "validation_datasets": sidecar.get("validation_datasets", "Not recorded"),
                "evaluation_metrics": sidecar.get("evaluation_metrics", sidecar.get("metrics", "Not recorded")),
                "calibration_metrics": sidecar.get("calibration_metrics", "Not recorded"),
                "subgroup_metrics": sidecar.get("subgroup_metrics", "Not recorded"),
                "state": str(entry.get("state", "unregistered")),
                "is_default": bool(entry.get("is_default", False)),
                "authenticity_state": str(auth.get("authenticity_state", "not assessed")),
                "model_classification": "Demonstration model" if synthetic_demo else str(sidecar.get("model_classification", "Trained/imported artifact; provenance review required")),
                "synthetic_demo": synthetic_demo,
                "default_scientific_inference_allowed": inference_allowed,
                "training_dataset_sha256": str(sidecar.get("dataset_sha256", "")),
                "split_strategy": str(sidecar.get("split_strategy", "")),
                "external_validation": bool(sidecar.get("external_validation") or sidecar.get("external_validation_report")),
                "intended_use": str(sidecar.get("intended_use", "Research/demo use only unless separately qualified")),
                "prohibited_use": str(sidecar.get("prohibited_use", "No autonomous clinical, therapeutic, safety-critical or regulatory decision-making")),
                "research_only": True,
                "qualification_status": "Software-eligible" if inference_allowed else "Blocked or demonstration-only pending qualification",
                "limitations": str(entry.get("notes", "No release qualification metadata supplied")),
                "blockers": str(auth.get("blockers", "")),
            }
        )
    return rows


def reference_rows(root: Path) -> list[dict[str, Any]]:
    payload = _read_json(root / "config" / "reference_assets_manifest.json")
    rows: list[dict[str, Any]] = []
    for item in payload.get("templates", []) if isinstance(payload, dict) else []:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "id": str(item.get("id", "")),
                "name": str(item.get("name", item.get("id", ""))),
                "provider": str(item.get("provider", "")),
                "scientific_domain": str(item.get("domain", item.get("purpose", ""))),
                "purpose": str(item.get("purpose", "")),
                "release": "User-selected; must be pinned at activation",
                "genome_build": "Asset-specific; must be recorded when applicable",
                "schema_version": "Provider-specific; must be recorded at activation",
                "checksum": "Required at activation",
                "licence": "Acceptance required; review provider terms",
                "download_source": "Operator-supplied official provider source; no silent download",
                "citation": "Provider citation required at activation",
                "download_size": "Unknown until a release is selected",
                "installed_size": "Measured after verified installation",
                "bundled": False,
                "local_path": "%LOCALAPPDATA%/BioIntelAI/ReferenceAssets/<asset>/<release>",
                "compatible_modules": item.get("compatible_modules", []),
                "compatible_engines": item.get("compatible_engines", []),
                "last_update": "",
                "installation_status": "Not installed by default",
                "integrity_status": "Not verified until checksum-bound activation",
                "rollback_version": "Previous verified activation when available",
                "activation_status": "External dependency required",
                "storage": "%LOCALAPPDATA%/BioIntelAI/ReferenceAssets",
                "lifecycle_controls": ["selective install", "resume/retry", "checksum", "licence", "version lock", "offline import", "repair", "rollback", "delete"],
                "notes": str(item.get("notes", "")),
            }
        )
    return rows


def _module_status_markdown(rows: list[dict[str, Any]], summary: dict[str, Any]) -> str:
    categories: dict[str, int] = {}
    for row in rows:
        categories[str(row["category"])] = categories.get(str(row["category"]), 0) + 1
    lines = [
        "# BioIntel AI Module-by-Module Status",
        "",
        f"Release: 15.6.0 Step206 · Registry records: {len(rows)}",
        "",
        "Every user-facing page appears exactly once in the authoritative registry. Functional means the software surface exists and passed software gates; it does not imply clinical, regulatory or independent scientific validation.",
        "",
        "## Integrity",
        "",
        f"- Registry healthy: {summary.get('healthy')}",
        f"- Missing/disabled pages: {len(summary.get('disabled_or_missing', []))}",
        f"- Duplicate IDs: {len(summary.get('duplicate_ids', []))}",
        f"- Full-analysis external assets required: {summary.get('external_asset_required', 0)}",
        "",
        "## Category coverage",
        "",
        "| Category | Modules |",
        "|---|---:|",
        *[f"| {category} | {count} |" for category, count in sorted(categories.items())],
        "",
        "Detailed per-module status, inputs, outputs, engines, references, limitations, fallbacks and feature flags are in `MODULE_REGISTRY.csv` and `MODULE_REGISTRY.json`.",
        "",
    ]
    return "\n".join(lines)


def export_all(root: Path, output: Path) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    modules, module_summary = module_rows(root)
    if not module_summary.get("healthy"):
        raise RuntimeError(f"Module registry integrity failed: {module_summary}")
    engines = engine_rows(root)
    models = model_rows(root)
    references = reference_rows(root)
    _write_registry(output, "MODULE_REGISTRY", "biointel.module-registry.v3", modules, module_summary)
    _write_registry(output, "ENGINE_REGISTRY", "biointel.engine-registry.v3", engines, {"engines": len(engines), "bundled": 0})
    _write_registry(
        output,
        "MODEL_REGISTRY",
        "biointel.model-registry.v3",
        models,
        {
            "models": len(models),
            "synthetic_demo": sum(row["synthetic_demo"] for row in models),
            "default_scientific_inference_allowed": sum(row["default_scientific_inference_allowed"] for row in models),
        },
    )
    _write_registry(output, "REFERENCE_DATABASE_REGISTRY", "biointel.reference-registry.v3", references, {"references": len(references), "bundled": 0})
    (output / "MODULE_STATUS_REPORT.md").write_text(_module_status_markdown(modules, module_summary), encoding="utf-8")
    report = {
        "schema": "biointel.ultimate-registry-export.v1",
        "generated_at_utc": _now(),
        "output": str(output),
        "module_integrity": module_summary,
        "counts": {"modules": len(modules), "engines": len(engines), "models": len(models), "references": len(references)},
        "status": "passed",
    }
    (output / "REGISTRY_EXPORT_REPORT.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--output", default="release/ultimate_registry")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    output = Path(args.output)
    if not output.is_absolute():
        output = root / output
    report = export_all(root, output.resolve())
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
