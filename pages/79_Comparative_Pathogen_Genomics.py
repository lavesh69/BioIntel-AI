from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.projects.comparative_genomics import (  # noqa: E402
    GenomeRecord,
    assignment_bootstrap_stability,
    best_hit_summary,
    compare_genomes,
    demo_marker_panel,
    demo_query_panel,
    demo_reference_panel,
    distance_matrix,
    gc_skew_profile,
    genome_qc,
    kmer_frequency_table,
    pairwise_variant_summary,
    pairwise_variant_table,
    pangenome_kmer_presence,
    parse_fasta,
    predict_orfs,
    screen_markers_with_tolerance,
    upgma_newick,
    window_reference_assignment,
)
from biointel.projects.pathogen_advanced import (  # noqa: E402
    alignment_ani_table,
    gene_pangenome,
    pathogen_tool_availability,
    validate_marker_reference_pack,
    window_divergence_scan,
)
from biointel.projects.professional import (  # noqa: E402
    QualityGate,
    model_card_payload,
    quality_gate_table,
)
from biointel.projects.reporting import build_project_bundle, build_run_manifest  # noqa: E402
from biointel.projects.run_registry import register_run  # noqa: E402
from biointel.ui.components import (  # noqa: E402
    metric_cards,
    scientific_boundary_banner,
    smart_dataframe,
    smart_json,
)
from biointel.ui.theme import apply_theme, hero, insight_callout, section_title  # noqa: E402
from biointel.ui.workflow import (  # noqa: E402
    analysis_run,
    read_uploaded_text,
    render_methodology,
    render_upload_preflight,
)

PROJECT_CODE = "BIO-CG-PATH"
RUN_REGISTRY = ROOT / "reports" / "biotechnology_project_runs.sqlite3"
PROJECT_NAME = "Comparative Genomics for Pathogen Detection and Characterization"
BOUNDARY = (
    "This workflow provides local genomic similarity and marker-screening evidence, not a validated clinical identification. "
    "Use curated references, contamination controls, accepted taxonomy methods, laboratory confirmation and expert review."
)


def _records_to_frame(records: list[GenomeRecord]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "genome_id": record.identifier,
                "description": record.description,
                "sequence": record.sequence,
            }
            for record in records
        ]
    )


st.set_page_config(page_title="Comparative Pathogen Genomics · BioIntel AI", page_icon="🧫", layout="wide")
apply_theme()

# STEP116_MODULE_EXPERIENCE_2_TO_9
from biointel.ui.module_experience_2_9 import render_module_experience as _render_step116_module_experience
_render_step116_module_experience("comparative_pathogen", key_prefix="step116_79_Comparative_Pathogen_Genomics_comparative_pathogen_1", expanded=False)
hero(
    PROJECT_NAME,
    "A complete local genomics workbench for FASTA validation, composition QC, canonical k-mer comparison, best-reference review, distance clustering, pairwise variant screening, marker detection and reproducible export.",
    eyebrow="Biotechnology Project 02 · Professional workbench",
    chips=[
        "FASTA QC",
        "ANI screen",
        "Gene pangenome",
        "Variant screen",
        "Marker provenance",
        "Tool bridge",
    ],
)
scientific_boundary_banner(source_kind="demo_reference", release_eligible=False, message=BOUNDARY)

render_methodology(
    method="FASTA QC, k-mer comparison, affine-gap pairwise variant screening, marker search and exploratory clustering.",
    assumptions=[
        "Reference panels are curated and sequence orientation/context are appropriate.",
    ],
    limitations=[
        "The app now includes an ORF-derived gene-cluster pangenome; final surveillance should still use annotation-aware specialist tools.",
        "Whole-genome phylogeny, recombination and clinical identification require external tools.",
    ],
    validation=[
        "Confirm taxonomy with ANI/core-genome methods.",
        "Screen contamination and validate markers experimentally.",
    ],
)

source_tabs = st.tabs(
    ["1 · Query genomes", "2 · Reference panel", "3 · Marker panel", "4 · Parameters"]
)
with source_tabs[0]:
    query_mode = st.radio(
        "Query source",
        ["Deterministic demo", "Upload FASTA", "Paste FASTA"],
        horizontal=True,
        key="cg_query_mode",
    )
    query_upload = st.file_uploader(
        "Query genome/contig FASTA",
        type=["fa", "fasta", "fna"],
        disabled=query_mode != "Upload FASTA",
        key="cg_query_upload",
    )
    query_upload_profile = render_upload_preflight(
        query_upload,
        key="cg_query",
        allowed_extensions=["fa", "fasta", "fna"],
        soft_limit_mb=15,
        hard_limit_mb=100,
    )
    query_text = st.text_area(
        "Paste query FASTA", height=180, disabled=query_mode != "Paste FASTA", key="cg_query_text"
    )
    try:
        if query_mode == "Upload FASTA" and query_upload:
            queries = parse_fasta(
                read_uploaded_text(query_upload, encoding="utf-8", errors="replace")
            )
        elif query_mode == "Paste FASTA" and query_text.strip():
            queries = parse_fasta(query_text)
        else:
            queries = demo_query_panel()
    except Exception as exc:
        st.error(f"Query FASTA could not be parsed: {exc}")
        queries = []
    if queries:
        smart_dataframe(genome_qc(queries, k=9), height=300, key="cg_query_qc_preview")

with source_tabs[1]:
    reference_mode = st.radio(
        "Reference source",
        ["Deterministic demo", "Upload FASTA", "Paste FASTA"],
        horizontal=True,
        key="cg_ref_mode",
    )
    reference_upload = st.file_uploader(
        "Reference-panel FASTA",
        type=["fa", "fasta", "fna"],
        disabled=reference_mode != "Upload FASTA",
        key="cg_ref_upload",
    )
    reference_upload_profile = render_upload_preflight(
        reference_upload,
        key="cg_reference",
        allowed_extensions=["fa", "fasta", "fna"],
        soft_limit_mb=25,
        hard_limit_mb=150,
    )
    reference_text = st.text_area(
        "Paste reference FASTA",
        height=180,
        disabled=reference_mode != "Paste FASTA",
        key="cg_ref_text",
    )
    try:
        if reference_mode == "Upload FASTA" and reference_upload:
            references = parse_fasta(
                read_uploaded_text(reference_upload, encoding="utf-8", errors="replace")
            )
        elif reference_mode == "Paste FASTA" and reference_text.strip():
            references = parse_fasta(reference_text)
        else:
            references = demo_reference_panel()
    except Exception as exc:
        st.error(f"Reference FASTA could not be parsed: {exc}")
        references = []
    if references:
        smart_dataframe(genome_qc(references, k=9), height=300, key="cg_reference_qc_preview")

with source_tabs[2]:
    marker_defaults = demo_marker_panel().assign(
        source="Bundled software-validation marker",
        release="Step59-local-v1",
        evidence="sequence-screen only",
        organism="synthetic/demo",
    )
    markers = st.data_editor(
        marker_defaults,
        width="stretch",
        hide_index=True,
        num_rows="dynamic",
        key="cg_marker_editor",
        column_config={
            "marker": st.column_config.TextColumn("Marker", required=True),
            "sequence": st.column_config.TextColumn("DNA sequence", required=True),
            "category": st.column_config.TextColumn("Category", required=True),
        },
    )
    st.caption(
        "Marker matches are transparent sequence screens. They do not establish phenotype or clinical resistance."
    )

with source_tabs[3]:
    with st.form("cg_equal_depth_form"):
        row1 = st.columns(4)
        k = row1[0].slider("Canonical k-mer size", 5, 25, 11, 2)
        high_threshold = row1[1].slider("High-similarity threshold", 0.50, 0.95, 0.72, 0.01)
        max_rankings = row1[2].slider(
            "References shown per query",
            1,
            max(1, min(10, len(references) if references else 1)),
            min(4, len(references) if references else 1),
        )
        mismatch_tolerance = row1[3].slider("Marker mismatch tolerance", 0, 5, 1)
        row2 = st.columns(3)
        composition_k = row2[0].slider("Composition k-mer size", 2, 8, 4)
        variant_limit = row2[1].number_input(
            "Variant rows retained per best hit", 100, 100_000, 5_000, 100
        )
        include_all_distance = row2[2].toggle(
            "Include queries and references in distance tree", value=True
        )
        run = st.form_submit_button(
            "Run complete comparative-genomics workbench", type="primary", width="stretch"
        )

if not queries or not references:
    st.info("Provide at least one valid query and one reference FASTA record.")
    st.stop()

if run:
    try:
        with analysis_run(
            "Validating genomes, fingerprinting k-mers and building comparative evidence"
        ):
            query_qc = genome_qc(queries, k=k)
            reference_qc = genome_qc(references, k=k)
            rankings = compare_genomes(queries, references, k=k)
            rankings["above_review_threshold"] = rankings["screening_score"] >= high_threshold
            best_hits = best_hit_summary(rankings)
            all_records = [*queries, *references] if include_all_distance else queries
            distances = distance_matrix(all_records, k=k)
            newick = upgma_newick(distances)
            marker_pack = validate_marker_reference_pack(pd.DataFrame(markers))
            marker_results = screen_markers_with_tolerance(
                queries, marker_pack, maximum_mismatches=int(mismatch_tolerance)
            )
            marker_metadata = (
                marker_pack.drop(columns=["sequence"]).drop_duplicates().reset_index(drop=True)
            )
            reference_map = {record.identifier: record for record in references}
            query_map = {record.identifier: record for record in queries}
            variant_summaries = []
            variant_tables = []
            for hit in best_hits.itertuples(index=False):
                query = query_map[str(hit.query_genome)]
                reference = reference_map[str(hit.best_reference)]
                variant_summaries.append(pairwise_variant_summary(query, reference))
                variants = pairwise_variant_table(query, reference, limit=int(variant_limit))
                if not variants.empty:
                    variant_tables.append(variants)
            variant_summary = pd.DataFrame(variant_summaries)
            variants = (
                pd.concat(variant_tables, ignore_index=True) if variant_tables else pd.DataFrame()
            )
            ani = alignment_ani_table(queries, references, best_only=True)
            divergence_tables = []
            for hit in best_hits.itertuples(index=False):
                divergence_tables.append(
                    window_divergence_scan(
                        query_map[str(hit.query_genome)],
                        reference_map[str(hit.best_reference)],
                        window=min(
                            1000, max(100, len(query_map[str(hit.query_genome)].sequence) // 10)
                        ),
                        step=min(
                            500, max(50, len(query_map[str(hit.query_genome)].sequence) // 20)
                        ),
                    )
                )
            divergence = (
                pd.concat(divergence_tables, ignore_index=True)
                if divergence_tables
                else pd.DataFrame()
            )
            gene_assignments, gene_presence, gene_pangenome_summary = gene_pangenome(
                [*queries, *references], minimum_amino_acids=20, similarity_threshold=0.60
            )
            composition_tables = []
            for record in queries:
                table = kmer_frequency_table(record, k=int(composition_k), top_n=30)
                table.insert(0, "genome_id", record.identifier)
                composition_tables.append(table)
            composition = pd.concat(composition_tables, ignore_index=True)
            parameters = {
                "canonical_kmer_size": int(k),
                "high_similarity_threshold": float(high_threshold),
                "marker_mismatch_tolerance": int(mismatch_tolerance),
                "composition_kmer_size": int(composition_k),
                "variant_row_limit": int(variant_limit),
            }
            outputs = {
                "query_qc": query_qc,
                "reference_qc": reference_qc,
                "reference_rankings": rankings,
                "best_hits": best_hits,
                "distance_matrix": distances.reset_index(names="genome_id"),
                "marker_results": marker_results,
                "pairwise_variant_summary": variant_summary,
                "pairwise_variants": variants,
                "query_kmer_composition": composition,
                "alignment_ani_screen": ani,
                "window_divergence": divergence,
                "gene_cluster_assignments": gene_assignments,
                "gene_pangenome_presence": gene_presence,
                "gene_pangenome_summary": gene_pangenome_summary,
                "marker_reference_metadata": marker_metadata,
            }
            inputs = {
                "query_genomes": _records_to_frame(queries),
                "reference_genomes": _records_to_frame(references),
                "marker_panel": marker_pack,
            }
            bundle = build_project_bundle(
                project_code=PROJECT_CODE,
                project_name=PROJECT_NAME,
                parameters=parameters,
                inputs=inputs,
                outputs=outputs,
                scientific_boundary=BOUNDARY,
                notes=f"UPGMA screening tree: {newick}",
            )
            bootstrap_stability = assignment_bootstrap_stability(
                queries, references, k=int(k), random_state=42
            )
            window_assignments = pd.concat(
                [
                    window_reference_assignment(
                        record,
                        references,
                        k=max(5, min(int(k), 15)),
                        window=min(1000, max(150, len(record.sequence) // 4)),
                        step=min(500, max(75, len(record.sequence) // 8)),
                    )
                    for record in queries
                ],
                ignore_index=True,
            )
            gc_skew = pd.concat(
                [
                    gc_skew_profile(
                        record,
                        window=min(500, max(100, len(record.sequence) // 10)),
                        step=min(250, max(50, len(record.sequence) // 20)),
                    )
                    for record in queries
                ],
                ignore_index=True,
            )
            orf_tables = [predict_orfs(record, minimum_amino_acids=20) for record in queries]
            orfs = (
                pd.concat(orf_tables, ignore_index=True)
                if any(not table.empty for table in orf_tables)
                else pd.DataFrame()
            )
            pangenome_matrix, pangenome_summary = pangenome_kmer_presence(
                [*queries, *references], k=max(5, min(int(k), 11)), maximum_kmers=3000
            )
            outputs.update(
                {
                    "assignment_bootstrap_stability": bootstrap_stability,
                    "window_reference_assignments": window_assignments,
                    "query_gc_skew": gc_skew,
                    "predicted_orfs": orfs,
                    "pangenome_kmer_presence": pangenome_matrix,
                    "pangenome_summary": pangenome_summary,
                }
            )
            mean_support = (
                float(bootstrap_stability["bootstrap_support_percent"].mean())
                if not bootstrap_stability.empty
                else 0.0
            )
            low_margin_windows = (
                int((window_assignments["assignment_margin"] < 0.05).sum())
                if not window_assignments.empty
                else 0
            )
            ambiguous = (
                int((query_qc["ambiguous_percent"] > 1).sum())
                if "ambiguous_percent" in query_qc.columns
                else 0
            )
            gates = quality_gate_table(
                [
                    QualityGate(
                        "CG-INPUT",
                        "Query sequence quality",
                        "pass" if ambiguous == 0 else "review",
                        100.0 * (1 - ambiguous / max(len(query_qc), 1)),
                        f"{ambiguous} queries exceed 1% ambiguous bases",
                        "Improve assemblies or mask uncertain regions.",
                    ),
                    QualityGate(
                        "CG-REF",
                        "Reference-panel coverage",
                        "pass" if len(references) >= 3 else "review",
                        min(100.0, len(references) / 3 * 100),
                        f"{len(references)} reference genomes",
                        "Use taxonomically representative and versioned references.",
                    ),
                    QualityGate(
                        "CG-BOOT",
                        "Assignment bootstrap support",
                        "pass" if mean_support >= 80 else "review",
                        mean_support,
                        f"Mean support {mean_support:.1f}%",
                        "Low support requires broader references or accepted ANI/taxonomy methods.",
                    ),
                    QualityGate(
                        "CG-CHIMERA",
                        "Window consistency",
                        "pass" if low_margin_windows == 0 else "review",
                        100.0 * (1 - low_margin_windows / max(len(window_assignments), 1)),
                        f"{low_margin_windows} low-margin windows",
                        "Review contamination, recombination and mixed assemblies.",
                    ),
                    QualityGate(
                        "CG-MARK",
                        "Marker context",
                        "review",
                        60.0,
                        f"{int(marker_results['detected'].sum()) if 'detected' in marker_results.columns else 0} sequence markers detected",
                        "Sequence presence alone does not establish phenotype.",
                    ),
                ]
            )
            manifest = build_run_manifest(
                project_code=PROJECT_CODE,
                project_name=PROJECT_NAME,
                parameters=parameters,
                inputs=inputs,
                outputs=outputs,
                scientific_boundary=BOUNDARY,
            )
            model_card = model_card_payload(
                project_code=PROJECT_CODE,
                title=PROJECT_NAME,
                intended_use="Screen assembled pathogen genomes against a controlled local reference panel.",
                out_of_scope=[
                    "Clinical identification",
                    "Outbreak attribution",
                    "Phenotypic resistance calls",
                ],
                methodology=[
                    "FASTA and composition QC",
                    "Canonical k-mer ranking",
                    "Window-level assignment",
                    "Bootstrap stability",
                    "ORF, GC-skew and pangenome screens",
                ],
                metrics={
                    "queries": len(queries),
                    "references": len(references),
                    "mean_bootstrap_support_percent": mean_support,
                    "low_margin_windows": low_margin_windows,
                },
                validation=[
                    "Reference ranking margin",
                    "Bootstrap k-mer subsampling",
                    "Window-consistency review",
                    "Marker mismatch tolerance",
                ],
                limitations=[
                    BOUNDARY,
                    "K-mer screens are not replacements for accepted ANI, phylogenomic or laboratory methods.",
                ],
                quality_gates=gates,
                run_fingerprint=manifest["run_fingerprint"],
            )
            bundle = build_project_bundle(
                project_code=PROJECT_CODE,
                project_name=PROJECT_NAME,
                parameters=parameters,
                inputs=inputs,
                outputs=outputs,
                scientific_boundary=BOUNDARY,
                notes=f"UPGMA screening tree: {newick}",
                quality_gates=gates,
                summary={
                    "Queries": len(queries),
                    "References": len(references),
                    "Mean bootstrap support": round(mean_support, 2),
                    "Low-margin windows": low_margin_windows,
                },
                methods=model_card["methodology"],
                model_card=model_card,
            )
            quality_score = float(
                gates.assign(
                    weight=gates["status"]
                    .map({"pass": 1.0, "review": 0.6, "block": 0.0})
                    .fillna(0.0)
                )
                .eval("score * weight")
                .mean()
            )
            register_run(
                RUN_REGISTRY,
                run_fingerprint=manifest["run_fingerprint"],
                project_code=PROJECT_CODE,
                project_name=PROJECT_NAME,
                status="qualified" if (gates["status"] == "block").sum() == 0 else "blocked",
                quality_score=quality_score,
                input_rows=sum(len(frame) for frame in inputs.values()),
                output_rows=sum(len(frame) for frame in outputs.values()),
                parameters=parameters,
                metrics={
                    "mean_bootstrap_support_percent": mean_support,
                    "low_margin_windows": low_margin_windows,
                },
            )
        st.session_state["cg_equal_depth_result"] = {
            "query_qc": query_qc,
            "reference_qc": reference_qc,
            "rankings": rankings,
            "best_hits": best_hits,
            "distances": distances,
            "newick": newick,
            "markers": marker_results,
            "variant_summary": variant_summary,
            "variants": variants,
            "composition": composition,
            "bundle": bundle,
            "manifest": manifest,
            "max_rankings": max_rankings,
            "bootstrap_stability": bootstrap_stability,
            "window_assignments": window_assignments,
            "gc_skew": gc_skew,
            "orfs": orfs,
            "pangenome_summary": pangenome_summary,
            "alignment_ani": ani,
            "window_divergence": divergence,
            "gene_assignments": gene_assignments,
            "gene_presence": gene_presence,
            "gene_pangenome_summary": gene_pangenome_summary,
            "marker_metadata": marker_metadata,
            "tool_availability": pathogen_tool_availability(),
            "quality_gates": gates,
            "model_card": model_card,
        }
        st.toast("Comparative-genomics workbench completed", icon="✅")
    except Exception as exc:
        st.error(f"Comparative-genomics workbench could not run: {exc}")

payload = st.session_state.get("cg_equal_depth_result")
if payload:
    best_hits = payload["best_hits"]
    metric_cards(
        [
            ("Query genomes", f"{len(queries):,}", None),
            ("Reference genomes", f"{len(references):,}", None),
            (
                "High-confidence assignments",
                f"{int((best_hits['assignment_confidence'] == 'High').sum()):,}",
                None,
            ),
            ("Detected markers", f"{int(payload['markers']['detected'].sum()):,}", None),
        ]
    )
    tabs = st.tabs(
        [
            "Executive summary",
            "Reference ranking",
            "ANI & divergence",
            "Distance & tree",
            "Pairwise variants",
            "Marker characterization",
            "Genome QC",
            "Composition",
            "Gene pangenome",
            "Deep genome assurance",
            "Tool bridge",
            "Exports & manifest",
        ]
    )
    with tabs[0]:
        smart_dataframe(best_hits, height=360)
        st.plotly_chart(
            px.bar(
                best_hits,
                x="query_genome",
                y="best_score",
                color="assignment_confidence",
                hover_data=["best_reference", "identification_margin"],
                title="Best-reference screening assignments",
            ),
            width="stretch",
        )
        insight_callout(
            "Assignment rule",
            "Review both the absolute similarity score and the margin over the second-best reference. Ambiguous margins should not be treated as confident identification.",
            "warning",
        )
    with tabs[1]:
        top = (
            payload["rankings"]
            .groupby("query_genome", group_keys=False)
            .head(int(payload["max_rankings"]))
        )
        st.plotly_chart(
            px.bar(
                top,
                x="screening_score",
                y="reference_genome",
                color="query_genome",
                orientation="h",
                hover_data=[
                    "jaccard_similarity",
                    "query_containment",
                    "reference_containment",
                    "gc_difference_percent",
                ],
                title="Ranked reference similarities",
            ),
            width="stretch",
        )
        smart_dataframe(top, height=500)
    with tabs[2]:
        smart_dataframe(payload["alignment_ani"], height=320)
        if not payload["window_divergence"].empty:
            st.plotly_chart(
                px.line(
                    payload["window_divergence"],
                    x="start",
                    y="identity_percent",
                    color="query",
                    line_dash="reference",
                    title="Window-level identity against best reference",
                ),
                width="stretch",
            )
            smart_dataframe(payload["window_divergence"], height=360)
        insight_callout(
            "ANI boundary",
            "The internal alignment identity is a transparent ANI-like screen for bounded sequences. Confirm accepted taxonomic thresholds with FastANI or another validated implementation.",
            "warning",
        )
    with tabs[3]:
        st.plotly_chart(
            px.imshow(
                payload["distances"],
                text_auto=".2f",
                aspect="auto",
                title="Canonical k-mer distance matrix",
            ),
            width="stretch",
        )
        st.code(payload["newick"], language="text")
        st.download_button(
            "Download screening tree (Newick)",
            payload["newick"],
            "comparative_genomics_tree.nwk",
            "text/plain",
            width="stretch",
        )
    with tabs[4]:
        smart_dataframe(payload["variant_summary"], height=300)
        if payload["variants"].empty:
            st.info("No positional differences were found within the retained comparison range.")
        else:
            st.plotly_chart(
                px.histogram(
                    payload["variants"],
                    x="variant_type",
                    color="query_genome",
                    title="Pairwise positional difference classes",
                ),
                width="stretch",
            )
            smart_dataframe(payload["variants"], height=520)
    with tabs[5]:
        detected = payload["markers"][payload["markers"]["detected"]]
        if detected.empty:
            st.info("No marker met the configured mismatch tolerance.")
        else:
            st.plotly_chart(
                px.bar(
                    detected.groupby(["genome_id", "category"]).size().reset_index(name="markers"),
                    x="genome_id",
                    y="markers",
                    color="category",
                    title="Detected characterization markers",
                ),
                width="stretch",
            )
        smart_dataframe(payload["markers"], height=470)
    with tabs[6]:
        left, right = st.columns(2)
        with left:
            section_title("Query QC", "Q")
            smart_dataframe(payload["query_qc"], height=420)
        with right:
            section_title("Reference QC", "R")
            smart_dataframe(payload["reference_qc"], height=420)
    with tabs[7]:
        selected_genome = st.selectbox(
            "Query genome",
            sorted(payload["composition"]["genome_id"].unique()),
            key="cg_composition_genome",
        )
        selected = payload["composition"][payload["composition"]["genome_id"] == selected_genome]
        st.plotly_chart(
            px.bar(
                selected,
                x="frequency_percent",
                y="kmer",
                orientation="h",
                title=f"Top canonical composition k-mers · {selected_genome}",
            ),
            width="stretch",
        )
        smart_dataframe(selected, height=420)
    with tabs[8]:
        smart_dataframe(payload["gene_pangenome_summary"], height=320)
        smart_dataframe(payload["gene_presence"], height=420)
        smart_dataframe(payload["gene_assignments"], height=420)
        if not payload["gene_pangenome_summary"].empty:
            category_counts = (
                payload["gene_pangenome_summary"]["category"].value_counts().reset_index()
            )
            category_counts.columns = ["category", "gene_clusters"]
            st.plotly_chart(
                px.bar(
                    category_counts,
                    x="category",
                    y="gene_clusters",
                    title="ORF-derived gene-cluster pangenome",
                ),
                width="stretch",
            )
        insight_callout(
            "Gene pangenome",
            "This ORF/protein-k-mer clustering is a real gene-cluster workflow, but final bacterial pangenomes should be reproduced with annotation-aware tools such as Panaroo/Roary.",
            "warning",
        )
    with tabs[9]:
        left, right = st.columns(2)
        with left:
            st.plotly_chart(
                px.bar(
                    payload["bootstrap_stability"],
                    x="query_id",
                    y="bootstrap_support_percent",
                    color="consensus_reference",
                    title="Reference-assignment bootstrap support",
                ),
                width="stretch",
            )
            smart_dataframe(payload["window_assignments"], height=360)
        with right:
            st.plotly_chart(
                px.line(
                    payload["gc_skew"],
                    x="start",
                    y="gc_skew",
                    color="genome_id",
                    title="Sliding-window GC skew",
                ),
                width="stretch",
            )
            smart_dataframe(payload["pangenome_summary"], height=240)
        section_title("Predicted open reading frames", "⌬")
        smart_dataframe(payload["orfs"], height=360)
        smart_dataframe(payload["quality_gates"], height=340)
        insight_callout(
            "Assurance boundary",
            "Internal support and consistency checks strengthen screening quality but do not constitute validated taxonomic identification.",
            "warning",
        )
    with tabs[10]:
        smart_dataframe(payload["tool_availability"], height=320)
        smart_dataframe(payload["marker_metadata"], height=320)
        st.caption(
            "When installed locally, specialist tools can be qualified and connected without uploading sequences to third parties."
        )
    with tabs[11]:
        smart_json(
            payload["model_card"],
            title="Comparative-genomics method card",
            download_name="comparative_genomics_method_card.json",
            key="cg_method_card",
        )
        smart_json(
            payload["manifest"],
            title="Reproducibility manifest",
            download_name="comparative_genomics_manifest.json",
            key="cg_manifest_download",
        )
        st.download_button(
            "Download complete comparative-genomics project bundle (.zip)",
            payload["bundle"],
            "BIO-CG-PATH_project_bundle.zip",
            "application/zip",
            width="stretch",
            key="cg_bundle_download",
        )
else:
    section_title("Professional capability map", "▦")
    smart_dataframe(
        pd.DataFrame(
            [
                (
                    "Input",
                    "Multi-record FASTA upload/paste with identifier and nucleotide validation",
                ),
                ("Quality", "Length, GC, ambiguity, sequence complexity and pass/review status"),
                (
                    "Comparison",
                    "Canonical k-mer Jaccard/containment scoring and best-hit margin review",
                ),
                ("Characterization", "Mismatch-tolerant marker screening with position and strand"),
                ("Variation", "Best-hit positional substitution/indel screening and summary"),
                ("Phylogeny", "Distance heatmap and deterministic UPGMA Newick tree"),
                ("Reproducibility", "SHA-256 manifest and downloadable input/output bundle"),
            ],
            columns=["Layer", "Implemented capability"],
        ),
        height=400,
    )

# Step 110 advanced scientific viewers
from biointel.ui.advanced_scientific_viewers import render_embedded_viewer as _render_step110_viewer

_render_step110_viewer("phylogenetic_tree", key_prefix="step110_79_Comparative_Pathogen_Genomics_phylogenetic_tree")
_render_step110_viewer("outbreak_map", key_prefix="step110_79_Comparative_Pathogen_Genomics_outbreak_map")

# Step 115 non-chart visual: outbreak_map_canvas
from biointel.ui.non_chart_scientific_visuals import render_non_chart_visual as _render_step115_non_chart
_render_step115_non_chart("outbreak_map_canvas", key_prefix="step115_79_Comparative_Pathogen_Genomics_outbreak_map_canvas", expanded=False)

# STEP127_SCIENTIFIC_DEPTH_COMPARATIVE_PATHOGEN
from biointel.step127.ui import render_step127_upgrade_panel as _render_step127_upgrade_panel
_render_step127_upgrade_panel('comparative_pathogen', expanded=False)

# Targeted peak-potential assurance for Genomics, Discovery, Omics, Lab and Translational modules.
from biointel.peak_potential.ui import render_peak_session_footer
render_peak_session_footer(page_key='comparative_pathogen_genomics', title='Comparative Pathogen Genomics', category='Bioinformatics')

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='comparative_pathogen_genomics', title='Comparative Pathogen Genomics', category='Bioinformatics')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
