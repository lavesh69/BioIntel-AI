from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.projects.professional import (  # noqa: E402
    QualityGate,
    model_card_payload,
    quality_gate_table,
)
from biointel.projects.reporting import build_project_bundle, build_run_manifest  # noqa: E402
from biointel.projects.run_registry import register_run  # noqa: E402
from biointel.projects.single_cell import (  # noqa: E402
    annotate_clusters_by_markers,
    batch_effect_audit,
    cluster_average_expression,
    cluster_quality_metrics,
    cluster_stability,
    default_cell_type_markers,
    demo_single_cell_counts,
    differential_expression_between_clusters,
    dropout_profile,
    find_cluster_markers,
    marker_specificity,
    parse_10x_mtx_bundle,
    pseudobulk_counts,
    pseudobulk_expression,
    run_single_cell_pipeline,
    trajectory_screen,
    validate_count_matrix,
)
from biointel.projects.single_cell_advanced import (  # noqa: E402
    ambient_rna_audit,
    batch_residualized_embedding,
    cell_cycle_scores,
    graph_cluster_cells,
    graph_cluster_stability,
    ligand_receptor_screen,
    parse_h5ad_bytes,
    simulated_doublet_scores,
)
from biointel.ui.components import (  # noqa: E402
    metric_cards,
    scientific_boundary_banner,
    smart_dataframe,
    smart_json,
)
from biointel.ui.theme import apply_theme, hero, insight_callout, section_title  # noqa: E402
from biointel.ui.workflow import (  # noqa: E402
    analysis_run,
    read_uploaded_table,
    render_methodology,
    render_upload_preflight,
)

PROJECT_CODE = "BIO-SCRNA"
RUN_REGISTRY = ROOT / "reports" / "biotechnology_project_runs.sqlite3"
PROJECT_NAME = "Single-Cell RNA Sequencing Analysis to Uncover Cellular Heterogeneity"
BOUNDARY = (
    "Clusters, marker scores, doublet flags and provisional labels are exploratory. Publication-grade scRNA-seq requires "
    "validated preprocessing, ambient-RNA and doublet assessment, batch-aware integration and biological confirmation."
)


st.set_page_config(page_title="Single-Cell Heterogeneity · BioIntel AI", page_icon="🧬", layout="wide")
apply_theme()

from biointel.ui.scientific_integrations import render_page_integrations as _render_biointel_integrations
_render_biointel_integrations("pages/80_Single_Cell_Heterogeneity.py", key_prefix="80_single_cell_heterogeneity", expanded=False)

# STEP196_CONTEXTUAL_ONLINE_RESEARCH_HOOK · TOP RELEVANT WEBSITES
from biointel.contextual_research_v196.ui import render_contextual_online_research as _render_step196_contextual_online_research
_render_step196_contextual_online_research('single_cell_core', expanded=False)

# STEP196_P0_P1_PRIORITY_UPGRADE_HOOK
from biointel.proof_gates_v10.ui import render_module_priority_workbench as _render_step196_p0_p1_priority_workbench
_render_step196_p0_p1_priority_workbench(ROOT, 'single_cell_core', expanded=False)

# STEP116_MODULE_EXPERIENCE_2_TO_9
from biointel.ui.module_experience_2_9 import render_module_experience as _render_step116_module_experience
_render_step116_module_experience("single_cell", key_prefix="step116_80_Single_Cell_Heterogeneity_single_cell_1", expanded=False)
hero(
    PROJECT_NAME,
    "A complete single-cell workbench for count-matrix validation, cell QC, doublet screening, normalization, variable-gene selection, dimensional reduction, clustering, stability checks, marker discovery, provisional annotation and cluster comparison.",
    eyebrow="Biotechnology Project 03 · Professional workbench",
    chips=[
        "Cell QC",
        "Doublet screen",
        "HVG + PCA",
        "Cluster stability",
        "Marker annotation",
        "Project bundle",
    ],
)
scientific_boundary_banner(source_kind="demo_reference", release_eligible=False, message=BOUNDARY)

render_methodology(
    method="Count-matrix QC, log normalization, graph/Leiden clustering, UMAP, doublet and ambient-RNA screens, marker statistics and donor-aware pseudobulk exports.",
    assumptions=[
        "Cells and genes are correctly oriented and metadata cell IDs match.",
    ],
    limitations=[
        "Graph clustering, UMAP and simulated-doublet scoring remain exploratory until validated against study-specific references.",
        "Cell-level tests may not represent donor-level biological replication.",
    ],
    validation=[
        "Compare graph resolutions, inspect batch-residualized embeddings and use donor-aware models.",
        "Confirm cell labels with independent markers/reference mapping.",
    ],
)

input_tab, metadata_tab, markers_tab, settings_tab = st.tabs(
    ["1 · Count matrix", "2 · Cell metadata", "3 · Marker panel", "4 · Analysis settings"]
)
with input_tab:
    source = st.radio(
        "Count-matrix source",
        ["Deterministic demo", "Upload CSV/TSV", "Upload 10x MTX ZIP", "Upload H5AD"],
        horizontal=True,
    )
    uploaded = st.file_uploader(
        "Genes-by-cells count matrix",
        type=["csv", "tsv", "zip", "h5ad"],
        help="CSV/TSV: genes by cells with a gene column. 10x ZIP: Matrix Market bundle. H5AD: counts layer is preferred; X is used otherwise.",
        disabled=source == "Deterministic demo",
        key="scrna_counts_upload",
    )
    count_upload_profile = render_upload_preflight(
        uploaded,
        key="scrna_counts",
        allowed_extensions=["csv", "tsv", "zip", "h5ad"],
        soft_limit_mb=80,
        hard_limit_mb=500,
    )
    demo_controls = st.columns(3)
    demo_genes = demo_controls[0].slider(
        "Demo genes", 300, 1_500, 700, 100, disabled=source != "Deterministic demo"
    )
    demo_cells = demo_controls[1].slider(
        "Demo cells", 60, 400, 180, 20, disabled=source != "Deterministic demo"
    )
    demo_clusters = demo_controls[2].slider(
        "Embedded demo populations", 2, 8, 4, disabled=source != "Deterministic demo"
    )
    h5ad_metadata = pd.DataFrame()
    h5ad_audit: dict[str, object] = {}
    if uploaded and source == "Upload 10x MTX ZIP":
        with analysis_run("Reading and validating 10x Matrix Market bundle"):
            counts = parse_10x_mtx_bundle(uploaded.getvalue(), maximum_dense_cells=12_000_000)
    elif uploaded and source == "Upload H5AD":
        with analysis_run("Reading H5AD counts and cell metadata"):
            counts, h5ad_metadata, h5ad_audit = parse_h5ad_bytes(uploaded.getvalue())
        st.caption(
            f"H5AD matrix source: {h5ad_audit.get('matrix_source')} · "
            f"{h5ad_audit.get('genes', 0):,} genes × {h5ad_audit.get('cells', 0):,} cells"
        )
    elif uploaded:
        counts = read_uploaded_table(uploaded)
    else:
        counts = demo_single_cell_counts(
            genes=int(demo_genes), cells=int(demo_cells), clusters=int(demo_clusters)
        )
    try:
        validated_preview = validate_count_matrix(counts)
        metric_cards(
            [
                ("Genes", f"{len(validated_preview):,}", None),
                ("Cells", f"{len(validated_preview.columns) - 1:,}", None),
                (
                    "Total counts",
                    f"{int(validated_preview.drop(columns=['gene']).to_numpy().sum()):,}",
                    None,
                ),
                (
                    "Input mode",
                    "Demo"
                    if not uploaded
                    else ("10x MTX ZIP" if source == "Upload 10x MTX ZIP" else "Uploaded table"),
                    None,
                ),
            ]
        )
        smart_dataframe(validated_preview.head(120), height=360, key="scrna_input_preview")
    except Exception as exc:
        st.error(f"Count matrix validation failed: {exc}")

cell_columns = [column for column in counts.columns if column != "gene"]
with metadata_tab:
    metadata_upload = st.file_uploader(
        "Optional cell metadata",
        type=["csv", "tsv"],
        help="Required column: cell. Optional: sample, batch, condition, donor.",
        key="scrna_metadata_upload",
    )
    metadata_upload_profile = render_upload_preflight(
        metadata_upload,
        key="scrna_metadata",
        allowed_extensions=["csv", "tsv"],
        soft_limit_mb=10,
        hard_limit_mb=50,
    )
    if metadata_upload:
        metadata = read_uploaded_table(metadata_upload)
    elif not h5ad_metadata.empty:
        metadata = h5ad_metadata.copy()
        for column, values in {
            "sample": [f"Sample_{1 + index % 4}" for index in range(len(metadata))],
            "batch": ["Batch_1"] * len(metadata),
            "condition": ["Unspecified"] * len(metadata),
        }.items():
            if column not in metadata.columns:
                metadata[column] = values
    else:
        metadata = pd.DataFrame(
            {
                "cell": cell_columns,
                "sample": [f"Sample_{1 + index % 4}" for index in range(len(cell_columns))],
                "batch": [f"Batch_{1 + index % 2}" for index in range(len(cell_columns))],
                "condition": [
                    "Reference" if index < len(cell_columns) / 2 else "Comparison"
                    for index in range(len(cell_columns))
                ],
            }
        )
    metadata = st.data_editor(
        metadata,
        width="stretch",
        height=330,
        hide_index=True,
        num_rows="dynamic",
        key="scrna_metadata_editor",
    )

with markers_tab:
    marker_panel = st.data_editor(
        default_cell_type_markers(),
        width="stretch",
        height=330,
        hide_index=True,
        num_rows="dynamic",
        key="scrna_marker_editor",
        column_config={
            "cell_type": st.column_config.TextColumn("Provisional cell type", required=True),
            "gene": st.column_config.TextColumn("Marker gene", required=True),
        },
    )
    st.caption(
        "Marker-based labels are provisional software annotations and require biological review."
    )

with settings_tab:
    with st.form("scrna_equal_depth_form"):
        section_title("QC and clustering parameters", "⚙")
        row1 = st.columns(4)
        min_counts = row1[0].number_input("Minimum counts per cell", 0, 100_000, 100, 50)
        min_genes = row1[1].number_input("Minimum detected genes", 1, 20_000, 30, 10)
        max_mito = row1[2].slider("Maximum mitochondrial %", 1.0, 60.0, 20.0, 1.0)
        clusters = row1[3].slider(
            "Requested clusters", 2, 12, min(4, max(2, len(cell_columns) // 12))
        )
        row2 = st.columns(4)
        max_hvg = max(50, len(counts))
        variable_genes = row2[0].slider(
            "Highly variable genes", 50, min(2_000, max_hvg), min(150, max_hvg), 25
        )
        random_state = row2[1].number_input("Random seed", 1, 9999, 42)
        stability_runs = row2[2].slider("Cluster stability runs", 3, 10, 3)
        marker_heatmap_genes = row2[3].slider("Marker heatmap genes", 8, 50, 20)
        row3 = st.columns(4)
        clustering_method = row3[0].selectbox(
            "Clustering", ["Leiden graph + UMAP", "KMeans + PCA"], index=0
        )
        graph_neighbors = row3[1].slider("Graph neighbours", 5, 50, 15)
        graph_resolution = row3[2].slider("Leiden resolution", 0.2, 3.0, 1.0, 0.1)
        exclude_doublets = row3[3].toggle("Exclude QC doublets", value=True)
        row4 = st.columns(4)
        compute_umap = row4[0].toggle(
            "Compute UMAP",
            value=False,
            help="UMAP gives a nonlinear embedding but can be slower on first run. The default graph-spectral embedding is deterministic and faster.",
        )
        simulated_doublets_enabled = row4[1].toggle("Simulated-doublet audit", value=True)
        ambient_enabled = row4[2].toggle("Ambient-RNA audit", value=True)
        include_matrices = row4[3].toggle("Include matrices in export", value=True)
        run = st.form_submit_button(
            "Run complete single-cell workbench", type="primary", width="stretch"
        )

if run:
    try:
        with analysis_run(
            "Filtering cells, normalizing expression and resolving heterogeneous populations"
        ):
            result = run_single_cell_pipeline(
                counts,
                min_counts=float(min_counts),
                min_genes=int(min_genes),
                max_mito_percent=float(max_mito),
                top_variable_genes=int(variable_genes),
                n_clusters=int(clusters),
                random_state=int(random_state),
                exclude_doublets=bool(exclude_doublets),
            )
            doublets = result.qc[
                [
                    column
                    for column in ["cell", "doublet_score", "doublet_flag", "pass_qc"]
                    if column in result.qc.columns
                ]
            ].copy()
            stability_seeds = [
                int(random_state) + index * 17 for index in range(int(stability_runs))
            ]
            graph_edges = pd.DataFrame()
            graph_metrics: dict[str, object] = {"method": "KMeans + PCA"}
            if clustering_method == "Leiden graph + UMAP":
                graph_result = graph_cluster_cells(
                    result.normalized,
                    result.variable_genes,
                    neighbors=int(graph_neighbors),
                    resolution=float(graph_resolution),
                    random_state=int(random_state),
                    minimum_clusters=2,
                    compute_umap=bool(compute_umap),
                )
                markers = find_cluster_markers(result.normalized, graph_result.embedding)
                summary = dict(result.summary)
                summary.update(
                    {
                        "clusters": int(graph_result.embedding["cluster"].nunique()),
                        "silhouette": float(graph_result.metrics["silhouette"]),
                        "clustering_method": str(graph_result.metrics["method"]),
                    }
                )
                result = replace(
                    result, embedding=graph_result.embedding, markers=markers, summary=summary
                )
                graph_edges = graph_result.neighbor_edges
                graph_metrics = graph_result.metrics
                stability = graph_cluster_stability(
                    result.normalized,
                    result.variable_genes,
                    neighbors=int(graph_neighbors),
                    resolution=float(graph_resolution),
                    random_seeds=stability_seeds,
                )
            else:
                stability = cluster_stability(
                    result.normalized,
                    result.variable_genes,
                    n_clusters=int(clusters),
                    random_seeds=stability_seeds,
                )
            marker_scores, annotations = annotate_clusters_by_markers(
                result.normalized, result.embedding, pd.DataFrame(marker_panel)
            )
            embedding = result.embedding.merge(annotations, on="cluster", how="left")
            metadata_frame = pd.DataFrame(metadata).copy()
            metadata_frame["cell"] = metadata_frame["cell"].astype(str)
            if metadata_frame["cell"].duplicated().any():
                raise ValueError("Cell metadata identifiers must be unique.")
            embedding = embedding.merge(
                metadata_frame, on="cell", how="left", validate="one_to_one"
            )
            top_marker_genes = (
                result.markers.sort_values("marker_score", ascending=False)["gene"]
                .drop_duplicates()
                .head(int(marker_heatmap_genes))
                .tolist()
            )
            average_expression = cluster_average_expression(
                result.normalized, result.embedding, top_marker_genes
            )
            simulated_doublets = (
                simulated_doublet_scores(
                    result.normalized, result.variable_genes, random_state=int(random_state)
                )
                if simulated_doublets_enabled
                else pd.DataFrame()
            )
            ambient_cells, ambient_genes = (
                ambient_rna_audit(result.filtered_counts)
                if ambient_enabled
                else (pd.DataFrame(), pd.DataFrame())
            )
            cycle = cell_cycle_scores(result.normalized)
            batch_corrected = pd.DataFrame()
            if (
                "batch" in metadata_frame.columns
                and metadata_frame["batch"].nunique(dropna=True) > 1
            ):
                batch_corrected = batch_residualized_embedding(
                    result.normalized,
                    result.variable_genes,
                    metadata_frame,
                    batch_column="batch",
                    random_state=int(random_state),
                )
            ligand_receptor = ligand_receptor_screen(result.normalized, result.embedding)
            parameters = {
                "minimum_counts": float(min_counts),
                "minimum_genes": int(min_genes),
                "maximum_mitochondrial_percent": float(max_mito),
                "highly_variable_genes": int(variable_genes),
                "clusters": int(clusters),
                "random_seed": int(random_state),
                "stability_runs": int(stability_runs),
                "exclude_heuristic_doublets": bool(exclude_doublets),
                "clustering_method": clustering_method,
                "graph_neighbors": int(graph_neighbors),
                "graph_resolution": float(graph_resolution),
                "simulated_doublet_audit": bool(simulated_doublets_enabled),
                "ambient_rna_audit": bool(ambient_enabled),
            }
            outputs = {
                "cell_qc": result.qc,
                "doublet_screen": doublets,
                "embedding_and_annotations": embedding,
                "cluster_markers": result.markers,
                "variable_genes": result.variable_genes,
                "cluster_stability": stability,
                "marker_annotation_scores": marker_scores,
                "cluster_annotations": annotations,
                "cluster_average_expression": average_expression,
                "neighbor_graph_edges": graph_edges,
                "simulated_doublet_screen": simulated_doublets,
                "ambient_rna_cell_audit": ambient_cells,
                "ambient_rna_gene_profile": ambient_genes,
                "cell_cycle_scores": cycle,
                "batch_residualized_embedding": batch_corrected,
                "ligand_receptor_screen": ligand_receptor,
            }
            if include_matrices:
                outputs["filtered_counts"] = result.filtered_counts
                outputs["log_normalized_expression"] = result.normalized
            inputs = {
                "count_matrix": counts,
                "cell_metadata": pd.DataFrame(metadata),
                "marker_panel": pd.DataFrame(marker_panel),
            }
            bundle = build_project_bundle(
                project_code=PROJECT_CODE,
                project_name=PROJECT_NAME,
                parameters=parameters,
                inputs=inputs,
                outputs=outputs,
                scientific_boundary=BOUNDARY,
                notes="Cluster labels and cell-type annotations are provisional and must be validated with independent biological evidence.",
            )
            batch_audit = batch_effect_audit(embedding, pd.DataFrame(metadata))
            cluster_quality = cluster_quality_metrics(result.embedding)
            pseudobulk = pseudobulk_expression(
                result.normalized, result.embedding, pd.DataFrame(metadata)
            )
            pseudobulk_raw = pseudobulk_counts(
                result.filtered_counts, result.embedding, pd.DataFrame(metadata)
            )
            specificity = marker_specificity(result.markers)
            trajectory_cells, trajectory_edges = trajectory_screen(result.embedding)
            dropout = dropout_profile(result.filtered_counts)
            outputs.update(
                {
                    "batch_effect_audit": batch_audit,
                    "cluster_quality_metrics": cluster_quality,
                    "pseudobulk_expression": pseudobulk,
                    "pseudobulk_raw_counts": pseudobulk_raw,
                    "marker_specificity": specificity,
                    "trajectory_cells": trajectory_cells,
                    "trajectory_edges": trajectory_edges,
                    "gene_dropout_profile": dropout,
                }
            )
            retention = float(result.summary["retention_percent"])
            mean_stability = (
                float(stability["adjusted_rand_index"].mean()) if not stability.empty else 0.0
            )
            max_batch_eta = (
                float(
                    batch_audit.loc[
                        batch_audit["covariate"] == "batch", "variance_explained_eta_squared"
                    ].max()
                )
                if not batch_audit.empty and (batch_audit["covariate"] == "batch").any()
                else 0.0
            )
            negative_silhouette = (
                float(cluster_quality["negative_silhouette_percent"].mean())
                if not cluster_quality.empty
                else 100.0
            )
            gates = quality_gate_table(
                [
                    QualityGate(
                        "SCRNA-RET",
                        "Cell retention",
                        "pass" if retention >= 60 else "review",
                        min(100.0, retention),
                        f"{retention:.1f}% cells retained",
                        "Review filtering thresholds and tissue-specific QC distributions.",
                    ),
                    QualityGate(
                        "SCRNA-STAB",
                        "Cluster stability",
                        "pass" if mean_stability >= 0.80 else "review",
                        100.0 * mean_stability,
                        f"Mean adjusted Rand index {mean_stability:.3f}",
                        "Compare resolutions and integration strategies.",
                    ),
                    QualityGate(
                        "SCRNA-SEP",
                        "Cluster separation",
                        "pass" if negative_silhouette <= 20 else "review",
                        max(0.0, 100.0 - negative_silhouette),
                        f"Mean negative silhouette {negative_silhouette:.1f}%",
                        "Investigate transitional states, doublets and over-clustering.",
                    ),
                    QualityGate(
                        "SCRNA-BATCH",
                        "Batch-effect screen",
                        "pass" if max_batch_eta <= 0.20 else "review",
                        max(0.0, 100.0 * (1.0 - max_batch_eta)),
                        f"Maximum batch eta-squared {max_batch_eta:.3f}",
                        "Use validated batch-aware integration and donor-aware statistics.",
                    ),
                    QualityGate(
                        "SCRNA-ANNOT",
                        "Annotation evidence",
                        "review",
                        60.0,
                        f"{len(annotations)} provisional cluster labels",
                        "Validate labels with multiple markers, references and biological review.",
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
                intended_use="Explore cellular heterogeneity in a validated genes-by-cells count matrix.",
                out_of_scope=[
                    "Clinical cell classification",
                    "Definitive lineage inference",
                    "Publication claims without donor-aware validation",
                ],
                methodology=[
                    "Cell QC and doublet heuristic",
                    "Log-normalization and HVG selection",
                    "PCA, kNN graph, Leiden clustering and UMAP",
                    "Stability, batch, marker-specificity and pseudobulk audits",
                ],
                metrics={
                    **result.summary,
                    "mean_cluster_stability": mean_stability,
                    "max_batch_eta_squared": max_batch_eta,
                    "negative_silhouette_percent": negative_silhouette,
                },
                validation=[
                    "Multi-seed cluster stability",
                    "Per-cluster silhouette quality",
                    "Batch variance screen",
                    "Marker specificity",
                    "Pseudobulk export",
                ],
                limitations=[
                    BOUNDARY,
                    "Graph/UMAP, simulated-doublet, ambient-RNA and ligand-receptor outputs are transparent local screens and require study-specific validation.",
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
                notes="Deep single-cell analysis and assurance bundle.",
                quality_gates=gates,
                summary={
                    "Input cells": int(result.summary["input_cells"]),
                    "Retained cells": int(result.summary["retained_cells"]),
                    "Clusters": int(result.summary["clusters"]),
                    "Mean stability": round(mean_stability, 4),
                    "Max batch eta-squared": round(max_batch_eta, 4),
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
                    "retention_percent": retention,
                    "mean_stability": mean_stability,
                    "max_batch_eta_squared": max_batch_eta,
                },
            )
        st.session_state["scrna_equal_depth_result"] = {
            "result": result,
            "doublets": doublets,
            "stability": stability,
            "marker_scores": marker_scores,
            "annotations": annotations,
            "embedding": embedding,
            "average_expression": average_expression,
            "bundle": bundle,
            "manifest": manifest,
            "batch_audit": batch_audit,
            "cluster_quality": cluster_quality,
            "pseudobulk": pseudobulk,
            "specificity": specificity,
            "trajectory_cells": trajectory_cells,
            "trajectory_edges": trajectory_edges,
            "dropout": dropout,
            "quality_gates": gates,
            "model_card": model_card,
            "graph_edges": graph_edges,
            "graph_metrics": graph_metrics,
            "simulated_doublets": simulated_doublets,
            "ambient_cells": ambient_cells,
            "ambient_genes": ambient_genes,
            "cell_cycle": cycle,
            "batch_corrected": batch_corrected,
            "ligand_receptor": ligand_receptor,
            "h5ad_audit": h5ad_audit,
        }
        st.toast("Single-cell workbench completed", icon="✅")
    except Exception as exc:
        st.error(f"Single-cell workbench could not run: {exc}")

payload = st.session_state.get("scrna_equal_depth_result")
if payload:
    result = payload["result"]
    metric_cards(
        [
            ("Input cells", f"{int(result.summary['input_cells']):,}", None),
            (
                "Retained cells",
                f"{int(result.summary['retained_cells']):,}",
                f"{result.summary['retention_percent']:.1f}% retention",
            ),
            ("Resolved clusters", f"{int(result.summary['clusters']):,}", None),
            ("Silhouette score", f"{result.summary['silhouette']:.3f}", None),
        ]
    )
    tabs = st.tabs(
        [
            "Executive summary",
            "Cell QC",
            "Embedding",
            "Cluster markers",
            "Provisional annotation",
            "Cluster comparison",
            "Stability",
            "Matrices",
            "Artefact & cell-state audits",
            "Batch & communication",
            "Deep assurance",
            "Exports & manifest",
        ]
    )
    with tabs[0]:
        cluster_summary = (
            payload["embedding"]
            .groupby(["cluster", "provisional_cell_type"], dropna=False)
            .size()
            .reset_index(name="cells")
        )
        smart_dataframe(cluster_summary, height=300)
        st.plotly_chart(
            px.bar(
                cluster_summary,
                x="cluster",
                y="cells",
                color="provisional_cell_type",
                title="Resolved cell populations",
            ),
            width="stretch",
        )
        insight_callout(
            "Scientific interpretation",
            "A strong silhouette score or stable clustering does not establish biological identity. Review marker specificity, batch structure and independent references.",
            "warning",
        )
    with tabs[1]:
        qc = result.qc.copy()
        for col_name in ["pass_qc", "doublet_flag", "doublet_score"]:
            if col_name not in qc.columns:
                candidates = [c for c in qc.columns if c.startswith(col_name)]
                if candidates:
                    qc[col_name] = qc[candidates[0]]
                elif col_name == "pass_qc":
                    qc["pass_qc"] = True
                elif col_name == "doublet_flag":
                    qc["doublet_flag"] = False
                elif col_name == "doublet_score":
                    qc["doublet_score"] = 0.0

        clean_cols = [c for c in qc.columns if not (c.endswith("_x") or c.endswith("_y"))]
        qc = qc[clean_cols].copy()
        left, right = st.columns(2)
        with left:
            st.plotly_chart(
                px.scatter(
                    qc,
                    x="total_counts",
                    y="detected_genes",
                    color="pass_qc",
                    size="mitochondrial_percent",
                    hover_name="cell",
                    title="Cell QC landscape",
                ),
                width="stretch",
            )
        with right:
            st.plotly_chart(
                px.histogram(
                    qc,
                    x="doublet_score",
                    color="doublet_flag",
                    nbins=30,
                    title="Heuristic doublet screen",
                ),
                width="stretch",
            )
        smart_dataframe(qc, height=480)
    with tabs[2]:
        color_choice = st.selectbox(
            "Colour embedding by",
            ["cluster", "provisional_cell_type", "sample", "batch", "condition"],
            key="scrna_embedding_color",
        )
        available_color = (
            color_choice if color_choice in payload["embedding"].columns else "cluster"
        )
        x_axis, y_axis = (
            ("UMAP1", "UMAP2")
            if {"UMAP1", "UMAP2"}.issubset(payload["embedding"].columns)
            else ("PC1", "PC2")
        )
        st.plotly_chart(
            px.scatter(
                payload["embedding"],
                x=x_axis,
                y=y_axis,
                color=available_color,
                hover_name="cell",
                hover_data=["cluster", "provisional_cell_type"],
                title=f"{x_axis.replace('1', '')} cell embedding",
            ),
            width="stretch",
        )
        smart_json(
            payload["graph_metrics"], title="Graph-clustering audit", key="scrna_graph_metrics"
        )
        if "PC3" in payload["embedding"].columns:
            st.plotly_chart(
                px.scatter_3d(
                    payload["embedding"],
                    x="PC1",
                    y="PC2",
                    z="PC3",
                    color=available_color,
                    hover_name="cell",
                    title="Three-dimensional PCA view",
                ),
                width="stretch",
            )
        smart_dataframe(payload["embedding"], height=420)
    with tabs[3]:
        selected_cluster = st.selectbox(
            "Marker table cluster",
            sorted(result.markers["cluster"].unique()),
            key="scrna_marker_cluster",
        )
        selected = result.markers[result.markers["cluster"] == selected_cluster].sort_values(
            "marker_score", ascending=False
        )
        st.plotly_chart(
            px.bar(
                selected.head(20).sort_values("marker_score"),
                x="marker_score",
                y="gene",
                orientation="h",
                title=f"Top markers · {selected_cluster}",
            ),
            width="stretch",
        )
        smart_dataframe(result.markers, height=500)
    with tabs[4]:
        st.plotly_chart(
            px.bar(
                payload["marker_scores"],
                x="cluster",
                y="mean_marker_score",
                color="cell_type",
                barmode="group",
                title="Marker-panel scores by cluster",
            ),
            width="stretch",
        )
        left, right = st.columns(2)
        with left:
            smart_dataframe(payload["annotations"], height=330)
        with right:
            smart_dataframe(payload["marker_scores"], height=330)
        insight_callout(
            "Annotation boundary",
            "Labels are provisional because marker panels can be incomplete, non-specific or context dependent.",
            "warning",
        )
    with tabs[5]:
        clusters_available = sorted(result.embedding["cluster"].unique())
        compare_cols = st.columns(2)
        cluster_a = compare_cols[0].selectbox(
            "Reference cluster", clusters_available, index=0, key="scrna_compare_a"
        )
        cluster_b = compare_cols[1].selectbox(
            "Comparison cluster",
            clusters_available,
            index=min(1, len(clusters_available) - 1),
            key="scrna_compare_b",
        )
        if cluster_a == cluster_b:
            st.info("Choose two different clusters for differential screening.")
        else:
            comparison = differential_expression_between_clusters(
                result.normalized,
                result.embedding,
                cluster_a=cluster_a,
                cluster_b=cluster_b,
                top_n=250,
            )
            st.plotly_chart(
                px.scatter(
                    comparison,
                    x="log_expression_difference",
                    y="screening_score",
                    color="direction",
                    hover_name="gene",
                    title="Cluster differential-expression screen",
                ),
                width="stretch",
            )
            smart_dataframe(comparison, height=470)
            st.download_button(
                "Download cluster comparison",
                comparison.to_csv(index=False),
                "single_cell_cluster_comparison.csv",
                "text/csv",
                width="stretch",
            )
        if not payload["average_expression"].empty:
            heatmap = payload["average_expression"].set_index("gene")
            st.plotly_chart(
                px.imshow(
                    heatmap,
                    aspect="auto",
                    title="Average expression of top marker genes by cluster",
                ),
                width="stretch",
            )
    with tabs[6]:
        st.plotly_chart(
            px.bar(
                payload["stability"],
                x="comparison_seed",
                y="adjusted_rand_index",
                title="Cluster stability across random seeds",
            ),
            width="stretch",
        )
        smart_dataframe(payload["stability"], height=330)
        mean_stability = float(payload["stability"]["adjusted_rand_index"].mean())
        insight_callout(
            "Stability interpretation",
            f"Mean adjusted Rand index: {mean_stability:.3f}. Stability is one quality signal and should be assessed alongside batch effects and biological coherence.",
            "info",
        )
    with tabs[7]:
        matrix_choice = st.radio(
            "Matrix",
            ["Filtered counts", "Log-normalized expression", "Variable-gene statistics"],
            horizontal=True,
        )
        if matrix_choice == "Filtered counts":
            smart_dataframe(result.filtered_counts, height=520)
        elif matrix_choice == "Log-normalized expression":
            smart_dataframe(result.normalized, height=520)
        else:
            st.plotly_chart(
                px.scatter(
                    result.variable_genes,
                    x="mean_expression",
                    y="dispersion",
                    color="highly_variable",
                    hover_name="gene",
                    title="Highly variable gene selection",
                ),
                width="stretch",
            )
            smart_dataframe(result.variable_genes, height=500)
    with tabs[8]:
        left, right = st.columns(2)
        with left:
            section_title("Simulated-doublet and ambient-RNA screens", "◉")
            if not payload["simulated_doublets"].empty:
                st.plotly_chart(
                    px.histogram(
                        payload["simulated_doublets"],
                        x="simulated_doublet_score",
                        color="simulated_doublet_flag",
                        title="Simulated-neighbour doublet scores",
                    ),
                    width="stretch",
                )
                smart_dataframe(payload["simulated_doublets"], height=280)
            if not payload["ambient_cells"].empty:
                smart_dataframe(payload["ambient_cells"], height=280)
        with right:
            section_title("Cell-cycle and ambient-gene audit", "⌁")
            smart_dataframe(payload["cell_cycle"], height=300)
            if not payload["ambient_genes"].empty:
                st.plotly_chart(
                    px.bar(
                        payload["ambient_genes"].head(25).sort_values("ambient_fraction"),
                        x="ambient_fraction",
                        y="gene",
                        orientation="h",
                        title="Top ambient-profile genes",
                    ),
                    width="stretch",
                )
        insight_callout(
            "Artefact boundary",
            "These local screens prioritize review; they do not replace tissue-specific empty-droplet, ambient-RNA or validated doublet models.",
            "warning",
        )
    with tabs[9]:
        left, right = st.columns(2)
        with left:
            section_title("Batch-residualized representation", "◫")
            if not payload["batch_corrected"].empty:
                st.plotly_chart(
                    px.scatter(
                        payload["batch_corrected"],
                        x="batch_corrected_PC1",
                        y="batch_corrected_PC2",
                        color="batch",
                        hover_name="cell",
                        title="Batch-residualized PCA diagnostic",
                    ),
                    width="stretch",
                )
                smart_dataframe(payload["batch_corrected"], height=280)
            else:
                st.info("Add at least two batches to generate a residualized diagnostic embedding.")
        with right:
            section_title("Ligand–receptor co-expression screen", "↔")
            if not payload["ligand_receptor"].empty:
                smart_dataframe(payload["ligand_receptor"].head(500), height=450)
            else:
                st.info("No bundled ligand–receptor pair passed the expression threshold.")
        insight_callout(
            "Communication boundary",
            "Ligand–receptor scores are cluster-average co-expression screens, not causal cell–cell communication evidence.",
            "warning",
        )
    with tabs[10]:
        section_title("Deep single-cell assurance", "✓")
        left, right = st.columns(2)
        with left:
            section_title("Batch and cluster diagnostics", "◫")
            smart_dataframe(payload["batch_audit"], height=300)
            smart_dataframe(payload["cluster_quality"], height=300)
        with right:
            section_title("Marker specificity and dropout", "⌁")
            st.plotly_chart(
                px.scatter(
                    payload["specificity"].head(250),
                    x="best_marker_score",
                    y="specificity_margin",
                    color="best_cluster",
                    hover_name="gene",
                    title="Marker specificity landscape",
                ),
                width="stretch",
            )
            smart_dataframe(payload["dropout"].head(300), height=280)
        if not payload["trajectory_cells"].empty:
            st.plotly_chart(
                px.scatter(
                    payload["trajectory_cells"],
                    x="PC1",
                    y="PC2",
                    color="screening_pseudotime",
                    hover_name="cell",
                    title="Exploratory geometry-based pseudotime screen",
                ),
                width="stretch",
            )
        section_title("Pseudobulk research matrix", "▦")
        smart_dataframe(payload["pseudobulk"].head(1000), height=360)
        smart_dataframe(payload["quality_gates"], height=340)
        insight_callout(
            "Inference boundary",
            "The trajectory and batch screens are diagnostics, not definitive developmental lineage or corrected expression inference.",
            "warning",
        )
    with tabs[11]:
        smart_json(
            payload["model_card"],
            title="Single-cell method card",
            download_name="single_cell_method_card.json",
            key="scrna_method_card",
        )
        smart_json(
            payload["manifest"],
            title="Reproducibility manifest",
            download_name="single_cell_manifest.json",
            key="scrna_manifest_download",
        )
        st.download_button(
            "Download complete single-cell project bundle (.zip)",
            payload["bundle"],
            "BIO-SCRNA_project_bundle.zip",
            "application/zip",
            width="stretch",
            key="scrna_bundle_download",
        )
else:
    section_title("Professional capability map", "▦")
    smart_dataframe(
        pd.DataFrame(
            [
                (
                    "Input & QC",
                    "Genes-by-cells validation, cell metadata, mitochondrial/ribosomal metrics and threshold filtering",
                ),
                (
                    "Artefact screen",
                    "QC and simulated-neighbour doublet screens plus ambient-RNA review",
                ),
                (
                    "Representation",
                    "Library-size normalization, HVG selection, PCA, kNN graph and UMAP",
                ),
                (
                    "Clustering",
                    "Leiden graph or KMeans populations, silhouette quality and multi-seed stability",
                ),
                (
                    "Biology",
                    "Cluster markers, editable marker panel, provisional annotation and cluster comparison",
                ),
                (
                    "Reproducibility",
                    "SHA-256 manifest, matrices and complete downloadable project bundle",
                ),
            ],
            columns=["Layer", "Implemented capability"],
        ),
        height=370,
    )

# Step 110 advanced scientific viewers
from biointel.ui.advanced_scientific_viewers import render_embedded_viewer as _render_step110_viewer

_render_step110_viewer("single_cell", key_prefix="step110_80_Single_Cell_Heterogeneity_single_cell")

# Step 115 scientific depth, validation and optimization layer
from biointel.scientific_depth import render_depth_upgrade_panel as _render_step114_depth

_render_step114_depth("single_cell_core", None, key_prefix="step114_single_cell_core", expanded=False)

# Step 115 non-chart visual: single_cell_canvas
from biointel.ui.non_chart_scientific_visuals import render_non_chart_visual as _render_step115_non_chart
_render_step115_non_chart("single_cell_canvas", key_prefix="step115_80_Single_Cell_Heterogeneity_single_cell_canvas", expanded=False)

# STEP127_SCIENTIFIC_DEPTH_SINGLE_CELL
from biointel.step127.ui import render_step127_upgrade_panel as _render_step127_upgrade_panel
_render_step127_upgrade_panel('single_cell', expanded=False)

# Targeted peak-potential assurance for Genomics, Discovery, Omics, Lab and Translational modules.
from biointel.peak_potential.ui import render_peak_session_footer
render_peak_session_footer(page_key='single_cell_heterogeneity', title='Single-Cell Heterogeneity', category='Bioinformatics')

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='single_cell_heterogeneity', title='Single-Cell Heterogeneity', category='Bioinformatics')

# STEP177_21_MODULE_MODEL_COHORT_RUNTIME_EXCELLENCE
from biointel.target_modules_v177.ui import render_step177_module_upgrade
render_step177_module_upgrade('single_cell_core', expanded=False)

# Step 183 all-module synthetic demo bundle
from biointel.portfolio_demo_v183.ui import render_step183_portfolio_demo as _render_step183_portfolio_demo
_render_step183_portfolio_demo("single_cell_core", expanded=False)

# Step 184 advanced deterministic demo assurance
from biointel.demo_assurance_v184.ui import render_step184_demo_assurance as _render_step184_demo_assurance
_render_step184_demo_assurance("single_cell_core", expanded=False)

# STEP188_MAJOR_MODULE_STANDARD_HOOK
from biointel.major_module_standard_v188.ui import render_step188_major_module_standard as _render_step188_major_module_standard
_render_step188_major_module_standard('single_cell_core', expanded=False)

# STEP189_UNIVERSAL_PLATFORM_HOOK
from biointel.universal_platform_v189.ui import render_step189_universal_platform as _render_step189_universal_platform
_render_step189_universal_platform('single_cell_core', expanded=False)

# STEP190_SCIENTIFIC_EXECUTION_HOOK
from biointel.scientific_execution_v190.ui import render_step190_scientific_execution as _render_step190_scientific_execution
_render_step190_scientific_execution('single_cell_core', expanded=False)

# STEP192_RELEASE_INTEGRITY_PUBLICATION_HOOK
from biointel.release_integrity_v192.ui import render_step192_release_integrity as _render_step192_release_integrity
_render_step192_release_integrity('single_cell_core', expanded=False)


# STEP193_MANDATORY_COMPLETION_HOOK
from biointel.mandatory_completion_v193.ui import render_step193_mandatory_completion as _render_step193_mandatory_completion
_render_step193_mandatory_completion('single_cell_core', expanded=False)

