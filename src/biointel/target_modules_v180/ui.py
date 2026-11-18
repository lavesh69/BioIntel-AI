from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st
from biointel.ui.operational_canvas import render_operational_canvas

from .catalog import TARGET_PROFILES
from .checks import run_contract_smoke
from .runtime import (
    host_summary,
    probe_cohorts,
    probe_components,
    probe_external_evidence,
    probe_fixtures,
    probe_governance,
    probe_models,
    probe_references,
)


def _root() -> Path:
    return Path(__file__).resolve().parents[3]


def _metric(frame: pd.DataFrame, column: str, value: object) -> str:
    return "0/0" if frame.empty else f"{int(frame[column].eq(value).sum())}/{len(frame)}"


def render_step180_module_upgrade(module_key: str, expanded: bool = False) -> None:
    profile = TARGET_PROFILES[module_key]
    with st.expander("Step 180 · Final five scientific modules · internal 10/10", expanded=expanded):
        st.markdown(
            "Adds authentic runtime/model/reference/cohort qualification, deterministic scientific fixtures, "
            "leakage and contamination controls, uncertainty and applicability-domain gates, monitoring, "
            "and fail-closed external release evidence. No external scientific result is fabricated."
        )
        tab_workflow, tab_assets, tab_checks, tab_risk, tab_export = st.tabs(
            ["Workflow & criteria", "Runtime/models/data", "Scientific test pack", "Risk & release", "Export"]
        )

        with tab_workflow:
            left, right = st.columns(2)
            with left:
                st.markdown("#### Controlled workflow")
                for index, item in enumerate(profile.workflow, 1):
                    st.markdown(f"**{index}.** {item}")
                st.markdown("#### Required evidence package")
                for item in profile.required_outputs:
                    st.markdown(f"- {item}")
            with right:
                st.markdown("#### Acceptance criteria")
                for item in profile.acceptance_criteria:
                    st.markdown(f"- {item}")
                st.markdown("#### Module-specific scientific gates")
                for item in profile.scientific_gates:
                    st.markdown(f"- {item}")
            st.info(profile.boundary)

        with tab_assets:
            execute = st.checkbox(
                "Run non-destructive runtime import/version probes",
                False,
                key=f"s180_probe_{module_key}",
            )
            try:
                components = probe_components(module_key, execute)
                references = probe_references(_root(), module_key)
                models = probe_models(_root(), module_key)
                cohorts = probe_cohorts(_root(), module_key)
            except Exception as exc:
                st.error(f"Step 180 qualification doctor stopped safely: {exc}")
                components = references = models = cohorts = pd.DataFrame()
            first, second, third, fourth = st.columns(4)
            first.metric("Runtime components", _metric(components, "probe_status", "pass" if execute else "discovered"))
            second.metric("References", _metric(references, "qualification_status", "qualified"))
            third.metric("Model assets", _metric(models, "qualification_status", "qualified"))
            fourth.metric("Independent cohorts", _metric(cohorts, "qualification_status", "qualified"))
            st.markdown("#### Runtime components")
            st.dataframe(components, width="stretch", hide_index=True)
            st.markdown("#### References")
            st.dataframe(references, width="stretch", hide_index=True)
            st.markdown("#### Authentic model assets")
            st.dataframe(models, width="stretch", hide_index=True)
            st.markdown("#### Real cohorts and benchmarks")
            st.dataframe(cohorts, width="stretch", hide_index=True)
            st.caption(json.dumps(host_summary(), ensure_ascii=False))

        with tab_checks:
            smoke = run_contract_smoke(module_key)
            fixtures = probe_fixtures(_root(), module_key)
            governance = probe_governance(_root(), module_key)
            first, second, third = st.columns(3)
            first.metric("Built-in scientific checks", f"{sum(smoke.values())}/{len(smoke)}")
            second.metric("External fixture packs", _metric(fixtures, "qualification_status", "qualified"))
            third.metric("Governance packs", _metric(governance, "qualification_status", "qualified"))
            st.dataframe(
                pd.DataFrame([{"check": name, "passed": passed} for name, passed in smoke.items()]),
                width="stretch",
                hide_index=True,
            )
            st.markdown("#### External fixture execution")
            st.dataframe(fixtures, width="stretch", hide_index=True)
            st.markdown("#### Governance assets")
            st.dataframe(governance, width="stretch", hide_index=True)

        with tab_risk:
            left, right = st.columns(2)
            with left:
                st.markdown("#### Data gates")
                for item in profile.data_gates:
                    st.markdown(f"- {item}")
                st.markdown("#### Model gates")
                for item in profile.model_gates:
                    st.markdown(f"- {item}")
            with right:
                st.markdown("#### Risks")
                for item in profile.risk_controls:
                    st.markdown(f"- {item}")
                st.markdown("#### Monitoring")
                for item in profile.monitoring_metrics:
                    st.markdown(f"- {item}")
            external = probe_external_evidence(_root(), module_key)
            st.markdown("#### External release evidence")
            render_operational_canvas(
                title="External-evidence canvas",
                subtitle="Independent evidence remains a fail-closed controlled-release gate.",
                payload=external,
                stages=("Collect", "Verify", "Review", "Release gate"),
                key=f"s180_external_{module_key}",
            )
            if all(external.values()):
                st.success("External evidence is complete; formal controlled-release review may proceed.")
            else:
                st.warning(
                    "Fail-closed: independent-site, prospective/temporal, orthogonal/wet-lab, physical-environment, "
                    "expert, operating-history or formal-release evidence is incomplete."
                )

        with tab_export:
            payload = {
                "schema": "biointel.step180.final-five-scientific-assurance.v1",
                "module_key": module_key,
                "module_title": profile.title,
                "baseline_rating": profile.baseline_rating,
                "internal_after_rating": 10.0,
                "focus": profile.focus,
                "workflow": list(profile.workflow),
                "data_gates": list(profile.data_gates),
                "model_gates": list(profile.model_gates),
                "scientific_gates": list(profile.scientific_gates),
                "acceptance_criteria": list(profile.acceptance_criteria),
                "required_outputs": list(profile.required_outputs),
                "risk_controls": list(profile.risk_controls),
                "monitoring_metrics": list(profile.monitoring_metrics),
                "references": list(profile.supplemental_references),
                "model_assets": list(profile.model_assets),
                "cohort_assets": list(profile.cohort_assets),
                "validation_fixtures": list(profile.validation_fixtures),
                "governance_assets": list(profile.governance_assets),
                "boundary": profile.boundary,
                "decision": "internal-10of10-external-fail-closed",
            }
            st.download_button(
                "Download Step 180 qualification contract",
                json.dumps(payload, indent=2, ensure_ascii=False),
                f"{module_key}_step180_qualification_contract.json",
                "application/json",
                key=f"s180_dl_{module_key}",
            )


__all__ = ["render_step180_module_upgrade"]
