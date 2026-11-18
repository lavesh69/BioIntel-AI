from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from biointel.runtime_paths import user_data_root
from .catalog import PROFILES, TARGET_MODULES, PortfolioDemoProfile

try:
    from biointel.nextgen.catalog import MODULE_BY_KEY
    from biointel.nextgen.scientific import analyse, demo_frame, normalise
except Exception:  # pragma: no cover
    MODULE_BY_KEY = {}
    analyse = demo_frame = normalise = None


ALIASES = {
    "autonomous_laboratory_planner": "autonomous_lab_planner",
    "pharmacovigilance": "pharmacovigilance_intelligence",
    "model_registry_ml_lifecycle": "model_registry_v2",
}


def _digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _scientific_generic(profile: PortfolioDemoProfile, n: int = 120) -> pd.DataFrame:
    title = profile.title.lower()
    idx = np.arange(n)
    site = np.where(idx % 2 == 0, "DEMO-SITE-A", "DEMO-SITE-B")
    batch = np.array([f"DEMO-B{(i % 4) + 1}" for i in idx])
    group = np.where(idx % 2 == 0, "control", "case")
    score = np.clip(0.15 + (idx % 20) / 22.0, 0, 0.99)

    if any(token in title for token in ("genom", "variant", "amr", "pangenome", "long-read", "virology", "microbiome")):
        return pd.DataFrame({
            "sample_id": [f"DEMO-S{i:03d}" for i in idx], "site_id": site, "batch_id": batch,
            "chromosome": [f"chr{(i % 22) + 1}" for i in idx], "position": 100000 + idx * 137,
            "reference": np.where(idx % 3 == 0, "A", "C"), "alternate": np.where(idx % 3 == 0, "G", "T"),
            "depth": 30 + idx % 70, "quality": 40 + idx % 50, "group": group,
            "prediction": score, "label": (idx % 2).astype(int), "synthetic_demo": True,
        })
    if any(token in title for token in ("protein", "antibody", "enzyme", "ligand", "vaccine")):
        alphabet = "ACDEFGHIKLMNPQRSTVWY"
        return pd.DataFrame({
            "entity_id": [f"DEMO-P{i:03d}" for i in idx], "site_id": site, "batch_id": batch,
            "sequence": ["M" + "".join(alphabet[(i + j) % len(alphabet)] for j in range(24)) for i in idx],
            "candidate_score": score, "confidence": np.clip(score + 0.05, 0, 1),
            "measured_proxy": np.round(5 + 2 * score + (idx % 5) * 0.02, 3),
            "group": group, "label": (idx % 2).astype(int), "synthetic_demo": True,
        })
    if any(token in title for token in ("image", "pathology", "microscopy", "phenotypic", "organoid", "spatial")):
        return pd.DataFrame({
            "image_id": [f"DEMO-IMG{i:03d}" for i in idx], "patient_id": [f"DEMO-PAT{i // 4:03d}" for i in idx],
            "site_id": site, "scanner_id": np.where(idx % 2 == 0, "DEMO-SC-A", "DEMO-SC-B"),
            "region_id": [f"R{i % 8}" for i in idx], "object_count": 50 + idx % 200,
            "signal": np.round(score * 100, 3), "confidence": np.clip(score + 0.04, 0, 1),
            "group": group, "label": (idx % 2).astype(int), "synthetic_demo": True,
        })
    if any(token in title for token in ("clinical", "trial", "pharma", "survival", "therapy", "pharmacovigilance")):
        return pd.DataFrame({
            "patient_id": [f"DEMO-PAT{i:03d}" for i in idx], "site_id": site, "batch_id": batch,
            "endpoint": np.where(idx % 2 == 0, "response", "non_response"),
            "time_days": 30 + idx * 3, "event": (idx % 3 == 0).astype(int),
            "prediction": score, "label": (idx % 2).astype(int), "subgroup": np.where(idx % 3 == 0, "A", "B"),
            "quality_score": np.round(0.85 + (idx % 10) / 100, 3), "synthetic_demo": True,
        })
    if any(token in title for token in ("omics", "single-cell", "cell atlas", "epigen", "glycom", "metabol", "flow cytometry")):
        return pd.DataFrame({
            "sample_id": [f"DEMO-S{i:03d}" for i in idx], "feature_id": [f"DEMO-F{i % 40:03d}" for i in idx],
            "modality": np.where(idx % 3 == 0, "RNA", np.where(idx % 3 == 1, "PROTEIN", "METABOLITE")),
            "abundance": np.round(1.0 + 3 * score, 4), "site_id": site, "batch_id": batch,
            "condition": group, "quality_score": np.round(0.88 + (idx % 8) / 100, 3),
            "prediction": score, "label": (idx % 2).astype(int), "synthetic_demo": True,
        })
    return pd.DataFrame({
        "sample_id": [f"DEMO-S{i:03d}" for i in idx], "site_id": site, "batch_id": batch,
        "feature_id": [f"DEMO-F{i % 30:03d}" for i in idx], "value": np.round(1 + score * 5, 4),
        "group": group, "prediction": score, "label": (idx % 2).astype(int),
        "quality_score": np.round(0.9 + (idx % 5) / 100, 3), "synthetic_demo": True,
    })


def _platform_frame(profile: PortfolioDemoProfile, n: int = 120) -> pd.DataFrame:
    idx = np.arange(n)
    return pd.DataFrame({
        "event_id": [f"DEMO-E{i:04d}" for i in idx],
        "actor": np.where(idx % 2 == 0, "demo-operator", "demo-reviewer"),
        "operation": [profile.workflow[i % max(1, len(profile.workflow))] if profile.workflow else "validate" for i in idx],
        "resource": [f"DEMO-R{i % 15:02d}" for i in idx],
        "status": np.where(idx % 10 == 0, "recovered", "completed"),
        "latency_ms": 20 + idx % 180,
        "retry_count": np.where(idx % 10 == 0, 1, 0),
        "checksum_valid": True,
        "expected_outcome": "pass",
        "synthetic_demo": True,
    })


def _native_frame(profile: PortfolioDemoProfile) -> tuple[pd.DataFrame | None, str, dict[str, Any], pd.DataFrame | None]:
    key = ALIASES.get(profile.module_key, profile.module_key)
    module = MODULE_BY_KEY.get(key) if MODULE_BY_KEY else None
    if module is None or demo_frame is None:
        return None, "module-specific-fixture", {}, None
    try:
        frame = demo_frame(module, 120)
    except Exception as exc:
        return None, "module-specific-fixture", {"native_input_error": str(exc)}, None
    try:
        data = normalise(frame, module)
        result, summary, _secondary, _extras = analyse(data, module, 0.7)
        return frame, "native-analysis-executed", dict(summary), result.head(250)
    except Exception as exc:
        return frame, "native-input-generated", {"native_analysis_error": str(exc)}, None


def _negative_cases(profile: PortfolioDemoProfile) -> pd.DataFrame:
    cases = [
        ("golden", "valid deterministic demo input", "pass"),
        ("missing_required_field", "remove one mandatory field", "fail-safe"),
        ("duplicate_identity", "duplicate sample/entity identifier", "fail-safe"),
        ("invalid_numeric_range", "inject impossible measurement", "fail-safe"),
        ("corrupt_checksum", "alter a registered file after hashing", "fail-safe"),
        ("cross_split_leakage", "repeat an entity across train and external validation", "fail-safe"),
    ]
    return pd.DataFrame(cases, columns=["case_id", "scenario", "expected_outcome"])


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def build_portfolio_demos(root: str | Path) -> dict[str, Any]:
    project = Path(root).resolve()
    base = user_data_root(project) / "step183" / "module_demos"
    base.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    native_executed = native_input = generic = 0

    for module_key in TARGET_MODULES:
        profile = PROFILES[module_key]
        folder = base / module_key
        folder.mkdir(parents=True, exist_ok=True)
        native, execution_mode, summary, result = _native_frame(profile)
        if native is not None:
            frame = native.copy()
            frame["synthetic_demo"] = True
        elif profile.module_class == "platform-core":
            frame = _platform_frame(profile)
        else:
            frame = _scientific_generic(profile)

        if execution_mode == "native-analysis-executed":
            native_executed += 1
        elif execution_mode == "native-input-generated":
            native_input += 1
        else:
            generic += 1

        input_path = folder / "demo_input.csv"
        frame.to_csv(input_path, index=False)
        negative_path = folder / "demo_negative_cases.csv"
        _negative_cases(profile).to_csv(negative_path, index=False)
        expected_path = folder / "demo_expected_outputs.json"
        _write_json(expected_path, {
            "schema": "biointel.step183.expected-outputs.v1",
            "module_key": module_key,
            "required_outputs": list(profile.required_outputs),
            "workflow": list(profile.workflow),
            "quality_gates_exercised": list(profile.quality_gates[:8]),
            "native_summary": summary,
            "synthetic_demo": True,
            "real_external_evidence": False,
            "controlled_release_eligible": False,
        })
        result_path = None
        if result is not None and not result.empty:
            result_path = folder / "demo_result_preview.csv"
            result.to_csv(result_path, index=False)
        readme_path = folder / "README_DEMO.md"
        readme_path.write_text(
            f"# {profile.title} — synthetic demo bundle\n\n"
            "This bundle is deterministic and synthetic. It can test imports, schema handling, analysis/UI paths, negative-case rejection, charts and exports.\n\n"
            f"- Execution mode: `{execution_mode}`\n"
            f"- Demo operational rating: **{profile.demo_operational_rating:.2f}/10**\n"
            f"- Baseline real-world practical rating remains: **{profile.baseline_practical_rating:.2f}/10**\n"
            "- Real external evidence: **not supplied**\n"
            "- Controlled scientific release: **not eligible**\n\n"
            f"Boundary: {profile.boundary}\n",
            encoding="utf-8",
        )
        files = [input_path, negative_path, expected_path, readme_path]
        if result_path is not None:
            files.append(result_path)
        manifest = {
            "schema": "biointel.step183.portfolio-demo-manifest.v1",
            "module_key": module_key,
            "module_title": profile.title,
            "source_step": profile.source_step,
            "execution_mode": execution_mode,
            "synthetic_or_demo": True,
            "real_external_evidence": False,
            "controlled_release_eligible": False,
            "internal_software_rating": 10.0,
            "baseline_practical_rating": profile.baseline_practical_rating,
            "demo_operational_rating": profile.demo_operational_rating,
            "demo_improvement": profile.demo_improvement,
            "files": [
                {"path": item.name, "sha256": _digest(item), "size_bytes": item.stat().st_size}
                for item in files
            ],
        }
        _write_json(folder / "demo_manifest.json", manifest)
        rows.append({
            "module_key": module_key,
            "module_title": profile.title,
            "source_step": profile.source_step,
            "execution_mode": execution_mode,
            "records": len(frame),
            "baseline_practical_rating": profile.baseline_practical_rating,
            "demo_operational_rating": profile.demo_operational_rating,
            "demo_improvement": profile.demo_improvement,
            "real_external_rating_changed": False,
            "controlled_release_eligible": False,
            "path": str(folder),
        })

    index = pd.DataFrame(rows)
    data_root = project / "data" / "step183"
    data_root.mkdir(parents=True, exist_ok=True)
    index.to_csv(data_root / "portfolio_demo_index.csv", index=False)
    _write_json(data_root / "portfolio_demo_index.json", rows)
    result = {
        "schema": "biointel.step183.portfolio-demo-build.v1",
        "modules": len(rows),
        "demo_ready_target": len(rows),
        "native_analysis_executed": native_executed,
        "native_input_generated": native_input,
        "module_specific_fixture": generic,
        "real_external_evidence_modules": 0,
        "controlled_release_eligible_modules": 0,
        "base": str(base),
    }
    _write_json(project / "STEP183_BUILD_RESULT.json", result)
    return result


__all__ = ["build_portfolio_demos"]
