from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel import __version__
from biointel.chemistry.admet import profile_admet, profile_dict
from biointel.chemistry.chemical_space import (
    activity_cliffs,
    butina_clusters,
    chemical_space_embedding,
    similarity_matrix,
)
from biointel.chemistry.molecule_visualization import molecule_png
from biointel.chemistry.standardization import standardize_molecule
from biointel.discovery.admet_plugins import ENDPOINT_PLUGINS
from biointel.discovery.docking import external_docking_readiness, readiness_dict
from biointel.discovery.lead_optimization import (
    assess_patent_evidence,
    assess_synthesis_feasibility,
    optimization_recommendations,
)
from biointel.discovery.lead_optimization import (
    result_dict as lead_result_dict,
)
from biointel.discovery.preparation import preparation_dict, prepare_molecular_states
from biointel.discovery.registry import (
    DEFAULT_PATH as DISCOVERY_DB,
)
from biointel.discovery.registry import (
    add_evidence,
    add_target_assessment,
    create_project,
    export_project_bundle,
    get_project,
    list_compounds,
    list_projects,
    project_snapshot,
    registry_summary,
    save_ranking,
    update_project,
    upsert_compound,
)
from biointel.discovery.target_intelligence import (
    build_target_evidence_profile,
    target_evidence_query_plan,
)
from biointel.discovery.target_intelligence import profile_dict as target_profile_dict
from biointel.discovery.workflow import TARGET_WEIGHT_TEMPLATES, rank_discovery_hits
from biointel.ui.components import scientific_boundary_banner, smart_dataframe, smart_json
from biointel.ui.workflow import read_uploaded_table, render_upload_preflight
from biointel.ui.theme import apply_theme, badge, command_bar, executive_kpis, hero, section_title
from biointel.module_runtime_v207.portfolio_ui import render_step207_portfolio_panel

st.set_page_config(page_title="Discovery Command Center · BioIntel AI", page_icon="🔭", layout="wide")


def _safe_page_link(container, path: str, label: str, icon: str) -> None:
    try:
        container.page_link(path, label=label)
    except (KeyError, RuntimeError):
        container.caption(f"{icon} {label}")


def _flatten_compounds(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    rows = []
    for row in frame.to_dict("records"):
        profile = row.pop("profile", {}) or json.loads(row.pop("profile_json", "{}"))
        row.pop("source", None)
        row.pop("source_json", None)
        rows.append({**row, **profile})
    return pd.DataFrame(rows)


apply_theme()
hero(
    "Discovery Command Center",
    "Persistent target-to-hit projects with evidence-weighted target intelligence, molecular-state preparation, identity-safe compound registration, chemical-space analytics, qualified endpoint gates and reproducible hit ranking.",
    eyebrow=f"BioIntel Discovery {__version__} · Evidence-Aware Workflow",
    chips=["Persistent projects", "Target evidence", "Molecular states", "Chemical space", "Robust ranking", "Reproducibility ZIP"],
)
scientific_boundary_banner(
    source_kind="mixed",
    release_eligible=False,
    message=(
        "Software calculations, provider records and imported evidence are tracked separately. "
        "Potency, selectivity, ADMET, docking, novelty, efficacy and safety remain unvalidated until qualified external evidence is attached."
    ),
)

render_step207_portfolio_panel("Discovery", expanded=False)

projects = list_projects(path=DISCOVERY_DB)
with st.sidebar:
    st.subheader("Discovery project")
    project_options = projects["project_id"].tolist() if not projects.empty else []
    selected_project = st.selectbox(
        "Open project",
        [""] + project_options,
        index=(
            [""] + project_options
        ).index(st.session_state.get("discovery_project_id", ""))
        if st.session_state.get("discovery_project_id", "") in project_options
        else 0,
        format_func=lambda value: (
            "Create or select a project"
            if not value
            else f"{projects.loc[projects['project_id'] == value, 'project_name'].iloc[0]} · {value}"
        ),
    )
    if selected_project:
        st.session_state["discovery_project_id"] = selected_project
    with st.expander("Create project", expanded=not project_options):
        with st.form("create_discovery_project"):
            project_name = st.text_input("Project name", value="New discovery program")
            indication = st.text_input("Indication/disease")
            objective = st.text_area("Objective")
            create = st.form_submit_button("Create persistent project", type="primary")
        if create:
            try:
                project_id = create_project(
                    project_name,
                    indication=indication,
                    objective=objective,
                    path=DISCOVERY_DB,
                )
                st.session_state["discovery_project_id"] = project_id
                st.toast(f"Created {project_id}")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

project_id = str(st.session_state.get("discovery_project_id", ""))
project = None
if project_id:
    try:
        project = get_project(project_id, path=DISCOVERY_DB)
    except KeyError:
        st.session_state.pop("discovery_project_id", None)
        project_id = ""

if project is None:
    st.info("Create or select a persistent Discovery project. Analyses can still be explored on individual pages, but project decisions will not be saved until a project is active.")
    workflow_tab, capability_tab = st.tabs(["Workflow map", "Capability & evidence map"])
    with workflow_tab:
        command_bar("Target → compounds → DTI/structure → developability → hit decision", "Open a project to persist targets, compounds, evidence, rankings and reproducibility artifacts.")
        links = st.columns(4)
        _safe_page_link(links[0], "pages/3_Drug_SMILES_Analyzer.py", "Molecule & similarity", "⚗️")
        _safe_page_link(links[0], "pages/13_ChEMBL_Dataset_Builder.py", "ChEMBL activity data", "🧪")
        _safe_page_link(links[1], "pages/4_DTI_Feature_Builder.py", "DTI features", "🧩")
        _safe_page_link(links[1], "pages/6_DTI_Predictor.py", "DTI predictor", "🎯")
        _safe_page_link(links[2], "pages/61_Structural_Bioinformatics.py", "Structure & pockets", "🧬")
        _safe_page_link(links[2], "pages/63_Pathway_Network_Analysis.py", "Pathway intelligence", "🕸️")
        _safe_page_link(links[3], "pages/62_ADMET_Drug_Discovery.py", "ADMET triage", "💊")
        _safe_page_link(links[3], "pages/85_Provider_Integration_Center.py", "Provider integration", "🌐")
    with capability_tab:
        smart_json({"registry": registry_summary(path=DISCOVERY_DB), "qualified_admet_plugins": ENDPOINT_PLUGINS.endpoints(), "docking": readiness_dict(external_docking_readiness())})
    st.stop()

compound_frame = list_compounds(project_id, path=DISCOVERY_DB)
flat_compounds = _flatten_compounds(compound_frame)
snapshot = project_snapshot(project_id, path=DISCOVERY_DB)
executive_kpis([
    ("Project", project["project_name"], project_id),
    ("Active target", project.get("active_target_id") or "Not set", "Versioned assessments"),
    ("Compounds", str(len(compound_frame)), "Identity-aware registry"),
    ("Evidence", str(len(snapshot["evidence"])), "Checksum-bound records"),
])

workflow_tab, assets_tab, analytics_tab, evidence_tab, capability_tab = st.tabs(["Workflow", "Targets & compounds", "Discovery analytics", "Evidence & export", "Capability map"])

with workflow_tab:
    command_bar(
        "Target → known ligands → molecular states → DTI/structure → ADMET → ranked hit decision",
        "Every persistent record stores source context, software version, checksums and decision history.",
    )
    stages = [
        {"Stage": "1. Target intelligence", "Local capability": "Evidence register, source-quality/confidence/recency aggregation, custom templates and gates", "External evidence": "Genetics, disease biology, expression, safety and experimental validation", "Destination": "Target intelligence / Pathway / Protein Annotation"},
        {"Stage": "2. Activity evidence", "Local capability": "ChEMBL pagination, assay context, component protection, replicate/conflict aggregation", "External evidence": "Official records, licences, releases and manual assay review", "Destination": "ChEMBL Builder / Provider Center"},
        {"Stage": "3. Molecular preparation", "Local capability": "Original form, parent, tautomer/stereo ensembles and ionizable-group warnings", "External evidence": "Assay pH, pKa/microspecies and correct stereochemical form", "Destination": "Compound Project / SMILES Analyzer"},
        {"Stage": "4. Screening", "Local capability": "Five fingerprint families, clustering, DTI schema checks and model release gates", "External evidence": "Qualified DTI model, independent validation and experimental potency", "Destination": "Chemical Space / DTI"},
        {"Stage": "5. Structure", "Local capability": "Structure QC, ligand-defined pockets, geometry hotspots and docking qualification gate", "External evidence": "Prepared structures, qualified protocol and expert pose review", "Destination": "Structural Bioinformatics"},
        {"Stage": "6. Developability", "Local capability": "Rule-based score plus qualified endpoint-plugin interface", "External evidence": "Validated ADME/tox model or experiment", "Destination": "ADMET"},
        {"Stage": "7. Decision", "Local capability": "Missing-safe robust ranking, Pareto diagnostics, evidence completeness and versioned exports", "External evidence": "Selectivity, novelty/IP, synthesis feasibility and prospective assay results", "Destination": "Hit Ranking / Evidence Bundle"},
    ]
    smart_dataframe(stages, height=520)
    links = st.columns(4)
    _safe_page_link(links[0], "pages/13_ChEMBL_Dataset_Builder.py", "Activity data", "🧪")
    _safe_page_link(links[0], "pages/3_Drug_SMILES_Analyzer.py", "Molecule analysis", "⚗️")
    _safe_page_link(links[1], "pages/4_DTI_Feature_Builder.py", "DTI features", "🧩")
    _safe_page_link(links[1], "pages/6_DTI_Predictor.py", "DTI prediction", "🎯")
    _safe_page_link(links[2], "pages/61_Structural_Bioinformatics.py", "Structure & docking gate", "🧬")
    _safe_page_link(links[2], "pages/63_Pathway_Network_Analysis.py", "Pathways", "🕸️")
    _safe_page_link(links[3], "pages/62_ADMET_Drug_Discovery.py", "ADMET", "💊")
    _safe_page_link(links[3], "pages/74_DTI_Validation_Evidence_Center.py", "DTI validation", "🛡️")

with assets_tab:
    view = st.selectbox("Workspace view", ['Target intelligence', 'Compound project'], key="discovery_assets_view")
    if view == 'Target intelligence':
        st.markdown("Import evidence rows or build a transparent manual evidence register. Scores are confidence-adjusted and can be blocked by hard gates.")
        template = st.selectbox("Indication weighting template", list(TARGET_WEIGHT_TEMPLATES), index=0)
        evidence_upload = st.file_uploader("Optional target-evidence CSV", type=["csv", "tsv", "xlsx", "xlsm"], help="Required: dimension, score. Optional: confidence, source_type, source, source_id, evidence_date, notes.")
        render_upload_preflight(evidence_upload, key="discovery_target_evidence", allowed_extensions=["csv", "tsv", "xlsx", "xlsm"], soft_limit_mb=20, hard_limit_mb=150)
        if evidence_upload is not None:
            evidence_rows = read_uploaded_table(evidence_upload)
            smart_dataframe(evidence_rows, height=260)
        else:
            evidence_rows = pd.DataFrame()
        with st.form("target_evidence_form"):
            target_id = st.text_input("Target identifier", value=project.get("active_target_id") or "PTGS2")
            indication_value = st.text_input("Indication", value=project.get("indication", ""))
            cols = st.columns(3)
            values = {
                "disease_relevance": cols[0].slider("Disease relevance", 0, 100, 70),
                "genetic_evidence": cols[1].slider("Genetic evidence", 0, 100, 55),
                "pathway_evidence": cols[2].slider("Pathway evidence", 0, 100, 70),
                "tractability": cols[0].slider("Tractability", 0, 100, 75),
                "safety_window": cols[1].slider("Safety window", 0, 100, 50),
                "experimental_validation": cols[2].slider("Experimental validation", 0, 100, 40),
            }
            confidence = st.slider("Manual evidence confidence", 0, 100, 50)
            gate_cols = st.columns(3)
            min_disease = gate_cols[0].number_input("Disease-relevance gate", 0, 100, 0)
            min_tractability = gate_cols[1].number_input("Tractability gate", 0, 100, 0)
            min_safety = gate_cols[2].number_input("Safety gate", 0, 100, 0)
            score_target = st.form_submit_button("Build and save target profile", type="primary", width="stretch")
        with st.expander("Official-source evidence acquisition plan", expanded=False):
            smart_dataframe(
                target_evidence_query_plan(target_id, indication_value),
                height=360,
            )
            st.caption(
                "This is a query and evidence-completeness plan—not retrieved evidence. "
                "Provider records must be imported, versioned, checksum-bound and reviewed."
            )
        if score_target:
            try:
                if evidence_rows.empty:
                    evidence_rows = pd.DataFrame([
                        {"dimension": name, "score": score, "confidence": confidence / 100, "source_type": "expert_opinion", "source": "manual project assessment", "notes": "User supplied"}
                        for name, score in values.items()
                    ])
                profile = build_target_evidence_profile(
                    target_id,
                    evidence_rows,
                    indication=indication_value,
                    template=template,
                    hard_gates={"disease_relevance": min_disease, "tractability": min_tractability, "safety_window": min_safety},
                )
                payload = target_profile_dict(profile)
                add_target_assessment(project_id, target_id=target_id, scoring=payload, evidence=profile.evidence_register, path=DISCOVERY_DB)
                update_project(project_id, indication=indication_value, active_target_id=target_id, path=DISCOVERY_DB)
                st.session_state["target_profile"] = payload
                st.toast("Target profile saved")
            except Exception as exc:
                st.error(str(exc))
        target_payload = st.session_state.get("target_profile")
        if target_payload:
            executive_kpis([
                ("Target", target_payload["target_id"], "Evidence register"),
                ("Raw score", f"{target_payload['total_score']:.1f}/100", template),
                ("Confidence-adjusted", f"{target_payload['confidence_adjusted_score']:.1f}/100", f"Evidence confidence {target_payload['evidence_confidence']:.1f}%"),
                ("Tier", target_payload["priority_tier"], "Hard gates enforced"),
            ])
            plot = pd.DataFrame({"Dimension": [key.replace("_", " ").title() for key in target_payload["dimension_scores"]], "Score": list(target_payload["dimension_scores"].values()), "Confidence": list(target_payload["dimension_confidence"].values())})
            st.plotly_chart(px.bar(plot, x="Dimension", y=["Score", "Confidence"], barmode="group", range_y=[0, 100], title="Evidence strength and confidence"), width="stretch")
            for item in target_payload.get("conflicts", []):
                st.warning(item)
            for item in target_payload.get("gate_failures", []):
                st.error(item)
            with st.expander("Complete target profile"):
                smart_json(target_payload)
    elif view == 'Compound project':
        st.markdown("Every candidate retains submitted form, standardized parent, identity keys, molecular-state context and duplicate decision.")
        with st.form("persistent_compound_form"):
            c1, c2 = st.columns([1, 2])
            compound_id = c1.text_input("Compound ID/name", value=f"candidate_{len(compound_frame) + 1:03d}")
            compound_smiles = c2.text_input("SMILES", value=str(st.session_state.get("discovery_smiles", "CC(=O)OC1=CC=CC=C1C(=O)O")))
            options = st.columns(3)
            preparation_mode = options[0].selectbox("Preparation mode", ["neutral_parent", "submitted_form", "tautomer_ensemble", "stereoisomer_ensemble", "assay_context", "physiological_context"])
            requested_ph = options[1].number_input("Assay pH", 0.0, 14.0, 7.4, 0.1, disabled=preparation_mode not in {"assay_context", "physiological_context"})
            duplicate_policy = options[2].selectbox("Duplicate policy", ["merge_exact", "reject_exact", "keep_separate", "merge_connectivity"])
            add_compound = st.form_submit_button("Prepare, profile and save candidate", type="primary", width="stretch")
        if add_compound:
            try:
                prep = prepare_molecular_states(compound_smiles, mode=preparation_mode, ph=requested_ph if preparation_mode in {"assay_context", "physiological_context"} else None)
                profile = profile_dict(profile_admet(prep.standardized_parent_smiles))
                profile["molecular_preparation"] = preparation_dict(prep)
                result = upsert_compound(
                    project_id,
                    compound_id=compound_id,
                    original_smiles=compound_smiles,
                    standardized_smiles=profile["standardized_smiles"],
                    inchikey=profile.get("inchikey"),
                    profile=profile,
                    source={"entry": "Discovery Command Center", "preparation_mode": preparation_mode, "assay_ph": requested_ph},
                    duplicate_policy=duplicate_policy,
                    path=DISCOVERY_DB,
                )
                st.session_state["latest_compound_profile"] = profile
                st.toast(f"Candidate {result['action']}")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
        compound_frame = list_compounds(project_id, path=DISCOVERY_DB)
        flat_compounds = _flatten_compounds(compound_frame)
        if compound_frame.empty:
            st.info("No compounds registered in this project.")
        else:
            latest = flat_compounds.iloc[0]
            left, right = st.columns([1, 1.8])
            with left:
                try:
                    mol, _ = standardize_molecule(str(latest["standardized_smiles"]))
                    st.image(molecule_png(mol), caption=str(latest["compound_id"]), width="stretch")
                except Exception:
                    pass
            with right:
                executive_kpis([
                    ("Candidate", latest["compound_id"], "Latest updated"),
                    ("Rule score", f"{int(latest['developability_score'])}/100", "Not a probability"),
                    ("Risk", str(latest["risk_level"]).title(), "Rule-based triage"),
                    ("Identity", str(latest.get("inchikey") or "Unavailable"), "Full stereochemical InChIKey"),
                ])
                st.code(str(latest["standardized_smiles"]), language=None)
            display = ["compound_id", "standardized_smiles", "inchikey", "connectivity_key", "developability_score", "risk_score", "risk_level", "qed", "esol_style_log_s", "aggregation_risk", "updated_at_utc"]
            smart_dataframe(flat_compounds[[column for column in display if column in flat_compounds.columns]], height=480)
            action_cols = st.columns(4)
            if action_cols[0].button("Open latest in SMILES Analyzer", width="stretch"):
                st.session_state["imported_smiles"] = latest["standardized_smiles"]
                st.switch_page("pages/3_Drug_SMILES_Analyzer.py")
            if action_cols[1].button("Open latest in ADMET", width="stretch"):
                st.session_state["admet_smiles"] = latest["standardized_smiles"]
                st.switch_page("pages/62_ADMET_Drug_Discovery.py")
            if action_cols[2].button("Send latest to DTI", width="stretch"):
                st.session_state["dti_smiles"] = latest["standardized_smiles"]
                st.switch_page("pages/4_DTI_Feature_Builder.py")
            if action_cols[3].button("Open structure workflow", width="stretch"):
                st.switch_page("pages/61_Structural_Bioinformatics.py")

with analytics_tab:
    view = st.selectbox("Workspace view", ['Chemical space', 'Hit ranking', 'Lead optimization & IP'], key="discovery_analytics_view")
    if view == 'Chemical space':
        if len(flat_compounds) < 2:
            st.info("Register at least two compounds for chemical-space analytics.")
        else:
            fingerprint_kind = st.selectbox("Fingerprint family", ["Morgan", "MACCS", "RDKit", "AtomPair", "Torsion"])
            threshold = st.slider("Butina clustering similarity threshold", 0.30, 0.95, 0.65, 0.05)
            try:
                matrix = similarity_matrix(flat_compounds, fingerprint_kind=fingerprint_kind)
                clusters = butina_clusters(flat_compounds, fingerprint_kind=fingerprint_kind, similarity_threshold=threshold)
                embedding = chemical_space_embedding(flat_compounds, fingerprint_kind=fingerprint_kind)
                space = flat_compounds.merge(clusters, on="compound_id", how="left").merge(embedding.drop(columns=["variance_explained"], errors="ignore"), on="compound_id", how="left")
                st.plotly_chart(px.imshow(matrix, zmin=0, zmax=1, aspect="auto", title=f"{fingerprint_kind} Tanimoto similarity matrix"), width="stretch")
                st.plotly_chart(px.scatter(space, x="PC1", y="PC2", color="cluster_id", hover_name="compound_id", size="developability_score" if "developability_score" in space else None, title="Chemical-space PCA and Butina clusters"), width="stretch")
                smart_dataframe(space[[column for column in ["compound_id", "cluster_id", "cluster_size", "PC1", "PC2", "scaffold_smiles"] if column in space.columns]], height=360)
                if "p_activity" in flat_compounds.columns:
                    cliffs = activity_cliffs(flat_compounds)
                    section_title("Activity cliffs", "↯")
                    smart_dataframe(cliffs, height=300)
            except Exception as exc:
                st.error(f"Chemical-space analysis failed: {exc}")
    elif view == 'Hit ranking':
        if flat_compounds.empty:
            st.info("Add project compounds before ranking.")
        else:
            numeric_columns = [column for column in flat_compounds.columns if pd.api.types.is_numeric_dtype(flat_compounds[column])]
            default_benefits = [column for column in ["developability_score", "qed", "p_activity", "selectivity_score", "target_confidence"] if column in numeric_columns]
            default_costs = [column for column in ["risk_score", "synthetic_accessibility_heuristic", "off_target_risk", "estimated_cost"] if column in numeric_columns]
            benefits = st.multiselect("Benefits — higher is better", numeric_columns, default=default_benefits)
            costs = st.multiselect("Costs — lower is better", [column for column in numeric_columns if column not in benefits], default=default_costs)
            method_cols = st.columns(3)
            method = method_cols[0].selectbox("Normalization", ["robust_percentile", "winsorized_minmax", "minmax", "zscore"])
            missing_penalty = method_cols[1].slider("Missing-evidence penalty", 0.0, 1.0, 0.25, 0.05)
            minimum_completeness = method_cols[2].slider("Minimum completeness", 0.0, 1.0, 0.60, 0.05)
            objectives = benefits + costs
            weights = {}
            if objectives:
                columns = st.columns(min(4, len(objectives)))
                for index, column in enumerate(objectives):
                    weights[column] = columns[index % len(columns)].number_input(column.replace("_", " ").title(), 0.0, 1.0, round(1 / len(objectives), 2), 0.05, key=f"w_{column}")
            if st.button("Rank and persist hit list", type="primary", width="stretch", disabled=not objectives):
                try:
                    ranked = rank_discovery_hits(
                        flat_compounds,
                        id_column="compound_id",
                        benefit_columns={column: weights[column] for column in benefits},
                        cost_columns={column: weights[column] for column in costs},
                        method=method,
                        missing_penalty=missing_penalty,
                        minimum_completeness=minimum_completeness,
                    )
                    ranking_id = save_ranking(project_id, result=ranked, method=method, parameters={"benefits": {column: weights[column] for column in benefits}, "costs": {column: weights[column] for column in costs}, "missing_penalty": missing_penalty, "minimum_completeness": minimum_completeness}, path=DISCOVERY_DB)
                    st.session_state["discovery_ranked_hits"] = ranked
                    st.toast(f"Saved ranking {ranking_id}")
                except Exception as exc:
                    st.error(str(exc))
            ranked = st.session_state.get("discovery_ranked_hits")
            if isinstance(ranked, pd.DataFrame) and not ranked.empty:
                smart_dataframe(ranked[[column for column in ["hit_rank", "compound_id", "multi_objective_score", "objective_completeness", "missing_objective_count", "pareto_front", "ranking_eligible", "ranking_warning"] + objectives if column in ranked.columns]], height=520)
                st.plotly_chart(px.bar(ranked.head(30).sort_values("multi_objective_score"), x="multi_objective_score", y="compound_id", color="pareto_front", orientation="h", title="Robust multi-objective hit ranking"), width="stretch")
                st.download_button("Download ranked hit list", ranked.to_csv(index=False), "ranked_discovery_hits.csv", "text/csv", width="stretch")
    elif view == 'Lead optimization & IP':
        if flat_compounds.empty:
            st.info("Add at least one project compound before lead-optimization review.")
        else:
            selected_id = st.selectbox("Candidate", flat_compounds["compound_id"].tolist(), key="lead_candidate")
            candidate = flat_compounds.loc[flat_compounds["compound_id"] == selected_id].iloc[0].to_dict()
            section_title("Liability-driven optimization plan", "↗")
            smart_dataframe(optimization_recommendations(candidate), height=340)
            with st.form("synthesis_feasibility_form"):
                cols = st.columns(3)
                estimated_steps = cols[0].number_input("Estimated route steps; 0 = unknown", 0, 100, 0)
                available_blocks = cols[1].selectbox("Commercial building blocks", ["unknown", "yes", "no"])
                hazardous_steps = cols[2].number_input("Hazardous steps", 0, 20, 0)
                protecting_groups = cols[0].number_input("Protecting-group operations", 0, 20, 0)
                precedent = cols[1].checkbox("Synthetic precedent documented")
                assess_synthesis = st.form_submit_button("Assess route evidence", type="primary")
            if assess_synthesis:
                synthesis = assess_synthesis_feasibility(
                    str(candidate["standardized_smiles"]),
                    estimated_steps=(int(estimated_steps) if estimated_steps > 0 else None),
                    commercially_available_building_blocks=(True if available_blocks == "yes" else False if available_blocks == "no" else None),
                    hazardous_steps=int(hazardous_steps),
                    protecting_groups=int(protecting_groups),
                    precedent_documented=precedent,
                )
                synthesis_payload = lead_result_dict(synthesis)
                st.session_state["synthesis_assessment"] = synthesis_payload
                add_evidence(project_id, entity_type="compound", entity_id=selected_id, evidence_type="synthesis_feasibility", source="local structured assessment", confidence=0.5, payload=synthesis_payload, path=DISCOVERY_DB)
            if st.session_state.get("synthesis_assessment"):
                smart_json(st.session_state["synthesis_assessment"])

            section_title("Patent/FTO evidence gate", "§")
            with st.form("patent_evidence_form"):
                checks = st.columns(4)
                exact = checks[0].checkbox("Exact structure search")
                substructure = checks[1].checkbox("Substructure/Markush search")
                similarity = checks[2].checkbox("Similarity search")
                target_search = checks[3].checkbox("Target/sequence search")
                jurisdictions = st.multiselect("Jurisdictions reviewed", ["WO/PCT", "US", "EP", "CN", "JP", "IN", "Other"])
                family = st.checkbox("Patent family and legal status reviewed")
                claims = st.checkbox("Independent claims reviewed")
                legal_reviewer = st.text_input("Qualified legal reviewer")
                assess_patent = st.form_submit_button("Evaluate patent-evidence completeness")
            if assess_patent:
                patent = assess_patent_evidence(
                    exact_structure_search=exact,
                    substructure_search=substructure,
                    similarity_search=similarity,
                    sequence_or_target_search=target_search,
                    jurisdiction_coverage=jurisdictions,
                    family_status_reviewed=family,
                    claims_reviewed=claims,
                    legal_reviewer=legal_reviewer,
                )
                patent_payload = lead_result_dict(patent)
                st.session_state["patent_assessment"] = patent_payload
                add_evidence(project_id, entity_type="compound", entity_id=selected_id, evidence_type="patent_fto_review", source="user-documented legal review", confidence=0.5 if not patent.complete else 0.9, payload=patent_payload, path=DISCOVERY_DB)
            if st.session_state.get("patent_assessment"):
                smart_json(st.session_state["patent_assessment"])
                st.warning("This completeness gate is not a legal opinion or freedom-to-operate clearance.")

with evidence_tab:
    st.markdown("Attach target, compound, assay, model, docking, synthesis, patent-search or wet-lab evidence. Every payload receives a SHA-256 digest.")
    with st.form("add_discovery_evidence"):
        cols = st.columns(3)
        entity_type = cols[0].selectbox("Entity type", ["project", "target", "compound", "assay", "model", "structure", "ranking"])
        entity_id = cols[1].text_input("Entity ID", value=project.get("active_target_id") or project_id)
        evidence_type = cols[2].text_input("Evidence type", value="review_note")
        source = st.text_input("Source/provider")
        source_id = st.text_input("Source record/release ID")
        confidence_value = st.slider("Evidence confidence", 0.0, 1.0, 0.7, 0.05)
        payload_text = st.text_area("Evidence payload (JSON or plain notes)", value="{}")
        save_evidence = st.form_submit_button("Save evidence", type="primary")
    if save_evidence:
        try:
            try:
                payload = json.loads(payload_text)
                if not isinstance(payload, dict):
                    payload = {"value": payload}
            except json.JSONDecodeError:
                payload = {"notes": payload_text}
            evidence_id = add_evidence(project_id, entity_type=entity_type, entity_id=entity_id, evidence_type=evidence_type, source=source or "local", source_id=source_id, confidence=confidence_value, payload=payload, path=DISCOVERY_DB)
            st.toast(f"Saved {evidence_id}")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))
    latest_snapshot = project_snapshot(project_id, path=DISCOVERY_DB)
    smart_dataframe(pd.DataFrame(latest_snapshot["evidence"]), height=380)
    bundle = export_project_bundle(project_id, path=DISCOVERY_DB)
    st.download_button("Download complete reproducibility bundle", bundle, f"{project_id}_discovery_evidence.zip", "application/zip", width="stretch")
    st.caption(f"Snapshot SHA-256: {latest_snapshot['snapshot_sha256']}")

with capability_tab:
    docking = readiness_dict(external_docking_readiness())
    capability_rows = [
        {"Capability": "Persistent discovery projects", "Status": "Implemented", "Evidence": "SQLite foreign keys, events and SHA-256 bundle", "Boundary": "External results must be imported"},
        {"Capability": "Target intelligence", "Status": "Implemented", "Evidence": "Source-quality/confidence/recency weighted profile", "Boundary": "Does not generate genetics or experiments"},
        {"Capability": "Molecular preparation", "Status": "Implemented", "Evidence": "Original/parent/tautomer/stereo states", "Boundary": "Exact pH microspecies need qualified pKa model"},
        {"Capability": "Chemical-space analytics", "Status": "Implemented", "Evidence": "Morgan/MACCS/RDKit/AtomPair/Torsion, clusters, PCA, cliffs", "Boundary": "Similarity does not prove activity"},
        {"Capability": "DTI", "Status": "Release-gated", "Evidence": "Schema and validation center", "Boundary": "Bundled synthetic models are not experimental evidence"},
        {"Capability": "ADMET", "Status": "Plugin-qualified", "Evidence": f"{len(ENDPOINT_PLUGINS.endpoints())} qualified endpoint plugin(s)", "Boundary": "Uninstalled endpoints remain not assessed"},
        {"Capability": "Docking", "Status": "Qualification-gated", "Evidence": "Tool detection and redocking/enrichment gate", "Boundary": "No validated docking claim without protocol evidence"},
        {"Capability": "Hit ranking", "Status": "Implemented", "Evidence": "Missing-safe robust scaling, penalties, Pareto front", "Boundary": "Rank depends on evidence quality"},
        {"Capability": "Patent/FTO", "Status": "Evidence import only", "Evidence": "Source and checksum registry", "Boundary": "Legal opinion remains external"},
        {"Capability": "Prospective validation", "Status": "Evidence import only", "Evidence": "Immutable evidence record", "Boundary": "Wet-lab outcome cannot be fabricated"},
    ]
    smart_dataframe(capability_rows, height=540)
    smart_json({"registry": registry_summary(path=DISCOVERY_DB), "qualified_admet_plugins": ENDPOINT_PLUGINS.endpoints(), "docking_readiness": docking})
    badge("● Truthful scientific boundary enforcement active", "success")

# STEP127_SCIENTIFIC_DEPTH_DISCOVERY_COMMAND
from biointel.step127.ui import render_step127_upgrade_panel as _render_step127_upgrade_panel
_render_step127_upgrade_panel('discovery_command', expanded=False)

# Targeted peak-potential assurance for Genomics, Discovery, Omics, Lab and Translational modules.
from biointel.peak_potential.ui import render_peak_session_footer
render_peak_session_footer(page_key='discovery_command_center', title='Discovery Command Center', category='Discovery')

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='discovery_command_center', title='Discovery Command Center', category='Discovery')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
