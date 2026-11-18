from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel import __version__
from biointel.chemistry.admet import profile_admet, profile_dict
from biointel.chemistry.molecule_visualization import molecule_png
from biointel.chemistry.standardization import standardize_molecule
from biointel.discovery.admet_plugins import ENDPOINT_PLUGINS
from biointel.discovery.preparation import preparation_dict, prepare_molecular_states
from biointel.ui.components import scientific_boundary_banner, smart_dataframe, smart_json
from biointel.ui.theme import apply_theme, badge, executive_kpis, hero, section_title
from biointel.ui.workflow import (
    analysis_run,
    read_uploaded_table,
    render_methodology,
    render_upload_preflight,
)

st.set_page_config(page_title="ADMET Rule-Based Triage · BioIntel AI", page_icon="💊", layout="wide")
apply_theme()

from biointel.ui.scientific_integrations import render_page_integrations as _render_biointel_integrations
_render_biointel_integrations("pages/62_ADMET_Drug_Discovery.py", key_prefix="62_admet_drug_discovery", expanded=False)

# STEP116_MODULE_EXPERIENCE_2_TO_9
from biointel.ui.module_experience_2_9 import render_module_experience as _render_step116_module_experience
_render_step116_module_experience("admet", key_prefix="step116_62_ADMET_Drug_Discovery_admet_1", expanded=False)
hero(
    "ADMET Rule-Based Triage & Developability",
    "Standardize structures, inspect medicinal-chemistry rules, structural alerts, applicability and batch priorities without presenting unvalidated biology as fact.",
    eyebrow=f"BioIntel Discovery {__version__} · Transparent Screening",
    chips=["Parent-structure standardization", "8 property rules", "PAINS/Brenk/NIH/ZINC", "Batch ranking", "Failure exports"],
)
scientific_boundary_banner(
    source_kind="demo_reference",
    release_eligible=False,
    message=(
        "Descriptor and rule outputs are early-discovery triage only. CYP, hERG, Ames, DILI, clearance and other biological endpoints remain explicitly unassessed unless a validated endpoint model is installed."
    ),
)
render_methodology(
    method="BioIntel parent-structure standardization followed by deterministic descriptors, medicinal-chemistry rules, catalog filters and a transparent 0–100 developability score.",
    assumptions=[
        "The submitted structure represents the intended chemical entity.",
        "Parent-fragment and neutralized representations are appropriate for comparative screening.",
    ],
    limitations=[
        "No clinical or toxicological conclusion is produced.",
        "The solubility and BBB outputs are descriptor heuristics, not assay-calibrated endpoint models.",
        "Synthetic-accessibility output is a transparent complexity heuristic, not the Ertl SA score.",
    ],
    validation=[
        "Confirm protonation, tautomer, salt and stereochemical form for the intended assay.",
        "Use endpoint-specific validated models and experimental assays before progression.",
    ],
)

examples = {
    "Aspirin": "CC(=O)OC1=CC=CC=C1C(=O)O",
    "Caffeine": "CN1C=NC2=C1C(=O)N(C(=O)N2C)C",
    "Warfarin": "CC(C(=O)CC1=CC=CC=C1)C2=C(O)C=CC=C2O",
    "Ibuprofen": "CC(C)CC1=CC=C(C=C1)C(C)C(=O)O",
    "Acetaminophen": "CC(=O)NC1=CC=C(C=C1)O",
    "Nicotinamide": "NC(=O)C1=CN=CC=C1",
    "Adenosine": "NC1=NC=NC2=C1N=CN2C3OC(CO)C(O)C3O",
    "Metformin": "CN(C)C(=N)N=C(N)N",
    "Sodium acetate (standardization example)": "CC(=O)[O-].[Na+]",
}

single_tab, batch_tab, coverage_tab = st.tabs([
    "Single molecule",
    "Batch screening & ranking",
    "Endpoint coverage",
])

with single_tab:
    session_default = str(st.session_state.pop("admet_smiles", "") or st.session_state.get("discovery_smiles", ""))
    with st.form("admet_single_form"):
        selected = st.selectbox("Reference molecule", list(examples))
        default_value = session_default or examples[selected]
        smiles = st.text_input("SMILES", default_value)
        assay_ph = st.number_input(
            "Assay pH",
            min_value=0.0,
            max_value=14.0,
            value=7.4,
            step=0.1,
            help=(
                "The selected pH is recorded and applied to the molecular-state preparation context. "
                "Exact microspecies still require a qualified pKa/protonation model."
            ),
        )
        run = st.form_submit_button("Standardize and profile molecule", type="primary", width="stretch")

    if run:
        try:
            with analysis_run("Standardizing structure and calculating developability profile"):
                payload = profile_dict(profile_admet(smiles))
                payload["assay_context"] = preparation_dict(
                    prepare_molecular_states(smiles, mode="assay_context", ph=float(assay_ph))
                )
            st.session_state["admet_profile_result"] = payload
        except Exception as exc:
            st.error(f"Molecule profiling failed: {exc}")

    payload = st.session_state.get("admet_profile_result")
    if payload:
        score = int(payload["developability_score"])
        assay_context = payload.get("assay_context", {})
        executive_kpis([
            ("Rule prioritization", f"{score}/100", "Not a biological probability"),
            ("Risk level", str(payload["risk_level"]).title(), "Rule-based prioritisation tier"),
            ("QED", f"{float(payload['qed']):.3f}", "Quantitative estimate of drug-likeness"),
            ("Assay pH", f"{float(assay_context.get('requested_ph', 7.4)):.1f}", "Applied preparation context"),
        ])
        badge(
            "● Inside screening domain" if payload["applicability_domain"] == "inside screening domain" else "● Edge/outside screening domain",
            "success" if payload["applicability_domain"] == "inside screening domain" else "warning",
        )

        left, right = st.columns([1, 1.55])
        with left:
            try:
                mol, _ = standardize_molecule(str(payload["standardized_smiles"]))
                st.image(molecule_png(mol), caption="Standardized parent structure", width="stretch")
            except Exception:
                st.info("Molecule rendering unavailable.")
            st.code(str(payload["standardized_smiles"]), language=None)
            if payload.get("inchikey"):
                st.caption(f"InChIKey: {payload['inchikey']}")
        with right:
            dimensions = {
                "Developability": score,
                "QED": round(float(payload["qed"]) * 100, 1),
                "Rule pass": round(
                    100 * sum(bool(row["passed"]) for row in payload["rule_results"]) / max(1, len(payload["rule_results"])),
                    1,
                ),
                "3D character": round(min(100, float(payload["fraction_csp3"]) * 100), 1),
                "Solubility window": round(max(0, min(100, 100 + 20 * float(payload["esol_style_log_s"]))), 1),
            }
            fig = go.Figure(
                data=go.Scatterpolar(
                    r=list(dimensions.values()) + [next(iter(dimensions.values()))],
                    theta=list(dimensions.keys()) + [next(iter(dimensions.keys()))],
                    fill="toself",
                    name="Screening profile",
                )
            )
            fig.update_layout(
                polar={"radialaxis": {"visible": True, "range": [0, 100]}},
                showlegend=False,
                title="Normalized discovery scorecard",
                margin={"l": 40, "r": 40, "t": 65, "b": 30},
            )
            st.plotly_chart(fig, width="stretch")

        section_title("Structure standardization", "🧼")
        std = payload["standardization"]
        smart_dataframe([
            {"Stage": "Submitted", "SMILES": std["original_smiles"]},
            {"Stage": "Parsed canonical", "SMILES": std["parsed_canonical_smiles"]},
            {"Stage": "Parent fragment", "SMILES": std["parent_smiles"]},
            {"Stage": "Final standardized", "SMILES": std["standardized_smiles"]},
        ], height=230)
        for warning in std.get("warnings", []):
            st.warning(warning)
        st.caption("Transformations: " + " · ".join(std.get("transformations", [])))
        if assay_context:
            st.markdown("**Assay molecular-state context**")
            smart_dataframe(
                [
                    {
                        "Assay pH": assay_context.get("requested_ph"),
                        "Preparation mode": assay_context.get("mode"),
                        "Ionizable groups": ", ".join(assay_context.get("ionizable_groups", [])) or "None detected",
                        "State candidates": len(assay_context.get("state_smiles", [])),
                        "Exact microspecies assigned": assay_context.get("exact_microspecies_assigned", False),
                    }
                ],
                height=150,
            )
            for warning in assay_context.get("warnings", []):
                st.info(warning)

        section_title("Medicinal-chemistry rules", "✓")
        rules = pd.DataFrame(payload["rule_results"])
        if not rules.empty:
            rules["status"] = rules["passed"].map({True: "PASS", False: "REVIEW"})
            rules["failed_criteria"] = rules["failed_criteria"].map(lambda x: "; ".join(x) if x else "—")
            smart_dataframe(rules[["name", "status", "failed_criteria", "interpretation"]], height=430)

        section_title("Liabilities and actions", "⚠")
        blocker_col, liability_col = st.columns(2)
        with blocker_col:
            st.markdown("**Critical blockers**")
            blockers = payload.get("critical_blockers") or []
            if blockers:
                for item in blockers:
                    st.error(item)
            else:
                st.success("No critical rule-based blocker detected.")
        with liability_col:
            st.markdown("**Modifiable liabilities**")
            liabilities = payload.get("modifiable_liabilities") or []
            if liabilities:
                for item in liabilities:
                    st.warning(item)
            else:
                st.success("No major modifiable liability detected by current rules.")
        st.markdown("**Recommended next actions**")
        for item in payload.get("recommendations", []):
            st.write(f"• {item}")

        section_title("Structural-alert catalog", "⌁")
        alerts = pd.DataFrame(payload.get("alert_matches", []))
        if alerts.empty and not payload.get("structural_alerts"):
            st.success("No PAINS, Brenk, NIH or ZINC catalog match detected.")
        else:
            if not alerts.empty:
                smart_dataframe(alerts, height=360)
            custom_only = [item for item in payload.get("structural_alerts", []) if not item.startswith(("BRENK:", "NIH:", "ZINC:"))]
            if custom_only:
                st.caption("Additional transparent SMARTS alerts: " + "; ".join(custom_only))

        section_title("Endpoint matrix", "▦")
        endpoint_frame = pd.DataFrame(payload["endpoint_summary"])
        endpoint_filter = st.multiselect(
            "Domains",
            sorted(endpoint_frame["domain"].unique()),
            default=sorted(endpoint_frame["domain"].unique()),
            key="single_endpoint_domains",
        )
        smart_dataframe(endpoint_frame[endpoint_frame["domain"].isin(endpoint_filter)], height=520)

        handoff = st.columns(3)
        if handoff[0].button("Send standardized structure to SMILES Analyzer", width="stretch"):
            st.session_state["imported_smiles"] = payload["standardized_smiles"]
            st.switch_page("pages/3_Drug_SMILES_Analyzer.py")
        if handoff[1].button("Send to DTI Feature Builder", width="stretch"):
            st.session_state["dti_smiles"] = payload["standardized_smiles"]
            st.switch_page("pages/4_DTI_Feature_Builder.py")
        if handoff[2].button("Open Discovery Command Center", width="stretch"):
            st.session_state["discovery_smiles"] = payload["standardized_smiles"]
            st.switch_page("pages/88_Discovery_Command_Center.py")

        with st.expander("Complete technical payload"):
            smart_json(payload, download_name="admet_rule_based_profile.json", key="admet_single_payload")

with batch_tab:
    uploaded = st.file_uploader("CSV compound library", type=["csv"], key="admet_batch_upload")
    upload_profile = render_upload_preflight(
        uploaded,
        key="admet_batch",
        allowed_extensions=["csv"],
        soft_limit_mb=20,
        hard_limit_mb=100,
    )
    starter = pd.DataFrame({"name": list(examples), "smiles": list(examples.values())})
    try:
        source = read_uploaded_table(uploaded) if uploaded else starter
    except Exception as exc:
        st.error(f"Could not read CSV: {exc}")
        source = pd.DataFrame()

    if source.empty or len(source.columns) == 0:
        st.warning("The selected CSV is empty. Add at least one row and a SMILES column.")
    else:
        controls = st.columns(3)
        name_column = controls[0].selectbox("Name/ID column", list(source.columns), index=0)
        smiles_index = 1 if len(source.columns) > 1 else 0
        smiles_column = controls[1].selectbox("SMILES column", list(source.columns), index=smiles_index)
        upper = min(5000, len(source))
        max_rows = controls[2].number_input("Maximum molecules", 1, max(1, upper), min(500, max(1, upper)))
        deduplicate = st.checkbox("Deduplicate standardized structures by InChIKey", value=True)
        if name_column == smiles_column:
            st.error("Name/ID and SMILES columns must be different.")
        run_batch = st.button(
            "Run standardized batch triage",
            type="primary",
            width="stretch",
            disabled=name_column == smiles_column,
        )
        if run_batch:
            rows: list[dict[str, object]] = []
            failures: list[dict[str, object]] = []
            progress = st.progress(0, text="Preparing molecule batch")
            subset = source.head(int(max_rows)).reset_index(drop=True)
            with analysis_run("Standardizing, profiling and ranking molecule batch"):
                for index, row in subset.iterrows():
                    name = row.get(name_column, f"row_{index + 1}")
                    raw_smiles = str(row.get(smiles_column, ""))
                    try:
                        payload = profile_dict(profile_admet(raw_smiles))
                        rows.append({
                            "source_row": index + 1,
                            "name": name,
                            "input_smiles": raw_smiles,
                            **payload,
                        })
                    except Exception as exc:
                        failures.append({
                            "source_row": index + 1,
                            "name": name,
                            "input_smiles": raw_smiles,
                            "error": str(exc),
                        })
                    progress.progress((index + 1) / max(1, len(subset)), text=f"Processed {index + 1:,}/{len(subset):,}")
            result = pd.DataFrame(rows)
            failure_frame = pd.DataFrame(failures)
            if not result.empty:
                result["duplicate_standardized_structure"] = result.duplicated("inchikey", keep=False) & result["inchikey"].notna()
                if deduplicate:
                    result = result.sort_values(["developability_score", "risk_score"], ascending=[False, True]).drop_duplicates("inchikey", keep="first")
                result = result.sort_values(
                    ["developability_score", "risk_score", "qed"],
                    ascending=[False, True, False],
                ).reset_index(drop=True)
                result.insert(0, "priority_rank", range(1, len(result) + 1))
            st.session_state["admet_batch_result"] = result
            st.session_state["admet_batch_failures"] = failure_frame
            st.toast(f"Batch complete: {len(result):,} profiles, {len(failure_frame):,} failures")

        result = st.session_state.get("admet_batch_result")
        failure_frame = st.session_state.get("admet_batch_failures")
        if isinstance(result, pd.DataFrame) and not result.empty:
            display_columns = [
                "priority_rank", "name", "standardized_smiles", "developability_score", "risk_level", "qed",
                "esol_style_log_s", "lipinski_pass", "veber_pass", "aggregation_risk",
                "applicability_domain", "duplicate_standardized_structure",
            ]
            smart_dataframe(result[[column for column in display_columns if column in result.columns]], height=560)
            chart_col, filter_col = st.columns([1.4, 1])
            with chart_col:
                fig = px.scatter(
                    result,
                    x="molecular_weight",
                    y="logp",
                    size="developability_score",
                    color="risk_level",
                    hover_name="name",
                    hover_data=["qed", "esol_style_log_s", "tpsa"],
                    title="Chemical-space triage: MW vs LogP",
                )
                st.plotly_chart(fig, width="stretch")
            with filter_col:
                st.plotly_chart(
                    px.histogram(result, x="developability_score", nbins=20, title="Developability distribution"),
                    width="stretch",
                )
            exportable = result.copy()
            for column in exportable.columns:
                if exportable[column].map(lambda value: isinstance(value, (dict, list))).any():
                    exportable[column] = exportable[column].map(lambda value: json.dumps(value, sort_keys=True, default=str))
            downloads = st.columns(2)
            downloads[0].download_button(
                "Download ranked batch profile",
                exportable.to_csv(index=False),
                "discovery_batch_ranked.csv",
                "text/csv",
                width="stretch",
            )
            if isinstance(failure_frame, pd.DataFrame) and not failure_frame.empty:
                st.warning(f"{len(failure_frame):,} molecule(s) failed validation or profiling.")
                smart_dataframe(failure_frame, height=280)
                downloads[1].download_button(
                    "Download failure report",
                    failure_frame.to_csv(index=False),
                    "discovery_batch_failures.csv",
                    "text/csv",
                    width="stretch",
                )
            else:
                downloads[1].success("No failed molecule rows.")

with coverage_tab:
    st.markdown(
        "This matrix prevents descriptor rules from being mistaken for validated biological predictions. "
        "Endpoints marked **not assessed** require a qualified model artifact, applicability-domain definition, validation metrics and versioned provenance before activation."
    )
    reference_payload = profile_dict(profile_admet(examples["Aspirin"]))
    coverage = pd.DataFrame(reference_payload["endpoint_summary"])
    coverage_summary = coverage.groupby(["domain", "status"], dropna=False).size().reset_index(name="endpoints")
    executive_kpis([
        ("Endpoint rows", str(len(coverage)), "Assessed and explicitly unassessed"),
        ("Rule/heuristic outputs", str(int((coverage["status"] != "not assessed").sum())), "Current local capability"),
        ("Not assessed", str(int((coverage["status"] == "not assessed").sum())), "Requires validated endpoint model"),
        ("Qualified endpoint plugins", str(len(ENDPOINT_PLUGINS.endpoints())), "Only qualified plugins can activate model outputs"),
        ("Fake probabilities", "0", "Unavailable biology is not fabricated"),
    ])
    smart_dataframe(coverage, height=600)
    st.plotly_chart(
        px.bar(coverage_summary, x="domain", y="endpoints", color="status", barmode="stack", title="ADMET capability coverage"),
        width="stretch",
    )

# Step 115 module-specific non-chart workspace: admet
from biointel.ui.non_chart_scientific_visuals import render_module_non_chart_panel as _render_step115_module_non_chart
_render_step115_module_non_chart("admet", key_prefix="step115_62_ADMET_Drug_Discovery_admet", expanded=False)

# STEP127_SCIENTIFIC_DEPTH_ADMET
from biointel.step127.ui import render_step127_upgrade_panel as _render_step127_upgrade_panel
_render_step127_upgrade_panel('admet', expanded=False)

# Targeted peak-potential assurance for Genomics, Discovery, Omics, Lab and Translational modules.
from biointel.peak_potential.ui import render_peak_session_footer
render_peak_session_footer(page_key='admet_discovery', title='ADMET Triage & Developability', category='Discovery')

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='admet_discovery', title='ADMET Triage & Developability', category='Discovery')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
