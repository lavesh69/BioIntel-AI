from __future__ import annotations

from dataclasses import asdict
import json
import importlib.util
import shutil
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from biointel.ui.components import metric_cards, smart_dataframe, smart_json
from biointel.ui.theme import section_title
from biointel.stability_v159 import assess_dataframe_admission, capture_resource_snapshot
from biointel.quality_v160 import quality_contract_manifest

from .assessment import assess_dataframe
from .evidence_readiness import assess_evidence_readiness, build_evidence_manifest_template
from .capability import assess_capability, capability_spec_for
from .profiles import profile_for
from .native_workflows import is_native_engine, native_engine_status, run_native_workflow


_ENGINE_ALIASES: dict[str, tuple[str, ...]] = {
    "bwa": ("bwa-mem2", "bwa"),
    "deeptools": ("bamCoverage",),
    "gromacs": ("gmx", "gmx_mpi"),
    "openmm": (),
    "scanpy": (),
    "scvelo": (),
    "cellrank": (),
    "stardist": (),
    "openslide": (),
    "netmhcpan": ("netMHCpan", "netMHCpan.exe"),
    "netmhciipan": ("netMHCIIpan", "netMHCIIpan.exe"),
    "iqtree": ("iqtree2", "iqtree"),
    "openms": ("FileInfo", "FileInfo.exe"),
    "proteinmpnn": ("protein_mpnn_run.py", "proteinmpnn"),
    "rfdiffusion": ("run_inference.py", "rfdiffusion"),
    "msgfplus": ("msgfplus", "MSGFPlus"),
    "regenie": ("regenie",),
    "saige": ("step1_fitNULLGLMM.R", "SAIGE"),
    "sniffles": ("sniffles", "sniffles2"),
    "expansionhunter": ("ExpansionHunter", "expansionhunter"),
    "macs2": ("macs2", "macs3"),
    "msconvert": ("msconvert", "msconvert.exe"),
    "cellpose": ("cellpose",),
    "plink2": ("plink2", "plink2.exe"),
    "rmats": ("rmats.py", "rmats"),
    "majiq": ("majiq",),
    "suppa2": ("suppa.py", "suppa2"),
    "anarci": ("ANARCI", "anarci"),
    "igblast": ("igblastn", "igblastp"),
    "obabel": ("obabel", "obabel.exe"),
    "whatshap": ("whatshap",),
    "vep": ("vep",),
    "bowtie": ("bowtie", "bowtie2"),
    "comet": ("comet", "comet.exe"),
}

_PYTHON_PACKAGES = {
    "openmm": "openmm",
    "scanpy": "scanpy",
    "scvelo": "scvelo",
    "cellrank": "cellrank",
    "stardist": "stardist",
    "openslide": "openslide",
    "cellpose": "cellpose",
    "anarci": "anarci",
    "whatshap": "whatshap",
}


def _engine_status(engine: str) -> dict[str, Any]:
    if is_native_engine(engine):
        return native_engine_status(engine)
    candidates = _ENGINE_ALIASES.get(engine, (engine,))
    path = ""
    for candidate in candidates:
        located = shutil.which(candidate)
        if located:
            path = located
            break
    package = _PYTHON_PACKAGES.get(engine)
    package_available = bool(package and importlib.util.find_spec(package))
    available = bool(path or package_available)
    return {
        "engine": engine,
        "available": available,
        "detected_path_or_package": path or (f"Python package: {package}" if package_available else "Not detected"),
        "execution_policy": "Explicit user action only",
    }



def engine_status_frame(module_key: str) -> pd.DataFrame:
    profile = profile_for(module_key)
    engines: list[str] = list(profile.engines) if profile is not None else []
    capability_spec = capability_spec_for(module_key)
    if capability_spec is not None:
        for stage in capability_spec.stages:
            engines.extend(stage.engines)
    engines = list(dict.fromkeys(engines))
    if not engines:
        return pd.DataFrame(columns=["engine", "available", "detected_path_or_package", "execution_policy"])
    return pd.DataFrame([_engine_status(engine) for engine in engines])

def render_depth_upgrade_panel(
    module_key: str,
    data: pd.DataFrame | None = None,
    *,
    key_prefix: str = "depth",
    expanded: bool = False,
    source_mode: str | None = None,
    run_summary: dict[str, Any] | None = None,
    evidence_metadata: dict[str, Any] | None = None,
) -> None:
    profile = profile_for(module_key)
    if profile is None:
        return
    with st.expander("Advanced scientific depth, readiness and validation", expanded=expanded):
        section_title(profile.title, "🧪")
        st.caption("This panel separates built-in QC from capabilities that require external engines, reference assets or independent validation.")
        has_capability = capability_spec_for(module_key) is not None
        tab_names = ["Readiness", "Data QC", "Native execution", "Evidence readiness", "Validation", "Optimization"]
        if has_capability:
            tab_names.extend(["Pipeline", "Release gate"])
        tab_names.append("Manifest")
        tabs = st.tabs(tab_names)
        with tabs[0]:
            engine_frame = engine_status_frame(module_key)
            available = int(engine_frame["available"].sum()) if not engine_frame.empty else 0
            metric_cards([
                ("Engines", f"{available}/{len(profile.engines)}", "Detected locally"),
                ("References", len(profile.references), "Required/planned"),
                ("Native formats", len(profile.native_formats), "Supported or adapter-ready"),
                ("Validation gates", len(profile.validations), "Must be reviewed"),
            ])
            quality_contract = quality_contract_manifest(module_key)
            quality_rows = pd.DataFrame(quality_contract["dimensions"])
            st.success("Step 160 internal module quality contract: 10/10 software-owned controls enabled.")
            st.caption("Specialist tools, qualified references and independent scientific evidence remain separate and are never auto-passed.")
            with st.expander("View the 10-point module quality contract", expanded=False):
                smart_dataframe(quality_rows, height=360, key=f"{key_prefix}_{module_key}_step160_quality_contract")
                st.download_button(
                    "Download Step 160 quality contract",
                    data=json.dumps(quality_contract, indent=2).encode("utf-8"),
                    file_name=f"{module_key}_step160_quality_contract.json",
                    mime="application/json",
                    key=f"{key_prefix}_{module_key}_step160_quality_download",
                    width="stretch",
                )
            if not engine_frame.empty:
                smart_dataframe(engine_frame, height=280, key=f"{key_prefix}_{module_key}_engines")
            else:
                st.info("This module's main depth upgrades are built-in statistical/data-quality workflows rather than command-line engines.")
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Reference assets**")
                for item in profile.references:
                    st.markdown(f"- {item}")
            with c2:
                st.markdown("**Native formats**")
                for item in profile.native_formats:
                    st.markdown(f"- {item}")

        with tabs[1]:
            if data is None or data.empty:
                st.info("Run or import data in this module to generate module-specific depth QC.")
            else:
                try:
                    assessment = assess_dataframe(module_key, data)
                    metric_cards([
                        ("Checks passed", assessment.summary["checks_passed"], "Automatic QC"),
                        ("Review", assessment.summary["checks_for_review"], "Needs attention"),
                        ("Failed", assessment.summary["checks_failed"], "Blocking checks"),
                        ("Flagged rows", assessment.summary["flagged_records"], "Bounded preview"),
                    ])
                    smart_dataframe(assessment.quality_checks, height=300, key=f"{key_prefix}_{module_key}_qc")
                    if not assessment.metrics.empty:
                        smart_dataframe(assessment.metrics, height=300, key=f"{key_prefix}_{module_key}_metrics")
                    if not assessment.flagged_records.empty:
                        with st.expander("Flagged-record preview", expanded=False):
                            smart_dataframe(assessment.flagged_records, height=340, key=f"{key_prefix}_{module_key}_flagged")
                    for recommendation in assessment.recommendations:
                        st.warning(recommendation)
                except Exception as exc:
                    error_id = f"DEPTH-{abs(hash((module_key, type(exc).__name__, str(exc)))) % 10**10:010d}"
                    st.error(f"Scientific depth QC stopped safely · {error_id}")
                    st.caption("The primary module remains usable. Review the input schema or export diagnostics from System Diagnostics.")

        native_result = None
        with tabs[2]:
            section_title("Built-in deterministic scientific execution", "⚙️")
            st.caption("Step 160 adds a ten-point module quality contract, full input/output integrity audits and reproducibility signatures on top of memory-aware admission, crash-loop protection, atomic redacted diagnostics and run-on-demand execution. Specialist pipelines and independent evidence remain required for confirmatory use.")
            analysis_mode = st.selectbox(
                "Local analysis mode",
                ["auto", "interactive", "extended", "full"],
                format_func=lambda value: {
                    "auto": "Auto safe · choose the largest qualified mode for this machine",
                    "interactive": "Interactive · up to 250k rows / 100 features",
                    "extended": "Extended · up to 750k rows / 256 features",
                    "full": "Full desktop · up to 1M rows / 512 features",
                }[value],
                key=f"{key_prefix}_{module_key}_analysis_mode",
                help="Auto safe evaluates current memory pressure and can downgrade before allocation. Bounded runs use deterministic even coverage across the full input rather than first-N rows.",
            )
            if data is None or data.empty:
                st.info("Run or import tabular data in this module to execute the local scientific core.")
            else:
                root = Path(__file__).resolve().parents[3]
                snapshot = capture_resource_snapshot(root)
                admission = assess_dataframe_admission(data, analysis_mode, root=root, snapshot=snapshot)
                metric_cards([
                    ("Safe mode", admission.effective_mode.title(), "Resource-aware admission"),
                    ("Available memory", f"{snapshot.available_memory_bytes / 1024**3:.1f} GiB", "Before native execution"),
                    ("Memory pressure", f"{snapshot.memory_pressure * 100:.0f}%", "Protected threshold monitoring"),
                    ("Estimated peak", f"{admission.estimated_peak_bytes / 1024**2:.0f} MiB", "Conservative working estimate"),
                ])
                for warning in admission.warnings:
                    st.warning(warning)
                result_key = f"{key_prefix}_{module_key}_step159_native_result"
                signature_key = f"{result_key}_signature"
                signature_frame = pd.concat([data.head(3), data.tail(3)], axis=0) if len(data) > 6 else data
                signature = (
                    tuple(data.shape),
                    tuple(str(column) for column in data.columns),
                    int(pd.util.hash_pandas_object(signature_frame, index=True).sum()) if not signature_frame.empty else 0,
                    analysis_mode,
                )
                if st.session_state.get(signature_key) != signature:
                    st.session_state.pop(result_key, None)
                run_clicked = st.button(
                    "Run protected native analysis",
                    key=f"{key_prefix}_{module_key}_step159_run",
                    type="primary",
                    width="stretch",
                    disabled=not admission.allowed,
                )
                if run_clicked:
                    run_metadata = dict(evidence_metadata or {})
                    run_metadata.update({
                        "analysis_mode": analysis_mode,
                        "effective_analysis_mode": admission.effective_mode,
                        "project_root": str(root),
                        "persist_diagnostics": True,
                    })
                    with st.spinner("Running protected deterministic analysis…"):
                        st.session_state[result_key] = run_native_workflow(module_key, data, metadata=run_metadata)
                    st.session_state[signature_key] = signature
                native_result = st.session_state.get(result_key)
                if native_result is None:
                    st.info("Analysis is ready. Use the Run button to avoid expensive reruns while changing controls.")
                else:
                    metric_cards([
                        ("Execution", native_result.status.title(), "Pass, review or fail-closed"),
                        ("Rows analyzed", f"{native_result.summary['rows_analyzed']:,}", "Bounded deterministic run"),
                        ("Checks passed", native_result.summary["checks_passed"], "Automatic checks"),
                        ("Tables", native_result.summary["tables_generated"], "Derived outputs"),
                    ])
                    smart_dataframe(native_result.checks, height=320, key=f"{key_prefix}_{module_key}_native_checks")
                    if not native_result.metrics.empty:
                        smart_dataframe(native_result.metrics, height=280, key=f"{key_prefix}_{module_key}_native_metrics")
                    for table_name, table in native_result.tables.items():
                        if isinstance(table, pd.DataFrame) and not table.empty:
                            with st.expander(table_name.replace("_", " ").title(), expanded=False):
                                smart_dataframe(table, height=340, key=f"{key_prefix}_{module_key}_native_{table_name}")
                    for recommendation in native_result.recommendations:
                        st.warning(recommendation)
                    smart_json(
                        native_result.manifest,
                        title="Step 160 native execution manifest",
                        download_name=f"{module_key}_step159_native_run.json",
                        key=f"{key_prefix}_{module_key}_step160_native_manifest",
                    )
                    st.download_button(
                        "Download complete native result bundle",
                        data=native_result.complete_bundle,
                        file_name=f"{module_key}_step160_complete_native_results.zip",
                        mime="application/zip",
                        key=f"{key_prefix}_{module_key}_native_bundle",
                        width="stretch",
                    )

        evidence_payload: dict[str, Any] = dict(evidence_metadata or {})
        with tabs[3]:
            section_title("Evidence-complete scientific readiness", "🧾")
            st.caption("The score rewards traceable evidence and automatically blocks unsupported release claims. Declarations are not treated as verification.")
            template = build_evidence_manifest_template(
                module_key,
                profile_references=profile.references,
                profile_validations=profile.validations,
            )
            with st.expander("Optional evidence declaration JSON", expanded=False):
                declaration_text = st.text_area(
                    "Paste a versioned evidence declaration",
                    value=json.dumps(evidence_payload, indent=2, default=str) if evidence_payload else "{}",
                    height=220,
                    key=f"{key_prefix}_{module_key}_evidence_json",
                )
                try:
                    parsed = json.loads(declaration_text or "{}")
                    if not isinstance(parsed, dict):
                        raise ValueError("Evidence declaration must be a JSON object")
                    evidence_payload = parsed
                except (json.JSONDecodeError, ValueError) as exc:
                    st.error(f"Evidence declaration is invalid: {exc}")
                st.download_button(
                    "Download evidence template",
                    data=json.dumps(template, indent=2, default=str),
                    file_name=f"{module_key}_evidence_template.json",
                    mime="application/json",
                    key=f"{key_prefix}_{module_key}_evidence_template_download",
                    width="stretch",
                )
            evidence_readiness = assess_evidence_readiness(
                module_key,
                data,
                profile_references=profile.references,
                profile_validations=profile.validations,
                metadata=evidence_payload,
                source_mode=source_mode,
                run_summary=run_summary,
            )
            metric_cards([
                ("Readiness", f"{evidence_readiness.score:.0f}/100", f"Grade {evidence_readiness.grade}"),
                ("Data quality", f"{evidence_readiness.data_quality_score:.0f}/30", "Schema and integrity"),
                ("Study design", f"{evidence_readiness.design_score:.0f}/20", "Replication and controls"),
                ("Release ready", "Yes" if evidence_readiness.release_ready else "No", "Independent evidence required"),
            ])
            smart_dataframe(evidence_readiness.checks, height=390, key=f"{key_prefix}_{module_key}_evidence_checks")
            with st.expander("Domain evidence requirements", expanded=False):
                smart_dataframe(evidence_readiness.requirements, height=420, key=f"{key_prefix}_{module_key}_evidence_requirements")
            if evidence_readiness.blockers:
                st.markdown("**Open scientific blockers**")
                for blocker in evidence_readiness.blockers[:20]:
                    st.markdown(f"- {blocker}")
                if len(evidence_readiness.blockers) > 20:
                    st.caption(f"{len(evidence_readiness.blockers) - 20} additional blockers are included in the manifest.")
            smart_json(
                evidence_readiness.manifest,
                title="Step 160 readiness manifest",
                download_name=f"{module_key}_step160_readiness.json",
                key=f"{key_prefix}_{module_key}_evidence_manifest",
            )

        with tabs[4]:
            st.markdown("**Validation requirements**")
            for index, validation in enumerate(profile.validations, start=1):
                st.checkbox(validation, value=False, key=f"{key_prefix}_{module_key}_validation_{index}")
            st.warning(profile.boundary)

        with tabs[5]:
            st.markdown("**Performance and reliability plan**")
            for item in profile.optimization:
                st.markdown(f"- {item}")
            st.markdown("- External tools run only from an explicit action and should use the background queue.")
            st.markdown("- Large inputs should use indexed/streamed access rather than full in-memory copies.")
            st.markdown("- Results must record input hashes, engine/database versions and parameters.")

        manifest_index = 6
        capability = None
        if has_capability:
            capability = assess_capability(
                module_key,
                data,
                engine_status_frame(module_key),
                evidence_metadata=evidence_payload,
                source_mode=source_mode,
                run_summary=run_summary,
            )
            with tabs[6]:
                section_title("Domain pipeline coverage", "🧭")
                if capability is None:
                    st.info("No Step 151 domain pipeline is registered for this module.")
                else:
                    metric_cards([
                        ("Execution tier", capability.tier, capability.tier_label),
                        ("Automatic coverage", f"{capability.coverage * 100:.0f}%", "Built-in or detected-engine stages"),
                        ("Built-in ready", capability.built_in_ready, "Runs without specialist binaries"),
                        ("Blocked", capability.blocked, "Data/schema blockers"),
                    ])
                    smart_dataframe(capability.stage_table, height=430, key=f"{key_prefix}_{module_key}_pipeline")
                    st.warning(capability.manifest["evidence_boundary"])
            with tabs[7]:
                section_title("Release and evidence gate", "🛡️")
                if capability is not None:
                    metric_cards([
                        ("Release ready", "Yes" if capability.release_ready else "No", "Software and evidence gate"),
                        ("Readiness", f"{capability.readiness_score:.0f}/100", f"Grade {capability.readiness_grade}"),
                        ("Pipeline blockers", len(capability.blockers), "Open stage requirements"),
                        ("Tier", capability.tier, "A executable · B adapter · C blocked/review"),
                    ])
                    if capability.blockers:
                        st.markdown("**Open pipeline requirements**")
                        for blocker in capability.blockers:
                            st.markdown(f"- {blocker}")
                    st.markdown("**High-stakes release blockers**")
                    for blocker_index, blocker in enumerate(capability.manifest["release_blockers"], start=1):
                        st.checkbox(blocker, value=False, key=f"{key_prefix}_{module_key}_release_{blocker_index}")
                    st.caption("The checklist is a review aid. Checking a box does not create or certify evidence.")
            manifest_index = 8

        with tabs[manifest_index]:
            manifest = {
                "schema": "biointel.step160.scientific-depth.v7",
                "release_step": 160,
                "module_key": module_key,
                "step160_quality_contract": quality_contract_manifest(module_key),
                "profile": asdict(profile),
                "engine_status": [_engine_status(engine) for engine in profile.engines],
                "data_rows": int(len(data)) if isinstance(data, pd.DataFrame) else 0,
                "data_columns": list(data.columns) if isinstance(data, pd.DataFrame) else [],
                "automatic_execution_policy": "Explicit action only",
                "capability": capability.manifest if capability is not None else None,
                "native_execution": native_result.manifest if native_result is not None else None,
                "evidence_readiness": evidence_readiness.manifest,
                "source_mode": source_mode,
                "run_summary": run_summary or {},
            }
            smart_json(manifest, title="Scientific depth manifest", download_name=f"{module_key}_scientific_depth.json", key=f"{key_prefix}_{module_key}_manifest")
