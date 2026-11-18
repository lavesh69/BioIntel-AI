from __future__ import annotations

import ast
import hashlib
import json
import sqlite3
import tempfile
from pathlib import Path

import pandas as pd

from biointel.nextgen.catalog import MODULE_BY_KEY
from biointel.nextgen.scientific import analyse, demo_frame, normalise
from biointel.nextgen.visual_intelligence_v132 import (
    MODULE_VISUALS,
    VISUAL_CATALOG,
    build_visual_artifact,
    database_summary,
    save_bookmark,
    save_workspace_layout,
)
from biointel.ui.navigation import catalogue_integrity

ROOT = Path(__file__).resolve().parents[1]
MODULE_KEYS = (
    "digital_pathology_foundation", "long_read_epigenome", "single_cell_long_read_isoforms",
    "biomedical_foundation_model_hub", "amr_surveillance", "spatial_medicine_tme",
    "gene_therapy_vector", "cell_therapy_cart", "federated_biomedical_ai",
    "clinical_biomarker_survival", "protein_ligand_codesign", "pangenome_population_medicine",
    "pharmacovigilance_intelligence", "synthetic_cohort_trial", "autonomous_lab_planner",
)


def add(checks: list[dict[str, object]], name: str, passed: bool, detail: str) -> None:
    checks.append({"name": name, "passed": bool(passed), "detail": detail})


def main() -> int:
    checks: list[dict[str, object]] = []
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    add(checks, "Version", version == "13.2.0", version)
    add(checks, "Step 132 release", (ROOT / "STEP132_RELEASE.json").is_file(), "release contract")
    add(checks, "Step 132 config", (ROOT / "config/step132_visual_intelligence.json").is_file(), "configuration")
    add(checks, "Central visual studio", (ROOT / "pages/196_Multi_Scale_Scientific_Visual_Intelligence_Studio.py").is_file(), "page 196")
    add(checks, "Visual catalog", len(VISUAL_CATALOG) == 30 and len({item.key for item in VISUAL_CATALOG}) == 30, f"visuals={len(VISUAL_CATALOG)}")
    add(checks, "Fifteen-module integration", set(MODULE_KEYS).issubset(MODULE_VISUALS), f"modules={len(MODULE_VISUALS)}")
    add(checks, "Navigation", bool(catalogue_integrity(ROOT).get("healthy")), "catalogue healthy")

    module = MODULE_BY_KEY["protein_ligand_codesign"]
    data = normalise(demo_frame(module, 90), module)
    result, _, secondary, extras = analyse(data, module, 0.70)
    visual_errors: list[str] = []
    for visual in VISUAL_CATALOG:
        try:
            figure, source, interpretation, limitation = build_visual_artifact(
                visual.key, module_key=module.key, data=data, result=result, secondary=secondary, extras=extras
            )
            figure.to_json() if figure is not None else None
            if not interpretation or not limitation or not isinstance(source, pd.DataFrame):
                visual_errors.append(f"{visual.key}: incomplete artifact")
        except Exception as exc:
            visual_errors.append(f"{visual.key}: {type(exc).__name__}: {exc}")
    add(checks, "Thirty visual runtime artifacts", not visual_errors, f"errors={len(visual_errors)}")

    module_errors: list[str] = []
    for module_key in MODULE_KEYS:
        module = MODULE_BY_KEY[module_key]
        data = normalise(demo_frame(module, 60), module)
        result, _, secondary, extras = analyse(data, module, 0.70)
        for visual_key in MODULE_VISUALS[module_key]:
            try:
                figure, source, _, _ = build_visual_artifact(
                    visual_key, module_key=module_key, data=data, result=result, secondary=secondary, extras=extras
                )
                figure.to_json() if figure is not None else None
                if source.empty:
                    module_errors.append(f"{module_key}/{visual_key}: empty")
            except Exception as exc:
                module_errors.append(f"{module_key}/{visual_key}: {exc}")
    add(checks, "Curated module visual runtime", not module_errors, f"errors={len(module_errors)}")

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        db = root / "visual.sqlite3"
        bookmark = save_bookmark(root, module_key="amr_surveillance", visual_key="experiment_replay", title="Replay", state={"zoom": 1}, path=db)
        layout = save_workspace_layout(root, module_key="amr_surveillance", name="Layout", monitors=[{"monitor": 1, "workspace": "Raw data"}], path=db)
        with sqlite3.connect(db) as connection:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        summary = database_summary(root, path=db)
        add(checks, "Step 132 persistence", bookmark.startswith("VBM-") and layout.startswith("LAY-") and summary["bookmarks"] == 1, str(summary))
        add(checks, "Step 132 database integrity", integrity == "ok", integrity)

    syntax_failures: list[str] = []
    python_files = list(ROOT.rglob("*.py"))
    for path in python_files:
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except Exception as exc:
            syntax_failures.append(f"{path.relative_to(ROOT)}: {exc}")
    add(checks, "Python syntax", not syntax_failures, f"files={len(python_files)}")

    locked = {
        "pages/6_DTI_Predictor.py": "84b3ecec1356b7239a057459210af4cd130c57c08dd9449b7239d1fe5954e0cc",
        "pages/74_DTI_Validation_Evidence_Center.py": "a700a8a21649b49cf0e3a1521d2afad45039b83b767c2fe730b93fee7d4f7f11",
        "pages/109_Lab_Instrument_Import_Center.py": "22b5aba5bfea37bb1ef330ed7cca3773467463f883189602d96a0151311c8f70",
        "pages/126_LIMS_ELN_and_Sample_Chain_of_Custody_Hub.py": "eadaef1a283a5fa11ce6b243aa561508ba9ceba9f6fdcc207f4853ccf7d86905",
        "pages/157_Instrument_Integration_Hub_2.py": "cf3a5f94756def0007dbff31184ec276d90b03fc6d6e1ca792c87189e5ab7d6d",
    }
    locked_ok = all(hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == digest for relative, digest in locked.items())
    add(checks, "Locked pages", locked_ok, "5 protected pages byte-identical")

    report = {
        "schema": "biointel.step132.verification.v1",
        "version": version,
        "checks": checks,
        "passed": sum(1 for item in checks if item["passed"]),
        "total": len(checks),
        "healthy": all(bool(item["passed"]) for item in checks),
        "python_files": len(python_files),
        "syntax_failures": syntax_failures,
        "visual_errors": visual_errors,
        "module_errors": module_errors,
    }
    target = ROOT / "reports/step132_visual_intelligence_verification.json"
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
