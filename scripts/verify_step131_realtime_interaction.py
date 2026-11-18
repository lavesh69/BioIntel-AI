from __future__ import annotations

import ast
import hashlib
import io
import json
import tempfile
import zipfile
from pathlib import Path

import pandas as pd

from biointel.nextgen.biomedical_expansion import NEW_BIOMEDICAL_KEYS
from biointel.nextgen.interaction_v131 import (
    build_figure_layout_bundle,
    create_review_thread,
    list_review_threads,
    progressive_sample,
    record_selection,
    uncertainty_profile,
)
from biointel.nextgen.intelligence import connect
from biointel.ui.navigation import catalogue_integrity

ROOT = Path(__file__).resolve().parents[1]


def add(checks: list[dict[str, object]], name: str, passed: bool, detail: str) -> None:
    checks.append({"name": name, "passed": bool(passed), "detail": detail})


def main() -> int:
    checks: list[dict[str, object]] = []
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    add(checks, "Version", version == "13.2.0", f"VERSION={version}")
    add(checks, "New biomedical modules", len(NEW_BIOMEDICAL_KEYS) == 15, f"modules={len(NEW_BIOMEDICAL_KEYS)}")
    add(checks, "Central interaction page", (ROOT / "pages/195_Real_Time_Scientific_Canvas_Collaboration_Center.py").is_file(), "page 195")
    add(checks, "Step 131 config", (ROOT / "config/step131_realtime_interaction_stability.json").is_file(), "configuration present")
    add(checks, "Step 131 release", (ROOT / "STEP131_RELEASE.json").is_file(), "release contract present")

    renderer = (ROOT / "src/biointel/ui/nextgen_intelligence.py").read_text(encoding="utf-8")
    workspace = (ROOT / "src/biointel/ui/reactive_scientific_workspace.py").read_text(encoding="utf-8")
    components = (ROOT / "src/biointel/ui/components.py").read_text(encoding="utf-8")
    visuals = (ROOT / "src/biointel/ui/scientific_visuals.py").read_text(encoding="utf-8")
    add(checks, "All-module integration", "render_reactive_scientific_workspace" in renderer, "shared intelligence tab")
    add(checks, "No-rerun canvas", "st.html" in workspace and "unsafe_allow_javascript=True" in workspace and "Drag a rectangle" in workspace, "offline browser-side interaction")
    add(checks, "Visual provenance and collaboration", "render_point_provenance" in workspace and "render_collaborative_review" in workspace, "integrated")
    add(checks, "Publication layout", "render_figure_layout_editor" in workspace, "journal presets and editable SVG bundle")
    add(checks, "WebGL and LOD", '"render_mode": "webgl"' in visuals and "progressive_sample" in visuals, "scatter acceleration")
    add(checks, "Visual fingerprinting", "save_visual_fingerprint" in components, "render-spec regression fingerprints")
    add(checks, "Navigation", bool(catalogue_integrity(ROOT).get("healthy")), "catalogue healthy")

    frame = pd.DataFrame({
        "candidate": [f"C{i}" for i in range(10000)],
        "score": list(range(10000)),
        "effect": [1.0] * 10000,
        "effect_ci_low": [0.5] * 10000,
        "effect_ci_high": [1.5] * 10000,
    })
    sampled, manifest = progressive_sample(frame, limit=500, selected_values=["C9999"])
    add(checks, "Progressive rendering", len(sampled) <= 500 and "C9999" in set(sampled["candidate"]), f"{len(sampled)}/{manifest.source_rows}")
    profile = uncertainty_profile(frame.head(100))
    add(checks, "Uncertainty audit", not profile.empty and int(profile.iloc[0]["valid_intervals"]) == 100, "interval integrity")

    with tempfile.TemporaryDirectory() as directory:
        temp = Path(directory)
        db = temp / "step131.sqlite3"
        record_selection(project_root=temp, module_key="amr_surveillance", chart_key="map", column_name="isolate", values=["I1"], path=db)
        thread = create_review_thread(project_root=temp, module_key="amr_surveillance", entity_id="I1", title="Review", created_by="tester", path=db)
        with connect(temp, path=db) as connection:
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        required = {"selection_history", "visual_provenance", "review_threads", "review_comments", "figure_layouts", "viewer_sync_state", "visual_fingerprints"}
        add(checks, "Step 131 database schema", required.issubset(tables), f"tables={len(tables)}")
        add(checks, "Step 131 database integrity", integrity == "ok" and thread.startswith("THR-"), integrity)
        add(checks, "Review persistence", len(list_review_threads(temp, "amr_surveillance", path=db)) == 1, "thread persisted")

    bundle = build_figure_layout_bundle(
        module_key="clinical_biomarker_survival", layout_name="Validation figure", preset="Nature two-column",
        panels=[{"title": "Panel", "values": [1, 2, 3]}], boundary="Research use only",
    )
    with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
        names = set(archive.namelist())
    add(checks, "Figure layout bundle", {"figure/figure_layout.svg", "manifest.json"}.issubset(names), "editable SVG bundle")

    syntax_failures: list[str] = []
    python_files = list(ROOT.rglob("*.py"))
    for path in python_files:
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except Exception as exc:
            syntax_failures.append(f"{path.relative_to(ROOT)}: {exc}")
    add(checks, "Python syntax", not syntax_failures, f"{len(python_files)} files")

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
        "schema": "biointel.step131.verification.v1",
        "version": version,
        "checks": checks,
        "passed": sum(1 for item in checks if item["passed"]),
        "total": len(checks),
        "healthy": all(bool(item["passed"]) for item in checks),
        "python_files": len(python_files),
        "syntax_failures": syntax_failures,
    }
    target = ROOT / "reports/step131_realtime_interaction_verification.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
