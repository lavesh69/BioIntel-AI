from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
import zipfile

import pandas as pd
import streamlit as st

from biointel.ui.operational_canvas import render_operational_canvas

from .catalog import PROFILES, STANDARD_TABS
from .engine import bundle_bytes, load_demo_input, module_folder, run_native_demo
from .validators import validate_module


def _root() -> Path:
    return Path(__file__).resolve().parents[3]


def _json(folder: Path, name: str) -> dict:
    return json.loads((folder / name).read_text(encoding="utf-8"))


def render_step188_major_module_standard(module_key: str, *, expanded: bool = False) -> None:
    if module_key not in PROFILES:
        return
    root = _root()
    profile = PROFILES[module_key]
    result = validate_module(root, module_key)
    folder = Path(result.path)
    with st.expander("Step 188 · Universal Major Module Standard (12-tab lifecycle)", expanded=expanded):
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Internal/demo rating", f"{result.rating:.2f}/10")
        c2.metric("Compulsory dimensions", f"{result.dimensions_passed}/{result.dimensions_total}")
        c3.metric("Lifecycle tabs", f"{result.tabs_passed}/{result.tabs_total}")
        c4.metric("Controlled release", "PENDING")
        if result.qualified_10_of_10:
            st.success("Module lifecycle, QC, deterministic analysis, validation, interpretation, reporting, history, recovery, security and qualification contracts are complete.")
        else:
            st.error("Step 188 blockers: " + ", ".join(result.blockers))
        st.caption("10/10 is internal/demo-operational assurance. Real wet-lab, clinical, instrument, licensed-data and independent-site evidence remains a separate release requirement.")

        tabs = st.tabs(list(STANDARD_TABS))
        with tabs[0]:
            render_operational_canvas(
                title=profile.title,
                subtitle="Module purpose, source and lifecycle at a glance.",
                payload={
                    "module_key": module_key,
                    "module_class": profile.module_class,
                    "source_step": profile.source_step,
                    "page": profile.page,
                },
                stages=("Prepare", "Quality control", "Analysis", "Review & export"),
                key=f"s188_overview_{module_key}",
            )
            st.markdown("**Intended workflow**")
            st.dataframe(pd.read_csv(folder / "workflow_stages.csv"), width="stretch", hide_index=True)
            st.info(profile.boundary)
        with tabs[1]:
            demo = pd.read_csv(folder / "demo_input.csv")
            st.dataframe(demo.head(100), width="stretch", hide_index=True)
            if st.button("Run deterministic Step 188 demo", key=f"s188_run_{module_key}"):
                output, summary = run_native_demo(demo, module_key)
                st.success("Deterministic demo completed")
                render_operational_canvas(
                    title="Demo run canvas",
                    subtitle="Deterministic demonstration output; not external scientific evidence.",
                    payload=summary,
                    stages=("Validate input", "Run local adapter", "Check output", "Record provenance"),
                    key=f"s188_demo_canvas_{module_key}",
                )
                st.dataframe(output.head(100), width="stretch", hide_index=True)
            st.download_button("Download demo input", demo.to_csv(index=False), f"{module_key}_step188_demo_input.csv", "text/csv", key=f"s188_demo_{module_key}")
        with tabs[2]:
            st.dataframe(pd.read_csv(folder / "input_schema.csv"), width="stretch", hide_index=True)
            render_operational_canvas(
                title="Integration contract canvas",
                subtitle="Required inputs, integration boundaries and reusable handoff facts.",
                payload=_json(folder, "integration_contract.json"),
                stages=("Validate", "Map", "Run", "Handoff"),
                key=f"s188_integration_{module_key}",
            )
        with tabs[3]:
            render_operational_canvas(
                title="Quality-control canvas",
                subtitle="Summary metrics are shown first; technical detail stays collapsible.",
                payload=_json(folder, "qc_summary.json"),
                stages=("Inspect", "Validate", "Flag", "Release or block"),
                key=f"s188_qc_{module_key}",
            )
            st.dataframe(pd.read_csv(folder / "qc_checks.csv"), width="stretch", hide_index=True)
            st.dataframe(pd.read_csv(folder / "sample_qc.csv").head(200), width="stretch", hide_index=True)
        with tabs[4]:
            st.dataframe(pd.read_csv(folder / "workflow_stages.csv"), width="stretch", hide_index=True)
            render_operational_canvas(
                title="Recovery canvas",
                subtitle="Checkpoint, retry and recovery information without a raw JSON wall.",
                payload=_json(folder, "recovery_contract.json"),
                stages=("Queue", "Checkpoint", "Recover", "Complete"),
                key=f"s188_recovery_{module_key}",
            )
            render_operational_canvas(
                title="Analysis canvas",
                subtitle="Local analysis summary and result integrity facts.",
                payload=_json(folder, "analysis_summary.json"),
                stages=("Input", "Analysis", "Quality gate", "Result"),
                key=f"s188_analysis_{module_key}",
            )
        with tabs[5]:
            results = pd.read_csv(folder / "analysis_results.csv")
            st.dataframe(results.head(500), width="stretch", hide_index=True)
            st.download_button("Download results CSV", results.to_csv(index=False), f"{module_key}_step188_results.csv", "text/csv", key=f"s188_results_{module_key}")
        with tabs[6]:
            visuals = pd.read_csv(folder / "visual_catalog.csv")
            st.dataframe(visuals, width="stretch", hide_index=True)
            results = pd.read_csv(folder / "analysis_results.csv")
            numeric = list(results.select_dtypes(include=["number"]).columns)
            if numeric:
                st.bar_chart(results[numeric[:2]].head(100))
                st.line_chart(results[numeric[:2]].head(100))
            st.dataframe(results.head(100), width="stretch", hide_index=True)
        with tabs[7]:
            st.dataframe(pd.read_csv(folder / "validation_matrix.csv"), width="stretch", hide_index=True)
            st.dataframe(pd.read_csv(folder / "negative_security_cases.csv"), width="stretch", hide_index=True)
            st.dataframe(pd.read_csv(folder / "repeatability.csv"), width="stretch", hide_index=True)
            st.dataframe(pd.read_csv(folder / "performance_benchmark.csv"), width="stretch", hide_index=True)
        with tabs[8]:
            st.markdown((folder / "interpretation.md").read_text(encoding="utf-8"))
        with tabs[9]:
            report = (folder / "reproducible_report.md").read_text(encoding="utf-8")
            st.markdown(report)
            a, b = st.columns(2)
            a.download_button("Download report", report, f"{module_key}_step188_report.md", "text/markdown", key=f"s188_report_{module_key}")
            b.download_button("Download environment manifest", json.dumps(_json(folder, "environment_manifest.json"), indent=2), f"{module_key}_environment.json", "application/json", key=f"s188_env_{module_key}")
        with tabs[10]:
            st.dataframe(pd.read_csv(folder / "run_history.csv"), width="stretch", hide_index=True)
            st.info("Rerun and run-comparison contracts are active. Input/output hashes and version snapshots are retained.")
        with tabs[11]:
            manifest = _json(folder, "qualification_manifest.json")
            st.dataframe(pd.DataFrame(manifest["dimensions"]), width="stretch", hide_index=True)
            render_operational_canvas(
                title="Security and governance canvas",
                subtitle="Software controls only; this does not claim external certification.",
                payload=_json(folder, "security_governance.json"),
                stages=("Protect", "Review", "Audit", "Escalate"),
                key=f"s188_security_{module_key}",
            )
            render_operational_canvas(
                title="Accessibility canvas",
                subtitle="Keyboard, contrast and local desktop support facts.",
                payload=_json(folder, "accessibility_contract.json"),
                stages=("Navigate", "Read", "Operate", "Recover"),
                key=f"s188_accessibility_{module_key}",
            )
            a, b = st.columns(2)
            a.download_button("Download complete Step 188 bundle", bundle_bytes(folder), f"{module_key}_step188_major_module_bundle.zip", "application/zip", key=f"s188_bundle_{module_key}")
            b.download_button("Download qualification manifest", json.dumps(manifest, indent=2), f"{module_key}_step188_qualification.json", "application/json", key=f"s188_qualification_{module_key}")


__all__ = ["render_step188_major_module_standard"]
