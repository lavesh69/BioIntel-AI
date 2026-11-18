from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from biointel.ui.operational_canvas import render_operational_canvas

from .catalog import PROFILES
from .generator import module_folder
from .qualification import validate_module


def _root() -> Path:
    return Path(__file__).resolve().parents[3]


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def render_step189_universal_platform(module_key: str, *, expanded: bool = False) -> None:
    if module_key not in PROFILES:
        return
    root = _root()
    profile = PROFILES[module_key]
    result = validate_module(root, module_key)
    folder = module_folder(root, module_key)
    with st.expander("Step 189 · Universal Production Platform & Category Adapter", expanded=expanded):
        a, b, c, d = st.columns(4)
        a.metric("Internal/demo rating", f"{result.rating:.2f}/10")
        b.metric("Platform controls", f"{result.dimensions_passed}/{result.dimensions_total}")
        c.metric("Category", profile.category.replace("_", " ").title())
        d.metric("Controlled release", "PENDING")
        if result.qualified_10_of_10:
            st.success("Project/sample registry, engine/reference readiness, preflight, durable jobs, provenance, handoffs, reports, monitoring, review and diagnostics are operational.")
        else:
            st.error("Step 189 blockers: " + ", ".join(result.blockers))
        st.caption("Detected real tools are used when available. Missing tools use a clearly labelled safe demo adapter. Synthetic references and demos never count as licensed production data or external scientific evidence.")

        tabs = st.tabs(["Preflight", "Project & Samples", "Engines & References", "Jobs & Recovery", "Results & Handoff", "Reports", "Monitoring", "Review & Diagnostics", "Qualification"])
        with tabs[0]:
            render_operational_canvas(
                title="Preflight canvas",
                subtitle="Local readiness checks and safe launch conditions.",
                payload=_read_json(folder / "preflight.json"),
                stages=("Inspect", "Validate", "Resolve blockers", "Ready"),
                key=f"s189_preflight_{module_key}",
            )
            st.dataframe(pd.read_csv(folder / "negative_security_cases.csv"), width="stretch", hide_index=True)
        with tabs[1]:
            render_operational_canvas(
                title="Project and samples canvas",
                subtitle="Project identity, registered inputs and local provenance without exposing host paths.",
                payload=_read_json(folder / "project_snapshot.json"),
                stages=("Register project", "Attach samples", "Verify identity", "Ready for analysis"),
                key=f"s189_project_{module_key}",
            )
            zip_path = folder / "portable_project.zip"
            zip_bytes = zip_path.read_bytes() if zip_path.exists() else b"PK\x05\x06" + b"\x00" * 18
            st.download_button("Download portable project", zip_bytes, f"{module_key}_portable_project.zip", "application/zip", key=f"s189_project_{module_key}")
        with tabs[2]:
            st.markdown("#### Engine readiness")
            st.dataframe(pd.read_csv(folder / "engine_status.csv"), width="stretch", hide_index=True)
            st.markdown("#### Reference readiness")
            st.dataframe(pd.read_csv(folder / "reference_status.csv"), width="stretch", hide_index=True)
        with tabs[3]:
            render_operational_canvas(
                title="Job and recovery canvas",
                subtitle="Run status, checkpoint state and recovery facts are presented as an operational workflow.",
                payload=_read_json(folder / "job_record.json"),
                stages=("Queued", "Validate input", "Analyse", "Checkpoint & handoff"),
                key=f"s189_job_{module_key}",
            )
            st.dataframe(pd.read_csv(folder / "performance_benchmark.csv"), width="stretch", hide_index=True)
        with tabs[4]:
            results = pd.read_csv(folder / "analysis_results.csv")
            st.dataframe(results.head(500), width="stretch", hide_index=True)
            render_operational_canvas(
                title="Results handoff canvas",
                subtitle="Export, downstream handoff and result-integrity facts.",
                payload=_read_json(folder / "handoff_contract.json"),
                stages=("Analyse", "Validate", "Package", "Handoff"),
                key=f"s189_handoff_{module_key}",
            )
            st.download_button("Download results", results.to_csv(index=False), f"{module_key}_step189_results.csv", "text/csv", key=f"s189_results_{module_key}")
        with tabs[5]:
            render_operational_canvas(
                title="Report package canvas",
                subtitle="Generated report files and reproducibility package information.",
                payload=_read_json(folder / "report_files.json"),
                stages=("Collect", "Render", "Sign", "Export"),
                key=f"s189_reports_{module_key}",
            )
            st.download_button("Download complete report bundle", (folder / "reports" / "report_bundle.zip").read_bytes(), f"{module_key}_step189_reports.zip", "application/zip", key=f"s189_report_{module_key}")
            st.markdown((folder / "reports" / "report.md").read_text(encoding="utf-8"))
        with tabs[6]:
            render_operational_canvas(
                title="Monitoring canvas",
                subtitle="Service health, performance and local operational monitoring summary.",
                payload=_read_json(folder / "monitoring_snapshot.json"),
                stages=("Observe", "Measure", "Detect", "Respond"),
                key=f"s189_monitoring_{module_key}",
            )
            render_operational_canvas(
                title="Provenance verification canvas",
                subtitle="Input/output identity and integrity verification summary.",
                payload=_read_json(folder / "provenance_verification.json"),
                stages=("Collect hashes", "Compare", "Verify", "Record"),
                key=f"s189_provenance_{module_key}",
            )
        with tabs[7]:
            render_operational_canvas(
                title="Review status canvas",
                subtitle="Review ownership, decision state and outstanding checks.",
                payload=_read_json(folder / "review_status.json"),
                stages=("Prepare", "Review", "Resolve", "Record"),
                key=f"s189_review_{module_key}",
            )
            render_operational_canvas(
                title="Diagnostic canvas",
                subtitle="Redacted diagnostic summary; technical details are collapsible for support.",
                payload=_read_json(folder / "diagnostic_example.json"),
                stages=("Detect", "Explain", "Recover", "Support"),
                key=f"s189_diagnostic_{module_key}",
            )
            st.download_button("Download redacted support bundle", (folder / "redacted_support_bundle.zip").read_bytes(), f"{module_key}_support_bundle.zip", "application/zip", key=f"s189_support_{module_key}")
        with tabs[8]:
            st.dataframe(pd.read_csv(folder / "capability_matrix.csv"), width="stretch", hide_index=True)
            render_operational_canvas(
                title="Qualification canvas",
                subtitle="Internal capability checks; controlled release remains evidence-gated.",
                payload=_read_json(folder / "qualification_manifest.json"),
                stages=("Assess", "Verify", "Review", "Gate"),
                key=f"s189_qualification_{module_key}",
            )
            render_operational_canvas(
                title="Release-boundary canvas",
                subtitle="What the local software does and what external evidence is still required.",
                payload=_read_json(folder / "release_boundary.json"),
                stages=("Local capability", "Evidence gap", "Independent review", "Controlled release"),
                key=f"s189_boundary_{module_key}",
            )


__all__ = ["render_step189_universal_platform"]
