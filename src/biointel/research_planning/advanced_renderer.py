from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from biointel.ui.components import metric_cards, smart_dataframe, smart_json

from .advanced_profiles import ADVANCED_PROFILES, get_advanced_profile
from .amendment import compare_plans, impact_summary
from .assumptions import AssumptionRegistry
from .calculation_verification import boundary_tests, verification_table, verify_two_group_continuous
from .collaboration import PlanningCollaborationStore
from .consistency import audit_study_design, consistency_summary
from .digital_thread import ResearchDigitalThreadStore, ThreadLink, ThreadNode
from .estimands import Estimand, IntercurrentEvent, estimand_flow, estimand_validation_table
from .interoperability import build_define_xml_readiness, build_fhir_questionnaire, build_odm_xml, build_variable_mapping
from .simulation import DEFAULT_SCENARIOS, simulate_scenarios
from .standards import readiness_summary, standards_matrix, validate_readiness

PROJECT_ROOT = Path(__file__).resolve().parents[3]
OS_ROOT = PROJECT_ROOT / "UserData" / "research_planning"
THREAD_DB = OS_ROOT / "research_digital_thread.sqlite"
ASSUMPTIONS_DB = OS_ROOT / "assumptions.sqlite"
COLLAB_DB = OS_ROOT / "collaboration.sqlite"


def _safe_payload(module_key: str, result: Any | None) -> dict[str, Any]:
    summary = getattr(result, "summary", {}) if result is not None else {}
    input_hash = summary.get("input_sha256", "") if isinstance(summary, dict) else ""
    base = {
        "protocol_id": "BIOINTEL-PLAN-001",
        "protocol_version": "0.1-draft",
        "background": "Scientific rationale documented in the study protocol.",
        "rationale": "Research question and evidence gap require prospective evaluation.",
        "primary_objective": "Evaluate the prespecified primary research objective.",
        "secondary_objectives": ["Evaluate safety and supporting secondary outcomes."],
        "study_design": "Parallel controlled study",
        "allocation": "1:1",
        "blinding": "Assessor blinded",
        "inclusion_criteria": ["Meets target population definition"],
        "exclusion_criteria": ["Material safety or interpretability concern"],
        "recruitment_setting": "Multi-site research setting",
        "intervention": "Planned intervention or exposure",
        "comparator": "Prespecified reference condition",
        "adherence_plan": "Adherence measured at each planned visit",
        "primary_endpoint": "Primary outcome",
        "endpoint_timing": "End of follow-up",
        "measurement_method": "Validated measurement procedure",
        "sample_size": int(summary.get("total_sample_size", summary.get("records", 200)) or 200),
        "effect_size": 0.35,
        "alpha": 0.05,
        "power": 0.80,
        "crf_plan": "Versioned CRF and data dictionary",
        "data_management_plan": "Controlled acquisition, validation, query and lock process",
        "monitoring_plan": "Risk-proportionate monitoring",
        "ethics_status": "Planning only",
        "consent_plan": "Consent workflow to be approved",
        "dissemination_plan": "Results reported irrespective of outcome",
        "critical_to_quality": ["Primary endpoint", "Eligibility", "Randomization", "Data completeness"],
        "risk_register": ["Recruitment", "Missing data", "Assay failure"],
        "risk_owner": "Study team",
        "risk_trigger": "Threshold-based escalation",
        "safety_plan": "Safety reporting and escalation plan",
        "participant_burden": "Participant burden assessed",
        "privacy_plan": "Minimum necessary data and access controls",
        "source_data_plan": "Source-to-CRF mapping",
        "audit_trail": "Immutable version and review history",
        "data_quality_controls": ["Range checks", "Consistency checks", "Duplicate checks"],
        "estimand_treatment": "Assigned treatment condition",
        "estimand_population": "Eligible randomized population",
        "estimand_variable": "Primary endpoint at target timepoint",
        "intercurrent_events": ["Treatment discontinuation", "Rescue medication"],
        "intercurrent_strategy": ["Treatment policy", "Hypothetical"],
        "population_summary": "Difference in adjusted means",
        "estimator": "Covariate-adjusted regression",
        "sensitivity_analyses": ["Per-protocol", "Tipping-point"],
        "objectives": ["Primary objective", "Secondary objective"],
        "endpoints": ["primary_outcome"],
        "activities": ["Screening", "Baseline", "Follow-up"],
        "epochs": ["Screening", "Treatment", "Follow-up"],
        "crf_variables": ["primary_outcome", "site", "baseline_value"],
        "controlled_terminology": ["Sex", "Visit", "Status"],
        "units": ["SI units"],
        "sdtm_mapping": True,
        "unique_subject_id": "USUBJID",
        "adam_mapping": True,
        "derivations": True,
        "analysis_flags": True,
        "fhir_mapping": True,
        "source_provenance": input_hash or "Starter planning context",
        "randomization_strata": ["site"],
        "protocol_sample_size": int(summary.get("total_sample_size", 200) or 200),
        "power_sample_size": int(summary.get("total_sample_size", 200) or 200),
        "visits": ["Screening", "Baseline", "Follow-up"],
        "biospecimen_visits": ["Baseline", "Follow-up"],
        "estimand_ids": ["EST-001"],
        "sap_estimand_ids": ["EST-001"],
        "protocol_sha256": input_hash or sha256(module_key.encode()).hexdigest(),
        "prereg_protocol_sha256": input_hash or sha256(module_key.encode()).hexdigest(),
        "estimated_eligible_population": 500,
        "budget_total": 1_000_000,
        "budget_contingency_fraction": 0.12,
        "operational_readiness_score": 75,
        "data_readiness_score": 78,
        "reproducibility_score": 82,
        "risk_control_score": 72,
        "participant_protection_score": 80,
        "budget_readiness_score": 70,
        "module_key": module_key,
    }
    return base


def _sankey_from_flow(flow: pd.DataFrame) -> go.Figure:
    if flow.empty:
        return go.Figure()
    labels = list(dict.fromkeys([*flow["source"].astype(str), *flow["target"].astype(str)]))
    index = {label: idx for idx, label in enumerate(labels)}
    return go.Figure(
        go.Sankey(
            node={"label": labels, "pad": 12, "thickness": 14},
            link={
                "source": [index[value] for value in flow["source"].astype(str)],
                "target": [index[value] for value in flow["target"].astype(str)],
                "value": flow["weight"].astype(float).tolist(),
            },
        )
    ).update_layout(title="Objective → estimand → estimator trace")


def render_connected_planning_os(module_key: str, result: Any | None = None, key_prefix: str | None = None) -> None:
    key = key_prefix or f"rp_os_{module_key}"
    profile = get_advanced_profile(module_key)
    plan = st.session_state.setdefault(f"{key}_plan", _safe_payload(module_key, result))
    st.caption("Local readiness tooling supports traceability and structured planning; it does not certify regulatory compliance or replace expert review.")

    tabs = st.tabs([
        "Digital thread",
        "Standards & estimand",
        "Scenarios & amendment",
        "CDISC/FHIR",
        "Assumptions & collaboration",
        "Consistency & verification",
    ])

    with tabs[0]:
        st.markdown("#### Unified Research Digital Thread")
        c1, c2, c3 = st.columns(3)
        node_type = c1.selectbox("Entity type", sorted({"objective", "endpoint", "estimand", "sample_size", "visit", "crf_variable", "analysis", "risk", "milestone", "assumption"}), key=f"{key}_node_type")
        node_title = c2.text_input("Entity title", value=module_key.replace("_", " ").title(), key=f"{key}_node_title")
        node_status = c3.selectbox("Entity status", ["Draft", "Reviewed", "Locked", "Needs review"], key=f"{key}_node_status")
        try:
            store = ResearchDigitalThreadStore(THREAD_DB)
            if st.button("Add or update thread entity", key=f"{key}_add_node"):
                node_id = store.stable_node_id(module_key, node_type, node_title)
                store.upsert_node(ThreadNode(node_id, node_type, node_title, module_key, node_status, {"source_module": module_key}))
                st.success(f"Digital-thread entity saved: {node_id}")
            nodes = store.nodes()
            links = store.links()
            metric_cards([
                ("Thread entities", len(nodes), None),
                ("Cross-module links", len(links), None),
                ("Orphan entities", len(store.orphan_report()), "Unlinked entities require traceability review"),
                ("Audit events", len(store.audit(5000)), None),
            ])
            if len(nodes) >= 2:
                source = st.selectbox("Link source", nodes["node_id"].tolist(), format_func=lambda value: f"{value} · {nodes.loc[nodes['node_id']==value,'title'].iloc[0]}", key=f"{key}_link_source")
                target_options = [value for value in nodes["node_id"].tolist() if value != source]
                target = st.selectbox("Link target", target_options, format_func=lambda value: f"{value} · {nodes.loc[nodes['node_id']==value,'title'].iloc[0]}", key=f"{key}_link_target")
                relation = st.text_input("Relationship", value="supports", key=f"{key}_relation")
                if st.button("Create traceability link", key=f"{key}_link"):
                    store.link(ThreadLink(source, target, relation, True))
                    st.success("Traceability link saved.")
            smart_dataframe(nodes.drop(columns=["payload_json", "payload"], errors="ignore"), height=300, key=f"{key}_nodes_table")
            with st.expander("Cross-module links and orphan review"):
                smart_dataframe(store.links(), height=250, key=f"{key}_links_table")
                smart_dataframe(store.orphan_report(), height=250, key=f"{key}_orphans")
        except Exception as exc:
            st.error(f"Digital thread is unavailable: {exc}")
        st.markdown("#### Module-specific advanced capability")
        c1, c2 = st.columns(2)
        with c1:
            for feature in profile.advanced_features:
                st.markdown(f"- {feature}")
        with c2:
            for visual in profile.advanced_visuals:
                st.markdown(f"- {visual}")

    with tabs[1]:
        st.markdown("#### Standards-readiness validator")
        standards = validate_readiness(plan)
        summary = readiness_summary(standards)
        metric_cards([
            ("Readiness score", f"{summary['score']:.1f}%", None),
            ("Ready requirements", f"{summary['ready']}/{summary['requirements']}", None),
            ("Critical gaps", summary["critical_missing"], None),
            ("Partial requirements", summary["partial"], None),
        ])
        matrix = standards_matrix(standards)
        if not matrix.empty:
            st.plotly_chart(px.bar(matrix, x="section", y="score", color="standard", barmode="group", title="Standards readiness by section"), width="stretch", key=f"{key}_standards_chart")
        smart_dataframe(standards, height=360, key=f"{key}_standards_table")

        st.markdown("#### Estimand Builder")
        c1, c2, c3 = st.columns(3)
        objective = c1.text_input("Objective", value=str(plan.get("primary_objective", "Primary objective")), key=f"{key}_est_obj")
        treatment = c2.text_input("Treatment condition", value=str(plan.get("estimand_treatment", "Treatment")), key=f"{key}_est_trt")
        population = c3.text_input("Population", value=str(plan.get("estimand_population", "Eligible population")), key=f"{key}_est_pop")
        c4, c5, c6 = st.columns(3)
        variable = c4.text_input("Variable", value=str(plan.get("estimand_variable", "Primary endpoint")), key=f"{key}_est_var")
        summary_measure = c5.text_input("Population summary", value=str(plan.get("population_summary", "Difference in means")), key=f"{key}_est_summary")
        estimator = c6.text_input("Estimator", value=str(plan.get("estimator", "Adjusted regression")), key=f"{key}_estimator")
        event = st.text_input("Intercurrent event", value="Treatment discontinuation", key=f"{key}_ice")
        strategy = st.selectbox("Intercurrent-event strategy", ["treatment policy", "hypothetical", "composite", "while on treatment", "principal stratum"], key=f"{key}_ice_strategy")
        sensitivity = st.text_input("Sensitivity analyses · semicolon separated", value="Per-protocol;Tipping-point", key=f"{key}_sensitivity")
        estimand = Estimand(
            "EST-001", objective, treatment, population, variable, summary_measure, estimator,
            (IntercurrentEvent(event, strategy),),
            tuple(item.strip() for item in sensitivity.split(";") if item.strip()),
        )
        validation = estimand_validation_table([estimand])
        smart_dataframe(validation, height=200, key=f"{key}_estimand_validation")
        flow = estimand_flow([estimand])
        st.plotly_chart(_sankey_from_flow(flow), width="stretch", key=f"{key}_estimand_flow")

    with tabs[2]:
        st.markdown("#### Scenario simulation engine")
        iterations = st.slider("Monte Carlo iterations", 500, 20_000, 2_000, 500, key=f"{key}_iterations")
        seed = st.number_input("Simulation seed", 0, 2_147_483_647, 142, key=f"{key}_sim_seed")
        if st.button("Run optimistic/base/conservative/stress simulation", type="primary", key=f"{key}_simulate"):
            try:
                scenario_summary, trajectories, risks = simulate_scenarios(DEFAULT_SCENARIOS, iterations, int(seed))
                st.session_state[f"{key}_scenario_summary"] = scenario_summary
                st.session_state[f"{key}_trajectories"] = trajectories
                st.session_state[f"{key}_risks"] = risks
            except Exception as exc:
                st.error(f"Simulation stopped safely: {exc}")
        scenario_summary = st.session_state.get(f"{key}_scenario_summary", pd.DataFrame())
        trajectories = st.session_state.get(f"{key}_trajectories", pd.DataFrame())
        risks = st.session_state.get(f"{key}_risks", pd.DataFrame())
        if not scenario_summary.empty:
            smart_dataframe(scenario_summary, height=260, key=f"{key}_scenario_table")
            st.plotly_chart(px.line(trajectories, x="month", y="median_enrolled", color="scenario", title="Recruitment scenario trajectories"), width="stretch", key=f"{key}_trajectory")
            st.plotly_chart(px.bar(risks, x="risk", y="probability", color="scenario", barmode="group", title="Scenario risk probabilities"), width="stretch", key=f"{key}_risk")

        st.markdown("#### Protocol Amendment Impact Analyzer")
        old_endpoint = st.text_input("Previous primary endpoint", value=str(plan.get("primary_endpoint", "Primary outcome")), key=f"{key}_old_endpoint")
        new_endpoint = st.text_input("Amended primary endpoint", value=old_endpoint, key=f"{key}_new_endpoint")
        old_n = st.number_input("Previous sample size", 1, 10_000_000, int(plan.get("sample_size", 200)), key=f"{key}_old_n")
        new_n = st.number_input("Amended sample size", 1, 10_000_000, int(old_n), key=f"{key}_new_n")
        changes = compare_plans({"primary_endpoint": old_endpoint, "sample_size": int(old_n)}, {"primary_endpoint": new_endpoint, "sample_size": int(new_n)})
        amendment_summary = impact_summary(changes)
        metric_cards([
            ("Changed fields", amendment_summary["changes"], None),
            ("Critical changes", amendment_summary["critical"], None),
            ("Affected modules", amendment_summary["affected_modules"], None),
            ("Revalidation", "Required" if amendment_summary["revalidation_required"] else "Not required", None),
        ])
        smart_dataframe(changes, height=250, key=f"{key}_amendments")

    with tabs[3]:
        st.markdown("#### CDASH / SDTM / ADaM / FHIR interoperability")
        variable_template = pd.DataFrame([
            {"variable": "participant_id", "label": "Participant identifier", "data_type": "string", "unit": "", "analysis_role": "Identifier"},
            {"variable": "site", "label": "Study site", "data_type": "string", "unit": "", "analysis_role": "Stratification"},
            {"variable": "primary_outcome", "label": "Primary outcome", "data_type": "float", "unit": "unit", "analysis_role": "Endpoint"},
            {"variable": "lab_test", "label": "Laboratory test", "data_type": "string", "unit": "", "analysis_role": "Covariate"},
            {"variable": "lab_value", "label": "Laboratory value", "data_type": "float", "unit": "SI", "analysis_role": "Covariate"},
        ])
        variable_editor = st.data_editor(variable_template, num_rows="dynamic", width="stretch", key=f"{key}_variables")
        try:
            mapping = build_variable_mapping(pd.DataFrame(variable_editor))
            readiness = build_define_xml_readiness(mapping)
            smart_dataframe(mapping, height=320, key=f"{key}_mapping")
            smart_dataframe(readiness, height=220, key=f"{key}_define_readiness")
            questionnaire = build_fhir_questionnaire(mapping)
            odm = build_odm_xml(mapping)
            c1, c2, c3 = st.columns(3)
            c1.download_button("Download mapping CSV", mapping.to_csv(index=False).encode(), "research_variable_mapping.csv", "text/csv", key=f"{key}_mapping_csv")
            c2.download_button("Download FHIR Questionnaire", json.dumps(questionnaire, indent=2).encode(), "research_questionnaire.fhir.json", "application/json", key=f"{key}_fhir")
            c3.download_button("Download ODM XML", odm, "research_crf_odm.xml", "application/xml", key=f"{key}_odm")
        except Exception as exc:
            st.error(f"Interoperability mapping failed safely: {exc}")

    with tabs[4]:
        st.markdown("#### Assumption Registry")
        try:
            registry = AssumptionRegistry(ASSUMPTIONS_DB)
            c1, c2, c3 = st.columns(3)
            name = c1.text_input("Assumption", value="Expected effect size", key=f"{key}_assumption_name")
            value = c2.text_input("Value", value="0.35", key=f"{key}_assumption_value")
            confidence = c3.selectbox("Confidence", ["Low", "Moderate", "High"], index=1, key=f"{key}_assumption_conf")
            c4, c5, c6 = st.columns(3)
            source = c4.text_input("Source", value="Evidence review", key=f"{key}_assumption_source")
            low = c5.number_input("Sensitivity low", value=0.25, key=f"{key}_assumption_low")
            high = c6.number_input("Sensitivity high", value=0.45, key=f"{key}_assumption_high")
            if st.button("Save assumption", key=f"{key}_save_assumption"):
                registry.upsert(module_key, name, value, source=source, confidence=confidence, sensitivity_low=float(low), sensitivity_high=float(high), impacted_modules=profile.consistency_links)
                st.success("Assumption saved with audit history.")
            smart_dataframe(registry.list(module_key), height=260, key=f"{key}_assumptions")
            with st.expander("Assumptions missing source or sensitivity bounds"):
                smart_dataframe(registry.sensitivity_gaps(), height=220, key=f"{key}_assumption_gaps")
        except Exception as exc:
            st.error(f"Assumption registry unavailable: {exc}")

        st.markdown("#### Structured Collaboration")
        try:
            collaboration = PlanningCollaborationStore(COLLAB_DB)
            c1, c2 = st.columns(2)
            topic = c1.text_input("Discussion title", value="Review planning assumption", key=f"{key}_discussion")
            author = c2.text_input("Reviewer / author", value="Local reviewer", key=f"{key}_author")
            if st.button("Open discussion", key=f"{key}_open_discussion"):
                thread_id = collaboration.create_thread(module_key, module_key, topic, author)
                st.session_state[f"{key}_thread_id"] = thread_id
                st.success(f"Discussion {thread_id} opened.")
            threads = collaboration.threads(module_key)
            smart_dataframe(threads, height=220, key=f"{key}_threads")
            if not threads.empty:
                thread_id = st.selectbox("Discussion", threads["thread_id"].astype(int).tolist(), key=f"{key}_thread_select")
                body = st.text_area("Comment", key=f"{key}_comment")
                mention = st.text_input("@mention", key=f"{key}_mention")
                if st.button("Add comment", key=f"{key}_add_comment"):
                    collaboration.add_comment(int(thread_id), author, body, mention)
                    st.success("Comment added.")
                smart_dataframe(collaboration.comments(int(thread_id)), height=220, key=f"{key}_comments")
        except Exception as exc:
            st.error(f"Collaboration workspace unavailable: {exc}")

    with tabs[5]:
        st.markdown("#### Study Design Consistency Auditor")
        consistency = audit_study_design(plan)
        con_summary = consistency_summary(consistency)
        metric_cards([
            ("Consistency score", f"{con_summary['score']:.1f}%", None),
            ("Checks passed", f"{con_summary['passed']}/{con_summary['checks']}", None),
            ("Needs review", con_summary["needs_review"], None),
            ("Critical open", con_summary["critical_open"], None),
        ])
        smart_dataframe(consistency, height=340, key=f"{key}_consistency")

        st.markdown("#### Independent Calculation Verification")
        c1, c2, c3 = st.columns(3)
        effect = c1.number_input("Effect size", 0.01, 5.0, 0.35, 0.05, key=f"{key}_verify_effect")
        alpha = c2.number_input("Alpha", 0.0001, 0.25, 0.05, 0.005, key=f"{key}_verify_alpha")
        power = c3.number_input("Power", 0.50, 0.999, 0.80, 0.01, key=f"{key}_verify_power")
        try:
            verified = verify_two_group_continuous(float(effect), float(alpha), float(power))
            table = verification_table([verified])
            smart_dataframe(table.drop(columns=["python_script", "r_script", "sas_script"]), height=180, key=f"{key}_verification")
            with st.expander("Formula and independent scripts"):
                st.code(verified.formula)
                st.code(verified.python_script, language="python")
                st.code(verified.r_script, language="r")
                st.code(verified.sas_script, language="sas")
            if st.toggle("Show boundary-condition matrix", key=f"{key}_boundary_toggle"):
                smart_dataframe(boundary_tests(), height=300, key=f"{key}_boundary_tests")
        except Exception as exc:
            st.error(f"Calculation verification failed safely: {exc}")
