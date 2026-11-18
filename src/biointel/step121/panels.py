from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from biointel.ui.components import metric_cards, smart_dataframe, smart_json
from biointel.ui.theme import insight_callout, section_title
from biointel.ui.workflow import read_uploaded_table, render_upload_preflight

from .automl import resource_bounded_automl
from .citations import build_citation_workspace, export_bibtex, export_ris
from .evidence import build_evidence_workspace
from .family_genetics import analyse_family_variants
from .microbiology_isolate import analyse_isolate, parse_fasta_text
from .model_assurance import run_assurance_suite
from .organoid import analyse_organoid_experiment


def _demo_family() -> tuple[pd.DataFrame, pd.DataFrame]:
    pedigree = pd.DataFrame(
        [
            ["F1", "FATHER", "0", "0", 1, 1],
            ["F1", "MOTHER", "0", "0", 2, 1],
            ["F1", "CHILD", "FATHER", "MOTHER", 1, 2],
            ["F1", "SIBLING", "FATHER", "MOTHER", 2, 1],
        ],
        columns=["family_id", "individual_id", "father_id", "mother_id", "sex", "phenotype"],
    )
    variants = pd.DataFrame(
        [
            ["1:100:A:G", "GENE1", "FATHER", "0/0", 40, 0.00, 0.0001],
            ["1:100:A:G", "GENE1", "MOTHER", "0/0", 38, 0.00, 0.0001],
            ["1:100:A:G", "GENE1", "CHILD", "0/1", 42, 0.46, 0.0001],
            ["1:100:A:G", "GENE1", "SIBLING", "0/0", 36, 0.00, 0.0001],
            ["2:200:C:T", "GENE2", "FATHER", "0/1", 34, 0.48, 0.002],
            ["2:200:C:T", "GENE2", "MOTHER", "0/0", 40, 0.00, 0.002],
            ["2:200:C:T", "GENE2", "CHILD", "0/1", 44, 0.51, 0.002],
            ["2:200:C:T", "GENE2", "SIBLING", "0/0", 32, 0.00, 0.002],
            ["2:260:G:A", "GENE2", "FATHER", "0/0", 35, 0.00, 0.001],
            ["2:260:G:A", "GENE2", "MOTHER", "0/1", 39, 0.44, 0.001],
            ["2:260:G:A", "GENE2", "CHILD", "0/1", 41, 0.49, 0.001],
            ["2:260:G:A", "GENE2", "SIBLING", "0/0", 30, 0.00, 0.001],
        ],
        columns=["variant_id", "gene", "sample_id", "genotype", "depth", "alt_fraction", "population_af"],
    )
    return pedigree, variants


def render_family_genetics_upgrade(*, key_prefix: str = "step121_family") -> None:
    with st.expander("Step 121 · Family identity, inheritance and segregation workbench", expanded=True):
        st.caption("PED/VCF-style family QC, Mendelian errors, de-novo candidates, compound-heterozygous candidates, kinship proxies and transparent segregation scoring.")
        source = st.radio("Input source", ["Deterministic demonstration", "Upload tables"], horizontal=True, key=f"{key_prefix}_source")
        if source == "Upload tables":
            ped_upload = st.file_uploader("Pedigree CSV/TSV", type=["csv", "tsv"], key=f"{key_prefix}_ped")
            variant_upload = st.file_uploader("Long variant-genotype CSV/TSV", type=["csv", "tsv"], key=f"{key_prefix}_variants")
            render_upload_preflight(ped_upload, key=f"{key_prefix}_ped_preflight", allowed_extensions=["csv", "tsv"], soft_limit_mb=25, hard_limit_mb=200)
            render_upload_preflight(variant_upload, key=f"{key_prefix}_var_preflight", allowed_extensions=["csv", "tsv"], soft_limit_mb=50, hard_limit_mb=500)
            if ped_upload is None or variant_upload is None:
                st.info("Upload both tables to run the family workflow.")
                return
            pedigree = read_uploaded_table(ped_upload)
            variants = read_uploaded_table(variant_upload)
        else:
            pedigree, variants = _demo_family()
        with st.expander("Input preview", expanded=False):
            st.markdown("**Pedigree**")
            smart_dataframe(pedigree, key=f"{key_prefix}_ped_preview")
            st.markdown("**Variant genotypes**")
            smart_dataframe(variants, key=f"{key_prefix}_var_preview")
        c1, c2, c3 = st.columns(3)
        min_depth = c1.number_input("Minimum child depth", 0.0, 500.0, 10.0, 1.0, key=f"{key_prefix}_depth")
        min_vaf = c2.number_input("Minimum child VAF", 0.0, 1.0, 0.20, 0.01, key=f"{key_prefix}_vaf")
        max_af = c3.number_input("Maximum population AF", 0.0, 1.0, 0.01, 0.001, format="%.4f", key=f"{key_prefix}_af")
        if st.button("Run family genetics analysis", type="primary", key=f"{key_prefix}_run"):
            try:
                st.session_state[f"{key_prefix}_result"] = analyse_family_variants(
                    pedigree,
                    variants,
                    min_child_depth=min_depth,
                    min_child_alt_fraction=min_vaf,
                    max_population_af=max_af,
                )
            except Exception as exc:
                st.error(f"Family analysis failed safely: {exc}")
        result = st.session_state.get(f"{key_prefix}_result")
        if result is None:
            return
        metric_cards(
            [
                ("Pedigree issues", int((result.pedigree_qc["severity"] != "pass").sum()), None),
                ("Trio observations", len(result.inheritance), None),
                ("De-novo candidates", len(result.de_novo_candidates), "Requires read review"),
                ("Compound-het pairs", len(result.compound_heterozygous), "Unphased candidates"),
            ]
        )
        tabs = st.tabs(["Pedigree/trio QC", "Inheritance", "Kinship", "Segregation", "Release package"])
        with tabs[0]:
            smart_dataframe(result.pedigree_qc, key=f"{key_prefix}_ped_qc")
            smart_dataframe(result.trio_qc, key=f"{key_prefix}_trio_qc")
        with tabs[1]:
            smart_dataframe(result.inheritance, key=f"{key_prefix}_inheritance")
            st.markdown("**Filtered de-novo candidates**")
            smart_dataframe(result.de_novo_candidates, key=f"{key_prefix}_denovo")
            st.markdown("**Compound-heterozygous candidates**")
            smart_dataframe(result.compound_heterozygous, key=f"{key_prefix}_compound")
        with tabs[2]:
            smart_dataframe(result.kinship, key=f"{key_prefix}_kinship")
        with tabs[3]:
            smart_dataframe(result.segregation, key=f"{key_prefix}_segregation")
        with tabs[4]:
            smart_json(result.release_gate, title="Release gate", key=f"{key_prefix}_gate")
            smart_json(result.manifest, title="Run manifest", key=f"{key_prefix}_manifest")
            st.download_button("Download inheritance table", result.inheritance.to_csv(index=False), "family_inheritance.csv", "text/csv", key=f"{key_prefix}_download")
        insight_callout("Evidence boundary", result.release_gate["boundary"], "warning")


def _demo_assurance(seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    n = 320
    age = rng.normal(50, 14, n)
    biomarker = rng.normal(0, 1, n)
    batch = rng.choice(["B1", "B2", "B3"], n)
    subgroup = rng.choice(["Group A", "Group B"], n, p=[0.65, 0.35])
    logit = -0.4 + 0.035 * (age - 50) + 1.2 * biomarker + 0.45 * (subgroup == "Group B") + rng.normal(0, 0.6, n)
    probability = 1 / (1 + np.exp(-logit))
    target = rng.binomial(1, probability)
    return pd.DataFrame({"age": age, "biomarker": biomarker, "batch": batch, "subgroup": subgroup, "outcome": target})


def render_model_assurance_upgrade(*, key_prefix: str = "step121_assurance") -> None:
    with st.expander("Step 121 · Explainability stability, subgroup and OOD assurance", expanded=True):
        st.caption("Leakage-safe held-out assurance with calibration, subgroup disparity, robust OOD scores, bootstrap explanation stability and local linear counterfactual candidates.")
        upload = st.file_uploader("Optional labelled CSV/TSV", type=["csv", "tsv"], key=f"{key_prefix}_upload")
        frame = read_uploaded_table(upload) if upload is not None else _demo_assurance()
        columns = list(frame.columns)
        target = st.selectbox("Target column", columns, index=columns.index("outcome") if "outcome" in columns else len(columns) - 1, key=f"{key_prefix}_target")
        group_options = ["None"] + [column for column in columns if column != target]
        group = st.selectbox("Optional subgroup column", group_options, index=group_options.index("subgroup") if "subgroup" in group_options else 0, key=f"{key_prefix}_group")
        task = st.selectbox("Task", ["Auto", "classification", "regression"], key=f"{key_prefix}_task")
        repeats = st.slider("Explanation bootstrap repeats", 3, 20, 8, key=f"{key_prefix}_repeats")
        if st.button("Run model assurance suite", type="primary", key=f"{key_prefix}_run"):
            try:
                st.session_state[f"{key_prefix}_result"] = run_assurance_suite(
                    frame,
                    target_column=target,
                    group_column=None if group == "None" else group,
                    task=None if task == "Auto" else task,
                    stability_repeats=repeats,
                )
            except Exception as exc:
                st.error(f"Assurance analysis failed safely: {exc}")
        result = st.session_state.get(f"{key_prefix}_result")
        if result is None:
            smart_dataframe(frame.head(100), key=f"{key_prefix}_preview")
            return
        tabs = st.tabs(["Performance", "Calibration/subgroups", "OOD", "Explanations", "Governance"])
        with tabs[0]:
            smart_dataframe(result.metrics, key=f"{key_prefix}_metrics")
        with tabs[1]:
            smart_dataframe(result.calibration, key=f"{key_prefix}_calibration")
            smart_dataframe(result.subgroup_audit, key=f"{key_prefix}_subgroups")
        with tabs[2]:
            smart_dataframe(result.ood_scores, key=f"{key_prefix}_ood")
        with tabs[3]:
            smart_dataframe(result.feature_effects, key=f"{key_prefix}_effects")
            smart_dataframe(result.explanation_stability, key=f"{key_prefix}_stability")
            smart_dataframe(result.counterfactuals, key=f"{key_prefix}_counterfactuals")
        with tabs[4]:
            smart_json(result.release_gate, title="Model assurance gate", key=f"{key_prefix}_gate")
            smart_json(result.manifest, title="Assurance manifest", key=f"{key_prefix}_manifest")
        insight_callout("Causality safeguard", result.release_gate["boundary"], "warning")


def _demo_isolate_inputs() -> tuple[str, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    locus_a = "ATGCGTACGTAGCTAGCTAGCGGATCCGATCGATCGATCGATCG"
    locus_b = "TTGCAACCGGTTAACCGGTTAACCGGTTAGCTAGCTAGCTAGCTA"
    amr = "GGTACCGGTACCGGTACCGGTACCGGTACCGGTACC"
    vf = "AACCTTGGAACCTTGGAACCTTGGAACCTTGGAA"
    fasta = f">contig1\n{locus_a * 5}{amr * 3}\n>contig2\n{locus_b * 5}{vf * 3}\n"
    taxonomy = pd.DataFrame(
        [
            ["Demo bacterium A", locus_a * 4 + locus_b * 4 + amr],
            ["Demo bacterium B", "CCCCGGGGAAAATTTT" * 30],
        ],
        columns=["taxon", "sequence"],
    )
    alleles = pd.DataFrame(
        [["abc", "1", locus_a], ["abc", "2", "C" * len(locus_a)], ["xyz", "4", locus_b], ["xyz", "5", "A" * len(locus_b)]],
        columns=["locus", "allele", "sequence"],
    )
    profiles = pd.DataFrame([["ST-DEMO", "1", "4"], ["ST-OTHER", "2", "5"]], columns=["sequence_type", "abc", "xyz"])
    genes = pd.DataFrame(
        [["demoA", amr, "AMR", "drugx", "demo-2026.1"], ["demoV", vf, "virulence", "", "demo-2026.1"]],
        columns=["gene", "sequence", "category", "phenotype", "database_release"],
    )
    phenotype = pd.DataFrame([["drugx", "resistant"], ["drugy", "susceptible"]], columns=["drug", "phenotype"])
    return fasta, taxonomy, alleles, profiles, genes, phenotype


def render_microbiology_isolate_upgrade(*, key_prefix: str = "step121_microbiology") -> None:
    with st.expander("Step 121 · Isolate QC, typing, AMR/VF and concordance screen", expanded=True):
        st.caption("Bounded local isolate workflow with assembly QC, candidate taxonomy, MLST profiles, versioned gene-catalog screening, contamination flags and phenotype-genotype review.")
        demo_fasta, demo_taxonomy, demo_alleles, demo_profiles, demo_genes, demo_pheno = _demo_isolate_inputs()
        fasta_text = st.text_area("Isolate assembly FASTA", demo_fasta, height=180, key=f"{key_prefix}_fasta")
        use_demo_refs = st.checkbox("Use bundled deterministic demonstration reference tables", value=True, key=f"{key_prefix}_demo_refs")
        if use_demo_refs:
            taxonomy, alleles, profiles, genes, phenotype = demo_taxonomy, demo_alleles, demo_profiles, demo_genes, demo_pheno
        else:
            uploads = {}
            for name, label in (("taxonomy", "Taxonomy references"), ("alleles", "MLST alleles"), ("profiles", "MLST profiles"), ("genes", "AMR/VF gene catalog"), ("phenotype", "Optional phenotype")):
                uploads[name] = st.file_uploader(f"{label} CSV/TSV", type=["csv", "tsv"], key=f"{key_prefix}_{name}")
            if any(uploads[name] is None for name in ("taxonomy", "alleles", "profiles", "genes")):
                st.info("Upload all four required reference tables.")
                return
            taxonomy = read_uploaded_table(uploads["taxonomy"])
            alleles = read_uploaded_table(uploads["alleles"])
            profiles = read_uploaded_table(uploads["profiles"])
            genes = read_uploaded_table(uploads["genes"])
            phenotype = read_uploaded_table(uploads["phenotype"]) if uploads["phenotype"] is not None else pd.DataFrame()
        if st.button("Run isolate rapid screen", type="primary", key=f"{key_prefix}_run"):
            try:
                st.session_state[f"{key_prefix}_result"] = analyse_isolate(
                    parse_fasta_text(fasta_text),
                    taxonomy_references=taxonomy,
                    allele_catalog=alleles,
                    mlst_profiles=profiles,
                    gene_catalog=genes,
                    phenotype=phenotype,
                )
            except Exception as exc:
                st.error(f"Isolate analysis failed safely: {exc}")
        result = st.session_state.get(f"{key_prefix}_result")
        if result is None:
            return
        tabs = st.tabs(["Assembly/taxonomy", "MLST", "AMR/VF", "Concordance", "Release"])
        with tabs[0]:
            smart_dataframe(result.assembly_qc, key=f"{key_prefix}_qc")
            smart_dataframe(result.taxonomic_screen, key=f"{key_prefix}_taxonomy")
            smart_dataframe(result.contamination_flags, key=f"{key_prefix}_contamination")
        with tabs[1]:
            smart_dataframe(result.mlst_calls, key=f"{key_prefix}_mlst")
        with tabs[2]:
            smart_dataframe(result.gene_hits, key=f"{key_prefix}_genes")
        with tabs[3]:
            smart_dataframe(result.concordance, key=f"{key_prefix}_concordance")
        with tabs[4]:
            smart_json(result.release_gate, title="Confirmatory release gate", key=f"{key_prefix}_gate")
            smart_json(result.manifest, title="Isolate manifest", key=f"{key_prefix}_manifest")
        insight_callout("Clinical boundary", result.release_gate["boundary"], "warning")


def _demo_automl(seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    n = 420
    x1 = rng.normal(size=n)
    x2 = rng.normal(size=n)
    category = rng.choice(["A", "B", "C"], n)
    logit = 1.5 * x1 - 0.9 * x2 + 0.6 * (category == "C") + rng.normal(0, 0.5, n)
    target = (logit > 0).astype(int)
    return pd.DataFrame({"feature_1": x1, "feature_2": x2, "category": category, "target": target})


def render_automl_upgrade(*, key_prefix: str = "step121_automl") -> None:
    with st.expander("Step 121 · Resource-bounded leakage-safe AutoML", expanded=True):
        st.caption("Deterministic candidate search with preprocessing inside cross-validation, held-out champion evaluation, permutation importance, model card and downloadable joblib artifact.")
        upload = st.file_uploader("Optional labelled CSV/TSV", type=["csv", "tsv"], key=f"{key_prefix}_upload")
        frame = read_uploaded_table(upload) if upload is not None else _demo_automl()
        target = st.selectbox("Target column", frame.columns, index=len(frame.columns) - 1, key=f"{key_prefix}_target")
        task = st.selectbox("Task", ["Auto", "classification", "regression"], key=f"{key_prefix}_task")
        c1, c2, c3 = st.columns(3)
        folds = c1.slider("CV folds", 2, 5, 5, key=f"{key_prefix}_folds")
        candidates = c2.slider("Maximum candidates", 1, 4, 3, key=f"{key_prefix}_candidates")
        max_rows = c3.number_input("Maximum rows", 100, 100_000, 20_000, 100, key=f"{key_prefix}_rows")
        if st.button("Run bounded AutoML", type="primary", key=f"{key_prefix}_run"):
            try:
                st.session_state[f"{key_prefix}_result"] = resource_bounded_automl(
                    frame,
                    target_column=str(target),
                    task=None if task == "Auto" else task,
                    cv_folds=folds,
                    max_candidates=candidates,
                    max_rows=int(max_rows),
                )
            except Exception as exc:
                st.error(f"AutoML failed safely: {exc}")
        result = st.session_state.get(f"{key_prefix}_result")
        if result is None:
            smart_dataframe(frame.head(100), key=f"{key_prefix}_preview")
            return
        metric_cards(
            [
                ("Task", result.task, None),
                ("Candidates", len(result.leaderboard), None),
                ("Champion", result.search_manifest["champion"], "Held-out evaluation attached"),
                ("Artifact SHA", result.search_manifest["artifact_sha256"][:12], "Reproducible local artifact"),
            ]
        )
        tabs = st.tabs(["Leaderboard", "Holdout", "Importance", "Model card", "Artifact"])
        with tabs[0]:
            smart_dataframe(result.leaderboard, key=f"{key_prefix}_leaderboard")
        with tabs[1]:
            smart_dataframe(result.holdout_predictions, key=f"{key_prefix}_predictions")
        with tabs[2]:
            smart_dataframe(result.feature_importance, key=f"{key_prefix}_importance")
        with tabs[3]:
            smart_json(result.model_card, title="Model card", key=f"{key_prefix}_model_card")
            smart_json(result.search_manifest, title="Search manifest", key=f"{key_prefix}_search_manifest")
        with tabs[4]:
            st.download_button("Download champion joblib", result.artifact_bytes, "step121_automl_champion.joblib", "application/octet-stream", key=f"{key_prefix}_artifact")
            st.download_button("Download leaderboard", result.leaderboard.to_csv(index=False), "step121_automl_leaderboard.csv", "text/csv", key=f"{key_prefix}_leaderboard_download")
        insight_callout("Validation boundary", "The bounded search improves reproducibility but does not establish external validity or production readiness.", "warning")


def _demo_citations() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ["C1", "Treatment X improves endpoint Y", "10.1000/demo.1", "", "Prospective cohort of X", "2024", "prospective cohort", "support", "high", False, False, "v1"],
            ["C1", "Treatment X improves endpoint Y", "10.1000/demo.2", "", "Independent null study", "2025", "cohort", "null", "medium", False, False, "v2"],
            ["C2", "Biomarker A predicts outcome B", "", "12345678", "Retrospective validation", "2023", "case-control", "support", "medium", False, True, "corrected-2025"],
        ],
        columns=["claim_id", "claim_text", "doi", "pmid", "title", "year", "study_design", "evidence_direction", "confidence", "retracted", "corrected", "version"],
    )


def render_citation_upgrade(*, key_prefix: str = "step121_citation") -> None:
    with st.expander("Step 121 · Claim-level citation graph and bibliography engine", expanded=True):
        st.caption("DOI/PMID normalization, duplicate detection, exact claim links, imported retraction/correction metadata, conflict queue and BibTeX/RIS exports. Provider verification remains explicit.")
        upload = st.file_uploader("Citation/claim CSV/TSV", type=["csv", "tsv"], key=f"{key_prefix}_upload")
        frame = read_uploaded_table(upload) if upload is not None else _demo_citations()
        try:
            result = build_citation_workspace(frame)
        except Exception as exc:
            st.error(f"Citation workspace failed safely: {exc}")
            return
        metric_cards(
            [
                ("Records", len(result.citations), None),
                ("Claims", result.citations["claim_id"].nunique(), None),
                ("Unique sources", result.citations["record_key"].nunique(), None),
                ("Conflict/review rows", len(result.conflict_review), "Not auto-resolved"),
            ]
        )
        tabs = st.tabs(["Citations", "Claims", "Conflict queue", "Graph", "Export"])
        with tabs[0]:
            smart_dataframe(result.citations, key=f"{key_prefix}_citations")
        with tabs[1]:
            smart_dataframe(result.claim_summary, key=f"{key_prefix}_claims")
        with tabs[2]:
            smart_dataframe(result.conflict_review, key=f"{key_prefix}_conflicts")
        with tabs[3]:
            smart_dataframe(result.graph_nodes, key=f"{key_prefix}_nodes")
            smart_dataframe(result.graph_edges, key=f"{key_prefix}_edges")
        with tabs[4]:
            st.download_button("Download BibTeX", export_bibtex(result.citations), "evidence_library.bib", "application/x-bibtex", key=f"{key_prefix}_bib")
            st.download_button("Download RIS", export_ris(result.citations), "evidence_library.ris", "application/x-research-info-systems", key=f"{key_prefix}_ris")
            st.download_button("Download claim-source edges", result.graph_edges.to_csv(index=False), "claim_evidence_edges.csv", "text/csv", key=f"{key_prefix}_edges_download")
            smart_json(result.release_gate, title="Publication release gate", key=f"{key_prefix}_gate")
            smart_json(result.manifest, title="Citation manifest", key=f"{key_prefix}_manifest")
        insight_callout("Citation boundary", result.release_gate["boundary"], "warning")


def _demo_organoid(seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows: list[dict[str, Any]] = []
    compounds = ["Vehicle", "Compound A", "Compound B"]
    concentrations = [0.01, 0.1, 1.0, 10.0]
    for plate_row in list("ABCDEFGH"):
        for plate_column in range(1, 13):
            well = f"{plate_row}{plate_column:02d}"
            compound = compounds[(plate_column - 1) % len(compounds)]
            concentration = concentrations[(plate_column - 1) % len(concentrations)]
            control = "negative" if compound == "Vehicle" else "positive" if compound == "Compound B" and concentration == 10.0 else "sample"
            for object_index in range(rng.integers(2, 6)):
                baseline = 15_000 + 700 * (ord(plate_row) - ord("A")) + 120 * plate_column
                effect = 1.0 if compound == "Vehicle" else 1 / (1 + concentration / (1.5 if compound == "Compound A" else 0.4))
                volume = max(500, baseline * effect + rng.normal(0, 1200))
                rows.append(
                    {
                        "object_id": f"{well}_O{object_index + 1}",
                        "well": well,
                        "plate_row": plate_row,
                        "plate_column": plate_column,
                        "compound": compound,
                        "concentration": concentration,
                        "control_type": control,
                        "volume_um3": volume,
                        "sphericity": np.clip(rng.normal(0.78, 0.08), 0.2, 1.0),
                        "intensity_mean": rng.normal(1200 * effect, 100),
                        "image_id": f"IMG_{well}",
                        "replicate": 1 + (plate_column % 3),
                    }
                )
    return pd.DataFrame(rows)


def render_organoid_upgrade(*, key_prefix: str = "step121_organoid") -> None:
    with st.expander("Step 121 · 3D organoid phenotype, plate QC and dose-response workbench", expanded=True):
        st.caption("Accepts object-level 3D measurements and adds median-polish plate normalization, robust z-scores, Z-prime, 4-parameter dose-response, morphology PCA and experiment-level release gates.")
        upload = st.file_uploader("Object measurement CSV/TSV", type=["csv", "tsv"], key=f"{key_prefix}_upload")
        frame = read_uploaded_table(upload) if upload is not None else _demo_organoid()
        numeric = list(frame.select_dtypes(include=[np.number]).columns)
        value = st.selectbox("Primary phenotype", numeric, index=numeric.index("volume_um3") if "volume_um3" in numeric else 0, key=f"{key_prefix}_value")
        if st.button("Run organoid experiment analysis", type="primary", key=f"{key_prefix}_run"):
            try:
                st.session_state[f"{key_prefix}_result"] = analyse_organoid_experiment(frame, value_column=value)
            except Exception as exc:
                st.error(f"Organoid analysis failed safely: {exc}")
        result = st.session_state.get(f"{key_prefix}_result")
        if result is None:
            smart_dataframe(frame.head(100), key=f"{key_prefix}_preview")
            return
        tabs = st.tabs(["Plate QC", "Normalized objects", "Dose response", "Morphology", "Release"])
        with tabs[0]:
            smart_dataframe(result.plate_qc, key=f"{key_prefix}_plate_qc")
            if not result.normalized_measurements.empty:
                well_summary = result.normalized_measurements.groupby("well", as_index=False)["plate_normalized_value"].median()
                st.plotly_chart(px.histogram(well_summary, x="plate_normalized_value", nbins=30, title="Well-level normalized phenotype"), width="stretch")
        with tabs[1]:
            smart_dataframe(result.normalized_measurements, key=f"{key_prefix}_normalized")
        with tabs[2]:
            smart_dataframe(result.dose_response, key=f"{key_prefix}_dose")
        with tabs[3]:
            smart_dataframe(result.morphology_embedding, key=f"{key_prefix}_embedding")
        with tabs[4]:
            smart_json(result.release_gate, title="Scientific release gate", key=f"{key_prefix}_gate")
            smart_json(result.manifest, title="Organoid manifest", key=f"{key_prefix}_manifest")
            st.download_button("Download normalized measurements", result.normalized_measurements.to_csv(index=False), "organoid_normalized_measurements.csv", "text/csv", key=f"{key_prefix}_download")
        insight_callout("Biological boundary", result.release_gate["boundary"], "warning")


def _demo_evidence() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ["E1", "genomics", "VAR-001", "Variant associates with phenotype", "support", "cohort", "doi:10.1000/a", "v1", "human", "WGS", 500, 1.8, 0.001, "high", True, "R1", "accepted", "CC-BY-4.0"],
            ["E1", "genomics", "VAR-001", "Variant associates with phenotype", "support", "cohort", "doi:10.1000/a", "v1", "human", "WGS", 500, 1.8, 0.001, "high", True, "R2", "accepted", "CC-BY-4.0"],
            ["E2", "imaging", "IMG-SIG-2", "Image signature predicts response", "support", "imaging study", "local:study2", "2026.1", "human", "microscopy", 80, 0.7, 0.02, "medium", False, "R1", "pending", "internal-review"],
            ["E3", "wet_lab", "ASSAY-9", "Compound inhibits target", "oppose", "wet-lab validation", "local:assay9", "run-3", "cell line", "binding assay", 12, -0.4, 0.08, "low", False, "R1", "rejected", "internal-review"],
        ],
        columns=["evidence_id", "domain", "subject_id", "claim", "direction", "study_design", "source", "version", "organism", "assay", "sample_size", "effect_size", "p_value", "confidence", "independent", "reviewer_id", "review_decision", "license"],
    )


def render_real_evidence_upgrade(*, key_prefix: str = "step121_evidence") -> None:
    with st.expander("Step 121 · Cross-domain evidence and independent adjudication", expanded=True):
        st.caption("Extends evidence intake beyond DTI to genomics, omics, imaging and wet-lab records with domain schemas, licences, source versions, reviewer votes, conflicts and graph exports.")
        upload = st.file_uploader("Cross-domain evidence CSV/TSV", type=["csv", "tsv"], key=f"{key_prefix}_upload")
        frame = read_uploaded_table(upload) if upload is not None else _demo_evidence()
        try:
            result = build_evidence_workspace(frame)
        except Exception as exc:
            st.error(f"Evidence workspace failed safely: {exc}")
            return
        metric_cards(
            [
                ("Evidence rows", len(result.evidence), None),
                ("Domains", result.evidence["domain"].nunique(), None),
                ("Independent rows", int(result.evidence["independent"].sum()), None),
                ("Conflict queue", len(result.conflict_queue), "Requires adjudication"),
            ]
        )
        tabs = st.tabs(["Evidence", "Domain coverage", "Adjudication", "Graph", "Release"])
        with tabs[0]:
            smart_dataframe(result.evidence, key=f"{key_prefix}_records")
        with tabs[1]:
            smart_dataframe(result.domain_summary, key=f"{key_prefix}_domains")
        with tabs[2]:
            smart_dataframe(result.adjudication, key=f"{key_prefix}_adjudication")
            smart_dataframe(result.conflict_queue, key=f"{key_prefix}_conflicts")
        with tabs[3]:
            smart_dataframe(result.graph_nodes, key=f"{key_prefix}_nodes")
            smart_dataframe(result.graph_edges, key=f"{key_prefix}_edges")
        with tabs[4]:
            smart_json(result.release_gate, title="Evidence release gate", key=f"{key_prefix}_gate")
            smart_json(result.manifest, title="Cross-domain evidence manifest", key=f"{key_prefix}_manifest")
            st.download_button("Download normalized evidence", result.evidence.to_csv(index=False), "cross_domain_evidence.csv", "text/csv", key=f"{key_prefix}_download")
        insight_callout("Validation boundary", result.release_gate["boundary"], "warning")
