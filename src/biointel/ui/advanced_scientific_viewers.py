from __future__ import annotations

import hashlib
import io
import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from Bio import Phylo
from PIL import Image
from scipy import ndimage

from biointel.ui.components import scientific_chart_card
from biointel.ui.operational_canvas import render_operational_canvas


@dataclass(frozen=True)
class AdvancedViewerSpec:
    key: str
    title: str
    icon: str
    description: str
    modules: tuple[str, ...]
    input_types: tuple[str, ...]
    evidence_status: str = "demo"


@dataclass(frozen=True)
class ViewerVisual:
    title: str
    interpretation: str
    method: str
    figure: go.Figure
    data: pd.DataFrame
    units: str | None = None
    source_count: int | None = None
    aggregation_note: str | None = None


ADVANCED_VIEWER_CATALOG: dict[str, AdvancedViewerSpec] = {
    "genome_browser": AdvancedViewerSpec(
        "genome_browser", "Interactive Genome Browser", "🧬",
        "Explore reference coordinates, gene models, coverage, variants, peaks and splice junctions in synchronized genomic tracks.",
        ("Variant Workbench", "GWAS", "Epigenomics", "RNA Splicing", "CRISPR", "Cancer Genomics", "Structural Variants"),
        ("VCF/VCF.GZ", "BED/GFF/GTF", "SAM", "BAM/CRAM via samtools"),
    ),
    "molecular_3d": AdvancedViewerSpec(
        "molecular_3d", "3D Molecular Structure Viewer", "🧩",
        "Inspect chains, ligands, pockets, contacts, mutations and confidence in an interactive three-dimensional scene.",
        ("Structural Bioinformatics", "Docking", "Antibody Engineering", "Protein Design", "Enzyme Engineering"),
        ("PDB", "mmCIF/CIF"),
    ),
    "pathology": AdvancedViewerSpec(
        "pathology", "Whole-Slide Pathology & Spatial Overlay", "🔬",
        "Navigate tissue imagery with adjustable expression, segmentation and region-of-interest overlays.",
        ("Spatial Omics", "Digital Pathology", "Cancer Genomics"),
        ("PNG/JPEG/TIFF/OME-TIFF", "Spatial coordinates CSV", "SVS/NDPI via OpenSlide"),
    ),
    "microscopy": AdvancedViewerSpec(
        "microscopy", "Microscopy Segmentation Overlay Editor", "🧫",
        "Review raw images, thresholded masks, labelled objects, morphology and correction-ready segmentation overlays.",
        ("Bioimage & Microscopy", "Organoid Analytics", "High-Content Screening"),
        ("PNG", "JPEG", "TIFF"),
    ),
    "flow_gating": AdvancedViewerSpec(
        "flow_gating", "Flow-Cytometry Gating Canvas", "🧪",
        "Explore FSC/SSC or marker channels, apply rectangular/quadrant gates and inspect population statistics.",
        ("Flow Cytometry", "Wet-Lab Biotechnology", "Immunology"),
        ("Native FCS", "CSV/TSV"),
    ),
    "mass_spectrometry": AdvancedViewerSpec(
        "mass_spectrometry", "Mass-Spectrometry & Chromatogram Viewer", "⚗️",
        "Inspect TIC/BPC chromatograms, MS1/MS2 spectra, isotope patterns, peak integration and library comparisons.",
        ("Metabolomics", "Proteomics", "Glycomics"),
        ("Native mzML/mzML.GZ", "Native MGF/MGF.GZ", "Peak tables"),
    ),
    "phylogenetic_tree": AdvancedViewerSpec(
        "phylogenetic_tree", "Interactive Phylogenetic Tree", "🌳",
        "Explore branch lengths, bootstrap support, clades and sample metadata in a zoomable tree.",
        ("Alignment & Phylogeny", "Pathogen Genomics", "Virology"),
        ("Newick/NWK/TREE", "Nexus"),
    ),
    "plate_map": AdvancedViewerSpec(
        "plate_map", "Interactive Plate Map & QC Overlay", "🧬",
        "Design and review 96/384-well layouts, standards, controls, replicate placement and spatial quality patterns.",
        ("ELISA", "qPCR", "High-Content Screening", "Wet-Lab Biotechnology"),
        ("Plate CSV", "Instrument export"),
    ),
    "pedigree": AdvancedViewerSpec(
        "pedigree", "Pedigree & Variant Segregation Viewer", "👪",
        "Visualize family relationships, affected status, genotypes, carriers and segregation consistency.",
        ("Rare Disease", "Family Genetics", "Pharmacogenomics"),
        ("PED", "Family CSV", "Variant table"),
    ),
    "outbreak_map": AdvancedViewerSpec(
        "outbreak_map", "Geographic Outbreak Map with Timeline", "🗺️",
        "Review locations, dates, genomic clusters, hosts, AMR signals and transmission links over time.",
        ("One Health", "Pathogen Outbreak", "Comparative Pathogen Genomics"),
        ("Sample metadata CSV", "GeoJSON-compatible coordinates"),
    ),
    "pangenome_graph": AdvancedViewerSpec(
        "pangenome_graph", "Pangenome Variation-Graph Explorer", "🕸️",
        "Inspect sequence-segment nodes, reference/sample paths, bubbles, coverage and core/accessory regions.",
        ("Pangenome Studio",),
        ("Native GFA/GFA1/GFA2", "CSV node/edge tables"),
    ),
    "single_cell": AdvancedViewerSpec(
        "single_cell", "Single-Cell Embedding Explorer", "🔭",
        "Explore UMAP-like embeddings by cluster, condition, batch, expression, pseudotime and selected cells.",
        ("Single-Cell", "Cell Atlas", "Perturb-seq"),
        ("Native H5AD", "Matrix Market", "CSV/TSV"),
    ),
    "sequence_track": AdvancedViewerSpec(
        "sequence_track", "Sequence & Protein Feature Track", "🧬",
        "Inspect domains, exons, motifs, PTMs, transmembrane regions, disorder, mutations and active sites along a sequence.",
        ("Protein Annotation", "CRISPR", "RNA Isoforms", "Protein Design"),
        ("Native FASTA", "GFF/GTF/BED", "Feature CSV"),
    ),
    "multiomics": AdvancedViewerSpec(
        "multiomics", "Multi-Omics Relationship Explorer", "🔗",
        "Trace gene-to-protein-to-metabolite-to-pathway relationships using Sankey, overlap and concordance views.",
        ("Omics Integration", "Biomarker Discovery", "Batch Correction"),
        ("Cross-omics mapping CSV",),
    ),
    "bioprocess_live": AdvancedViewerSpec(
        "bioprocess_live", "Live Bioprocess & Instrument Dashboard", "🏭",
        "Monitor process trajectories, control limits, feed events, alarms, golden batches and endpoint forecasts.",
        ("Bioprocess", "Fermentation", "Instrument Integration"),
        ("Historian CSV", "Sensor stream export"),
    ),
    "workflow_dag": AdvancedViewerSpec(
        "workflow_dag", "Workflow DAG Execution Monitor", "🔀",
        "Inspect dependencies, critical path, node status, runtime, resource use and failure propagation.",
        ("Visual Workflow Builder", "Workflow Dashboard"),
        ("Workflow JSON", "Execution event CSV"),
    ),
    "freezer_map": AdvancedViewerSpec(
        "freezer_map", "Freezer, Rack & Sample Map", "🧊",
        "Navigate storage hierarchy, occupied positions, sample risk, expiry and aliquot lineage.",
        ("LIMS/ELN", "Sample Registry", "Data Lakehouse"),
        ("Inventory CSV",),
    ),
    "static_reporting": AdvancedViewerSpec(
        "static_reporting", "Offline Static Visual Report Renderer", "📄",
        "Generate deterministic SVG/HTML/JSON/data bundles and readiness checks for PDF, DOCX and presentation reporting.",
        ("Visual Workspace", "Report Studio"),
        ("Plotly JSON", "CSV"),
    ),
    "visual_regression": AdvancedViewerSpec(
        "visual_regression", "Visual Regression & State Coverage", "🧪",
        "Track page/theme/state baselines, semantic fingerprints, changed regions and review status.",
        ("Platform Quality", "Visual Workspace"),
        ("Baseline manifest JSON", "PNG screenshots"),
    ),
}


def _rng(seed: int | str) -> np.random.Generator:
    if isinstance(seed, str):
        seed = sum((index + 1) * ord(char) for index, char in enumerate(seed)) % (2**32 - 1)
    return np.random.default_rng(int(seed))


def _visual(title: str, interpretation: str, method: str, figure: go.Figure, data: pd.DataFrame,
            units: str | None = None, source_count: int | None = None,
            aggregation_note: str | None = None) -> ViewerVisual:
    figure.update_layout(margin=dict(l=45, r=20, t=70, b=45), height=560, legend_title_text="")
    return ViewerVisual(title, interpretation, method, figure, data.reset_index(drop=True), units,
                        source_count, aggregation_note)


def _genome_browser(seed: int = 110) -> list[ViewerVisual]:
    from .advanced_viewer_builders_core import _genome_browser as implementation
    return implementation(seed)


def _parse_pdb_atoms(text: str) -> pd.DataFrame:
    from .advanced_viewer_builders_core import _parse_pdb_atoms as implementation
    return implementation(text)


def _demo_atoms(seed: int = 111) -> pd.DataFrame:
    from .advanced_viewer_builders_core import _demo_atoms as implementation
    return implementation(seed)


def _molecular_3d(seed: int = 111, pdb_text: str | None = None) -> list[ViewerVisual]:
    from .advanced_viewer_builders_core import _molecular_3d as implementation
    return implementation(seed, pdb_text)


def _synthetic_tissue(seed: int = 112, size: int = 220) -> tuple[np.ndarray, np.ndarray, pd.DataFrame]:
    from .advanced_viewer_builders_core import _synthetic_tissue as implementation
    return implementation(seed, size)


def _pathology(seed: int = 112, image: np.ndarray | None = None, overlay_opacity: float = 0.55) -> list[ViewerVisual]:
    from .advanced_viewer_builders_core import _pathology as implementation
    return implementation(seed, image, overlay_opacity)


def _microscopy(seed: int = 113, image: np.ndarray | None = None, threshold: float = 0.58, min_size: int = 20) -> list[ViewerVisual]:
    from .advanced_viewer_builders_core import _microscopy as implementation
    return implementation(seed, image, threshold, min_size)


def _flow_gating(seed: int = 114, x_gate: float = 55_000, y_gate: float = 45_000) -> list[ViewerVisual]:
    from .advanced_viewer_builders_core import _flow_gating as implementation
    return implementation(seed, x_gate, y_gate)


def _mass_spectrometry(seed: int = 115) -> list[ViewerVisual]:
    from .advanced_viewer_builders_core import _mass_spectrometry as implementation
    return implementation(seed)


def _tree_coordinates(newick: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    tree = Phylo.read(io.StringIO(newick), "newick")
    terminals = tree.get_terminals()
    y_map = {clade: float(index) for index, clade in enumerate(terminals)}
    x_map = tree.depths(unit_branch_lengths=False)
    if not max(x_map.values(), default=0):
        x_map = tree.depths(unit_branch_lengths=True)
    def assign_y(clade: Any) -> float:
        if clade in y_map:
            return y_map[clade]
        children = [assign_y(child) for child in clade.clades]
        y_map[clade] = float(np.mean(children)) if children else 0.0
        return y_map[clade]
    assign_y(tree.root)
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for clade in tree.find_clades(order="preorder"):
        nodes.append({"name": clade.name or "internal", "x": float(x_map.get(clade, 0)), "y": float(y_map.get(clade, 0)), "confidence": clade.confidence})
        for child in clade.clades:
            edges.append({"x0": float(x_map.get(clade, 0)), "y0": float(y_map.get(clade, 0)), "x1": float(x_map.get(child, 0)), "y1": float(y_map.get(child, 0))})
    return pd.DataFrame(nodes), pd.DataFrame(edges)


def _phylogenetic_tree(seed: int = 116, newick: str | None = None) -> list[ViewerVisual]:
    default_newick = "((Sample_A:0.12,Sample_B:0.15)92:0.10,((Sample_C:0.08,Sample_D:0.09)85:0.14,(Sample_E:0.11,Sample_F:0.13)78:0.12)88:0.07,Sample_G:0.31);"
    try:
        nodes, edges = _tree_coordinates((newick or default_newick).strip())
    except Exception:
        nodes, edges = _tree_coordinates(default_newick)
    fig = go.Figure()
    for row in edges.itertuples():
        fig.add_trace(go.Scatter(x=[row.x0, row.x1, row.x1], y=[row.y0, row.y0, row.y1], mode="lines", line={"width": 2}, showlegend=False, hoverinfo="skip"))
    leaves = nodes[nodes["name"] != "internal"]
    internals = nodes[nodes["name"] == "internal"]
    fig.add_trace(go.Scatter(x=leaves["x"], y=leaves["y"], mode="markers+text", text=leaves["name"], textposition="middle right", marker={"size": 9}, name="Samples"))
    fig.add_trace(go.Scatter(x=internals["x"], y=internals["y"], mode="markers", marker={"size": 5}, name="Internal nodes"))
    fig.update_layout(title="Interactive rectangular phylogenetic tree", xaxis_title="Branch length", yaxis={"showticklabels": False})
    branch = edges.copy()
    branch["length"] = np.sqrt((branch["x1"] - branch["x0"]) ** 2 + (branch["y1"] - branch["y0"]) ** 2)
    fig2 = px.histogram(branch, x="length", nbins=15, marginal="box", title="Branch-length distribution")
    leaf_dist = leaves[["name", "x"]].rename(columns={"x": "root_to_tip_distance"})
    fig3 = px.bar(leaf_dist.sort_values("root_to_tip_distance", ascending=False), x="name", y="root_to_tip_distance", title="Root-to-tip distance")
    return [
        _visual("Interactive phylogenetic tree", "Supports zooming, sample search by hover and branch-length inspection.", "Newick branch-coordinate rendering", fig, nodes, "Substitutions/site", len(nodes)),
        _visual("Branch-length distribution", "Highlights unusually long branches and potential outliers.", "Tree edge-length distribution", fig2, branch, "Branch length"),
        _visual("Root-to-tip distance", "Compares accumulated evolutionary distance for terminal samples.", "Root depth by terminal", fig3, leaf_dist, "Substitutions/site"),
    ]


def _plate_map(seed: int = 117, rows: int = 8, columns: int = 12) -> list[ViewerVisual]:
    rng = _rng(seed)
    row_names = [chr(65 + i) for i in range(rows)]
    records = []
    for r, row in enumerate(row_names):
        for col in range(1, columns + 1):
            edge = r in {0, rows - 1} or col in {1, columns}
            role = "Blank" if col == 1 else "Standard" if col in {2, 3} else "Control" if col in {11, 12} else "Sample"
            value = rng.normal(1.0 + (0.12 if edge else 0), 0.12)
            records.append({"well": f"{row}{col}", "row": row, "column": col, "role": role, "value": value, "edge": edge})
    data = pd.DataFrame(records)
    pivot = data.pivot(index="row", columns="column", values="value")
    text = data.pivot(index="row", columns="column", values="well")
    fig = go.Figure(go.Heatmap(z=pivot.values, x=pivot.columns, y=pivot.index, text=text.values, hovertemplate="Well %{text}<br>Signal %{z:.3f}<extra></extra>", colorbar={"title": "Signal"}))
    fig.update_layout(title=f"{rows * columns}-well plate signal and QC overlay", xaxis_title="Column", yaxis_title="Row")
    role_summary = data.groupby("role", as_index=False).agg(mean_signal=("value", "mean"), wells=("well", "size"), cv=("value", lambda s: 100 * s.std(ddof=1) / max(s.mean(), 1e-9)))
    fig2 = px.bar(role_summary, x="role", y="mean_signal", error_y="cv", text="wells", title="Plate role summary")
    edge_summary = data.groupby("edge", as_index=False).agg(mean_signal=("value", "mean"), sd=("value", "std"))
    edge_summary["region"] = edge_summary["edge"].map({True: "Edge wells", False: "Interior wells"})
    fig3 = px.bar(edge_summary, x="region", y="mean_signal", error_y="sd", title="Edge-effect comparison")
    return [
        _visual("Plate map and QC overlay", "Displays well-level signal, layout and spatial anomalies.", "Interactive heatmap over plate coordinates", fig, data, "Relative signal", len(data)),
        _visual("Standards, controls and samples", "Compares mean signal and variation across plate roles.", "Role-level aggregation", fig2, role_summary, "Relative signal / CV%"),
        _visual("Edge-effect assessment", "Compares edge and interior wells to reveal evaporation or reader-position bias.", "Spatial plate-region comparison", fig3, edge_summary, "Relative signal"),
    ]


def _pedigree(seed: int = 118) -> list[ViewerVisual]:
    nodes = pd.DataFrame([
        {"id": "I-1", "x": 1, "y": 3, "sex": "M", "affected": False, "genotype": "0/1", "role": "Grandfather"},
        {"id": "I-2", "x": 3, "y": 3, "sex": "F", "affected": False, "genotype": "0/0", "role": "Grandmother"},
        {"id": "II-1", "x": 2, "y": 2, "sex": "F", "affected": False, "genotype": "0/1", "role": "Mother"},
        {"id": "II-2", "x": 5, "y": 2, "sex": "M", "affected": False, "genotype": "0/1", "role": "Father"},
        {"id": "III-1", "x": 2.8, "y": 1, "sex": "F", "affected": False, "genotype": "0/0", "role": "Sibling"},
        {"id": "III-2", "x": 4.2, "y": 1, "sex": "M", "affected": True, "genotype": "1/1", "role": "Proband"},
    ])
    edges = pd.DataFrame([
        {"source": "I-1", "target": "II-1"}, {"source": "I-2", "target": "II-1"},
        {"source": "II-1", "target": "III-1"}, {"source": "II-2", "target": "III-1"},
        {"source": "II-1", "target": "III-2"}, {"source": "II-2", "target": "III-2"},
    ])
    by_id = nodes.set_index("id")
    fig = go.Figure()
    for edge in edges.itertuples():
        a, b = by_id.loc[edge.source], by_id.loc[edge.target]
        fig.add_trace(go.Scatter(x=[a.x, b.x], y=[a.y, b.y], mode="lines", line={"width": 2}, showlegend=False, hoverinfo="skip"))
    for sex, symbol in (("M", "square"), ("F", "circle")):
        subset = nodes[nodes["sex"] == sex]
        fig.add_trace(go.Scatter(x=subset["x"], y=subset["y"], mode="markers+text", text=subset["id"], textposition="bottom center", marker={"size": 28, "symbol": symbol, "color": np.where(subset["affected"], 1, 0), "colorscale": [[0, "white"], [1, "black"]], "line": {"width": 2, "color": "black"}}, customdata=subset[["role", "genotype", "affected"]], hovertemplate="%{text}<br>%{customdata[0]}<br>Genotype %{customdata[1]}<br>Affected %{customdata[2]}<extra></extra>", name=sex))
    fig.update_layout(title="Pedigree and genotype segregation", xaxis={"visible": False}, yaxis={"visible": False}, showlegend=False)
    genotype_summary = nodes.groupby(["genotype", "affected"], as_index=False).size().rename(columns={"size": "people"})
    fig2 = px.bar(genotype_summary, x="genotype", y="people", color="affected", barmode="group", title="Genotype and phenotype distribution")
    consistency = pd.DataFrame([{"check": "Mendelian inheritance", "status": "Pass", "score": 1.0}, {"check": "Affected segregation", "status": "Consistent", "score": 0.92}, {"check": "Missing genotypes", "status": "None", "score": 1.0}, {"check": "Phenotype completeness", "status": "Complete", "score": 1.0}])
    fig3 = px.bar(consistency, x="check", y="score", color="status", range_y=[0, 1.05], title="Segregation quality checks")
    return [
        _visual("Pedigree and segregation", "Shows family structure, affected status and genotype inheritance.", "Pedigree node-edge rendering", fig, nodes, "Family generation", len(nodes)),
        _visual("Genotype/phenotype composition", "Summarises carriers, homozygotes and affected status.", "Family genotype aggregation", fig2, genotype_summary, "People"),
        _visual("Segregation checks", "Highlights inheritance consistency and missing-data blockers.", "Rule-based segregation review", fig3, consistency, "Quality score"),
    ]


def _outbreak_map(seed: int = 119) -> list[ViewerVisual]:
    rng = _rng(seed)
    cities = [("Delhi", 28.6139, 77.2090), ("Mumbai", 19.0760, 72.8777), ("Bengaluru", 12.9716, 77.5946), ("Kolkata", 22.5726, 88.3639), ("Chennai", 13.0827, 80.2707), ("Jaipur", 26.9124, 75.7873)]
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = []
    for i in range(160):
        city, lat, lon = cities[int(rng.integers(0, len(cities)))]
        rows.append({"sample": f"S{i+1:03d}", "city": city, "lat": lat + rng.normal(0, 0.18), "lon": lon + rng.normal(0, 0.18), "date": (start + timedelta(days=int(rng.integers(0, 120)))).date().isoformat(), "cluster": f"C{int(rng.integers(1, 6))}", "host": rng.choice(["Human", "Animal", "Wastewater"]), "amr_score": float(rng.beta(1.4, 3.2))})
    data = pd.DataFrame(rows).sort_values("date")
    data["month"] = data["date"].str[:7]
    fig = px.scatter_geo(data, lat="lat", lon="lon", color="cluster", size="amr_score", hover_name="sample", hover_data=["city", "date", "host"], animation_frame="month", scope="asia", title="Outbreak geography with monthly playback")
    timeline = data.groupby(["month", "cluster"], as_index=False).size().rename(columns={"size": "samples"})
    fig2 = px.line(timeline, x="month", y="samples", color="cluster", markers=True, title="Cluster frequency over time")
    host = data.groupby(["host", "cluster"], as_index=False).size().rename(columns={"size": "samples"})
    fig3 = px.bar(host, x="host", y="samples", color="cluster", barmode="stack", title="Host/source composition by cluster")
    return [
        _visual("Geographic outbreak playback", "Shows sample locations, genomic clusters, host source and AMR signal over time.", "Animated geospatial point map", fig, data, "Latitude/longitude", len(data)),
        _visual("Outbreak cluster timeline", "Tracks cluster expansion, decline and replacement over time.", "Monthly cluster aggregation", fig2, timeline, "Samples/month"),
        _visual("Host and environmental source", "Compares cluster composition across human, animal and wastewater sources.", "Host-by-cluster aggregation", fig3, host, "Samples"),
    ]


def _network_figure(nodes: pd.DataFrame, edges: pd.DataFrame, title: str, color_col: str | None = None,
                    size_col: str | None = None) -> go.Figure:
    by_id = nodes.set_index("id")
    fig = go.Figure()
    for edge in edges.itertuples():
        if edge.source not in by_id.index or edge.target not in by_id.index:
            continue
        a, b = by_id.loc[edge.source], by_id.loc[edge.target]
        fig.add_trace(go.Scatter(x=[a.x, b.x], y=[a.y, b.y], mode="lines", line={"width": max(1, float(getattr(edge, "weight", 1)))}, opacity=0.45, showlegend=False, hoverinfo="skip"))
    marker: dict[str, Any] = {"size": 15, "line": {"width": 1}}
    if color_col and color_col in nodes.columns:
        categories = pd.Categorical(nodes[color_col])
        marker["color"] = categories.codes
        marker["colorscale"] = "Turbo"
        marker["showscale"] = True
    if size_col and size_col in nodes.columns:
        values = pd.to_numeric(nodes[size_col], errors="coerce").fillna(1)
        marker["size"] = 8 + 20 * values / max(float(values.max()), 1)
    fig.add_trace(go.Scatter(x=nodes["x"], y=nodes["y"], mode="markers+text", text=nodes["label"], textposition="top center", marker=marker, customdata=nodes.drop(columns=["x", "y"], errors="ignore").astype(str).to_numpy(), hovertemplate="%{text}<extra></extra>"))
    fig.update_layout(title=title, xaxis={"visible": False}, yaxis={"visible": False}, showlegend=False)
    return fig


def _pangenome_graph(seed: int = 120) -> list[ViewerVisual]:
    rng = _rng(seed)
    n = 34
    angles = np.linspace(0, 2 * np.pi, n, endpoint=False)
    nodes = pd.DataFrame({"id": [f"n{i+1}" for i in range(n)], "label": [f"seg{i+1}" for i in range(n)], "x": 10 * np.cos(angles), "y": 6 * np.sin(angles), "coverage": rng.integers(2, 45, n), "class": rng.choice(["Core", "Accessory", "Rare"], n, p=[0.5, 0.35, 0.15])})
    edges = []
    for i in range(n):
        edges.append({"source": f"n{i+1}", "target": f"n{(i+1)%n+1}", "weight": 1})
    for _ in range(18):
        a = int(rng.integers(0, n)); b = (a + int(rng.integers(2, 8))) % n
        edges.append({"source": f"n{a+1}", "target": f"n{b+1}", "weight": 2})
    edge_table = pd.DataFrame(edges)
    fig = _network_figure(nodes, edge_table, "Pangenome sequence-segment graph", "class", "coverage")
    class_summary = nodes.groupby("class", as_index=False).agg(segments=("id", "size"), mean_coverage=("coverage", "mean"))
    fig2 = px.bar(class_summary, x="class", y="segments", color="mean_coverage", title="Core/accessory segment composition")
    degree = pd.concat([edge_table["source"], edge_table["target"]]).value_counts().rename_axis("id").reset_index(name="degree")
    degree = degree.merge(nodes[["id", "class", "coverage"]], on="id")
    fig3 = px.scatter(degree, x="degree", y="coverage", color="class", size="degree", hover_name="id", title="Graph connectivity and coverage")
    return [
        _visual("Pangenome variation graph", "Displays sequence segments, sample-path alternatives and bubble-like connections.", "GFA-style node-edge rendering", fig, nodes, "Graph coordinates / coverage", len(nodes)),
        _visual("Core and accessory composition", "Summarises graph segments by population frequency class.", "Segment-class aggregation", fig2, class_summary, "Segments"),
        _visual("Connectivity and coverage", "Highlights highly connected graph nodes and unusual coverage.", "Node degree versus coverage", fig3, degree, "Graph degree / coverage"),
    ]


def _single_cell(seed: int = 121) -> list[ViewerVisual]:
    rng = _rng(seed)
    clusters = [("T cells", -4, 1, 1400), ("B cells", 2, 4, 900), ("Myeloid", 4, -2, 1100), ("Stromal", -1, -4, 700)]
    frames = []
    for index, (name, mx, my, count) in enumerate(clusters):
        frames.append(pd.DataFrame({"UMAP1": rng.normal(mx, 1.1, count), "UMAP2": rng.normal(my, 0.9, count), "cluster": name, "condition": rng.choice(["Control", "Treated"], count), "gene_expression": rng.gamma(1.5 + index * 0.25, 1.0, count), "pseudotime": np.clip(rng.normal(index / 3, 0.18, count), 0, 1)}))
    data = pd.concat(frames, ignore_index=True)
    sampled = data.sample(min(len(data), 5000), random_state=seed)
    fig = px.scatter(sampled, x="UMAP1", y="UMAP2", color="cluster", symbol="condition", opacity=0.55, render_mode="webgl", title="Single-cell embedding by cluster and condition")
    fig2 = px.scatter(sampled, x="UMAP1", y="UMAP2", color="gene_expression", opacity=0.6, render_mode="webgl", title="Gene-expression feature overlay")
    fig3 = px.scatter(sampled.sort_values("pseudotime"), x="UMAP1", y="UMAP2", color="pseudotime", opacity=0.6, render_mode="webgl", title="Pseudotime trajectory overlay")
    return [
        _visual("Single-cell embedding explorer", "Supports lasso/box selection and cluster/condition inspection.", "UMAP-like two-dimensional embedding", fig, sampled, "Embedding coordinates", len(data), "Stratified display subset" if len(sampled) < len(data) else None),
        _visual("Gene-expression overlay", "Shows spatial expression patterns across the embedding.", "Per-cell expression colour overlay", fig2, sampled, "Normalized expression", len(data), "Display subset"),
        _visual("Pseudotime overlay", "Reveals continuous state progression across clusters.", "Per-cell pseudotime colour overlay", fig3, sampled, "Pseudotime 0–1", len(data), "Display subset"),
    ]


def _sequence_track(seed: int = 122, length: int = 950) -> list[ViewerVisual]:
    features = pd.DataFrame([
        {"feature": "Signal peptide", "start": 1, "end": 24, "track": "Processing", "score": 0.92},
        {"feature": "Domain A", "start": 75, "end": 260, "track": "Domains", "score": 0.88},
        {"feature": "Active site", "start": 184, "end": 184, "track": "Sites", "score": 0.99},
        {"feature": "Disordered region", "start": 295, "end": 365, "track": "Disorder", "score": 0.76},
        {"feature": "Domain B", "start": 390, "end": 640, "track": "Domains", "score": 0.91},
        {"feature": "Transmembrane", "start": 710, "end": 735, "track": "Topology", "score": 0.94},
        {"feature": "Mutation V812M", "start": 812, "end": 812, "track": "Variants", "score": 0.67},
        {"feature": "PTM S845", "start": 845, "end": 845, "track": "PTMs", "score": 0.83},
    ])
    track_order = {name: idx for idx, name in enumerate(features["track"].unique())}
    fig = go.Figure()
    for row in features.itertuples():
        y = track_order[row.track]
        end = row.end if row.end > row.start else row.start + max(2, length * 0.006)
        fig.add_trace(go.Scatter(x=[row.start, end], y=[y, y], mode="lines+markers", line={"width": 14}, marker={"size": 6}, name=row.track, text=[row.feature, row.feature], hovertemplate=f"{row.feature}<br>{row.start}–{row.end}<br>Score {row.score:.2f}<extra></extra>", showlegend=False))
    fig.update_layout(title="Sequence feature track", xaxis={"title": "Residue/base position", "range": [0, length]}, yaxis={"tickmode": "array", "tickvals": list(track_order.values()), "ticktext": list(track_order.keys())})
    rng = _rng(seed)
    positions = np.arange(1, length + 1)
    conservation = pd.DataFrame({"position": positions, "conservation": np.clip(0.55 + 0.25 * np.sin(positions / 43) + rng.normal(0, 0.08, length), 0, 1)})
    fig2 = px.line(conservation, x="position", y="conservation", title="Sequence conservation/confidence profile")
    category = features.groupby("track", as_index=False).size().rename(columns={"size": "features"})
    fig3 = px.bar(category, x="track", y="features", title="Feature composition")
    return [
        _visual("Sequence feature track", "Provides residue/base-level domains, topology, PTMs, variants and active-site context.", "Coordinate-aligned feature intervals", fig, features, "Sequence position", len(features)),
        _visual("Conservation/confidence profile", "Highlights conserved or uncertain sequence regions for design and interpretation.", "Sliding simulated conservation score", fig2, conservation, "Score 0–1", len(conservation)),
        _visual("Feature composition", "Summarises the number of annotated features by biological category.", "Feature category count", fig3, category, "Features"),
    ]


def _multiomics(seed: int = 123) -> list[ViewerVisual]:
    rng = _rng(seed)
    genes = [f"G{i}" for i in range(1, 9)]
    proteins = [f"P{i}" for i in range(1, 7)]
    metabolites = [f"M{i}" for i in range(1, 6)]
    pathways = ["Immune", "Energy", "Cell cycle", "Stress"]
    labels = genes + proteins + metabolites + pathways
    index = {label: i for i, label in enumerate(labels)}
    links = []
    for gene in genes:
        protein = rng.choice(proteins)
        links.append({"source": gene, "target": protein, "weight": int(rng.integers(2, 12)), "layer": "Transcript→Protein"})
    for protein in proteins:
        metabolite = rng.choice(metabolites)
        links.append({"source": protein, "target": metabolite, "weight": int(rng.integers(2, 12)), "layer": "Protein→Metabolite"})
    for metabolite in metabolites:
        pathway = rng.choice(pathways)
        links.append({"source": metabolite, "target": pathway, "weight": int(rng.integers(2, 12)), "layer": "Metabolite→Pathway"})
    link_df = pd.DataFrame(links)
    fig = go.Figure(go.Sankey(node={"label": labels, "pad": 18, "thickness": 16}, link={"source": [index[x] for x in link_df["source"]], "target": [index[x] for x in link_df["target"]], "value": link_df["weight"]}))
    fig.update_layout(title="Gene → protein → metabolite → pathway flow")
    overlap = pd.DataFrame({"feature": [f"F{i}" for i in range(1, 31)], "transcriptomics": rng.integers(0, 2, 30), "proteomics": rng.integers(0, 2, 30), "metabolomics": rng.integers(0, 2, 30)})
    overlap["membership"] = overlap[["transcriptomics", "proteomics", "metabolomics"]].astype(str).agg("".join, axis=1).map({"100": "Transcript only", "010": "Protein only", "001": "Metabolite only", "110": "Transcript+Protein", "101": "Transcript+Metabolite", "011": "Protein+Metabolite", "111": "All three", "000": "None"})
    overlap_summary = overlap.groupby("membership", as_index=False).size().rename(columns={"size": "features"}).sort_values("features", ascending=False)
    fig2 = px.bar(overlap_summary, x="membership", y="features", title="Cross-omics feature overlap")
    samples = pd.DataFrame(rng.normal(size=(20, 12)), columns=[f"feature_{i+1}" for i in range(12)])
    corr = samples.corr()
    fig3 = px.imshow(corr, zmin=-1, zmax=1, color_continuous_scale="RdBu_r", title="Cross-omics correlation matrix")
    corr_data = corr.reset_index().melt(id_vars="index", var_name="feature_b", value_name="correlation").rename(columns={"index": "feature_a"})
    return [
        _visual("Multi-omics relationship Sankey", "Traces feature evidence across molecular layers into pathways.", "Weighted alluvial/Sankey flow", fig, link_df, "Evidence weight", len(link_df)),
        _visual("Cross-omics overlap", "Shows unique and shared feature support across omics layers.", "UpSet-style membership aggregation", fig2, overlap_summary, "Features"),
        _visual("Cross-omics concordance", "Highlights positively and negatively correlated molecular features.", "Pearson correlation matrix", fig3, corr_data, "Correlation −1 to 1"),
    ]


def _bioprocess_live(seed: int = 124) -> list[ViewerVisual]:
    rng = _rng(seed)
    time = np.linspace(0, 72, 289)
    biomass = 0.25 * np.exp(0.075 * np.minimum(time, 45)) / (1 + np.exp((time - 45) / 4)) + rng.normal(0, 0.08, len(time))
    biomass = np.clip(biomass, 0, None)
    substrate = np.clip(24 - 0.42 * time + rng.normal(0, 0.5, len(time)), 0, None)
    product = np.clip(0.05 * time**1.7 / (1 + np.exp((time - 60) / 6)) + rng.normal(0, 0.25, len(time)), 0, None)
    pH = 7.0 - 0.35 * np.exp(-((time - 24) / 12) ** 2) + rng.normal(0, 0.025, len(time))
    do = np.clip(80 - 55 * (biomass / max(float(biomass.max()), 1)) + rng.normal(0, 3, len(time)), 5, 100)
    data = pd.DataFrame({"time_h": time, "biomass": biomass, "substrate": substrate, "product": product, "pH": pH, "DO_percent": do})
    long = data.melt(id_vars="time_h", value_vars=["biomass", "substrate", "product"], var_name="analyte", value_name="value")
    fig = px.line(long, x="time_h", y="value", color="analyte", title="Live process trajectories")
    controls = data.melt(id_vars="time_h", value_vars=["pH", "DO_percent"], var_name="sensor", value_name="value")
    fig2 = px.line(controls, x="time_h", y="value", color="sensor", facet_row="sensor", title="Critical process parameters and control bands")
    fig2.add_hline(y=6.7, line_dash="dash", row=1, col=1)
    fig2.add_hline(y=7.2, line_dash="dash", row=1, col=1)
    data["specific_productivity"] = data["product"].diff().clip(lower=0) / data["time_h"].diff().replace(0, np.nan) / data["biomass"].clip(lower=0.05)
    fig3 = px.line(data, x="time_h", y="specific_productivity", title="Soft-sensor productivity estimate")
    return [
        _visual("Live bioprocess dashboard", "Displays biomass, substrate and product trajectories with zoomable time navigation.", "Time-series process monitoring", fig, long, "Hours / process units", len(data)),
        _visual("Critical process controls", "Tracks pH and dissolved oxygen against operating limits.", "Sensor trend and control-band review", fig2, controls, "pH / % saturation"),
        _visual("Productivity soft sensor", "Estimates productivity changes and potential endpoint timing.", "Finite-difference product rate normalized by biomass", fig3, data, "Product/(biomass·hour)"),
    ]


def _workflow_dag(seed: int = 125) -> list[ViewerVisual]:
    nodes = pd.DataFrame([
        {"id": "upload", "label": "Upload", "x": 0, "y": 1, "status": "Completed", "runtime_s": 12},
        {"id": "qc", "label": "QC", "x": 1, "y": 1, "status": "Completed", "runtime_s": 55},
        {"id": "normalize", "label": "Normalize", "x": 2, "y": 1.5, "status": "Completed", "runtime_s": 93},
        {"id": "features", "label": "Features", "x": 2, "y": 0.5, "status": "Completed", "runtime_s": 188},
        {"id": "model", "label": "Model", "x": 3, "y": 1, "status": "Running", "runtime_s": 310},
        {"id": "validate", "label": "Validate", "x": 4, "y": 1, "status": "Queued", "runtime_s": 0},
        {"id": "report", "label": "Report", "x": 5, "y": 1, "status": "Blocked", "runtime_s": 0},
    ])
    edges = pd.DataFrame([
        {"source": "upload", "target": "qc", "weight": 1}, {"source": "qc", "target": "normalize", "weight": 1},
        {"source": "qc", "target": "features", "weight": 1}, {"source": "normalize", "target": "model", "weight": 1},
        {"source": "features", "target": "model", "weight": 2}, {"source": "model", "target": "validate", "weight": 1},
        {"source": "validate", "target": "report", "weight": 1},
    ])
    fig = _network_figure(nodes, edges, "Workflow DAG and live execution state", "status", "runtime_s")
    fig2 = px.bar(nodes.sort_values("runtime_s", ascending=True), x="runtime_s", y="label", color="status", orientation="h", title="Node runtime and bottlenecks")
    status = nodes.groupby("status", as_index=False).size().rename(columns={"size": "nodes"})
    fig3 = px.pie(status, names="status", values="nodes", hole=0.45, title="Workflow state composition")
    return [
        _visual("Workflow DAG monitor", "Shows dependencies, current node states and critical execution path.", "Directed acyclic graph rendering", fig, nodes, "Workflow coordinates / seconds", len(nodes)),
        _visual("Node runtime bottlenecks", "Ranks completed/running steps by execution time.", "Per-node runtime comparison", fig2, nodes, "Seconds"),
        _visual("Execution state summary", "Summarises completed, running, queued and blocked nodes.", "Workflow state aggregation", fig3, status, "Nodes"),
    ]


def _freezer_map(seed: int = 126) -> list[ViewerVisual]:
    rng = _rng(seed)
    rows = [chr(65 + i) for i in range(9)]
    records = []
    for r, row in enumerate(rows):
        for col in range(1, 10):
            occupied = bool(rng.random() < 0.72)
            records.append({"position": f"{row}{col}", "row": row, "column": col, "occupied": occupied, "sample_id": f"SMP-{rng.integers(1000, 9999)}" if occupied else "", "freeze_thaw": int(rng.integers(0, 8)) if occupied else 0, "days_to_expiry": int(rng.integers(-30, 900)) if occupied else np.nan, "risk": rng.choice(["Low", "Medium", "High"], p=[0.68, 0.24, 0.08]) if occupied else "Empty"})
    data = pd.DataFrame(records)
    risk_code = data["risk"].map({"Empty": 0, "Low": 1, "Medium": 2, "High": 3})
    pivot = pd.DataFrame({"row": data["row"], "column": data["column"], "risk_code": risk_code}).pivot(index="row", columns="column", values="risk_code")
    hover = data.assign(hover=data["position"] + " · " + data["sample_id"].replace("", "Empty") + " · " + data["risk"]).pivot(index="row", columns="column", values="hover")
    fig = go.Figure(go.Heatmap(z=pivot.values, x=pivot.columns, y=pivot.index, text=hover.values, hovertemplate="%{text}<extra></extra>", colorbar={"title": "Risk", "tickvals": [0, 1, 2, 3], "ticktext": ["Empty", "Low", "Medium", "High"]}))
    fig.update_layout(title="Freezer box occupancy and risk map", xaxis_title="Column", yaxis_title="Row")
    occupied = data[data["occupied"]].copy()
    fig2 = px.histogram(occupied, x="freeze_thaw", color="risk", barmode="group", title="Freeze–thaw exposure distribution")
    expiry = occupied.groupby("risk", as_index=False).agg(samples=("sample_id", "size"), median_days=("days_to_expiry", "median"))
    fig3 = px.bar(expiry, x="risk", y="samples", text="median_days", title="Storage risk and expiry profile")
    return [
        _visual("Freezer and sample map", "Shows occupied positions, sample identifiers and storage-risk status.", "Rack/box coordinate heatmap", fig, data, "Storage positions", len(data)),
        _visual("Freeze–thaw exposure", "Highlights samples with repeated freeze–thaw cycles.", "Sample exposure distribution", fig2, occupied, "Cycles"),
        _visual("Expiry and risk profile", "Summarises sample count and median time to expiry by risk state.", "Risk-level aggregation", fig3, expiry, "Samples / days"),
    ]


def _static_reporting(seed: int = 127) -> list[ViewerVisual]:
    formats = pd.DataFrame([
        {"format": "SVG", "availability": 1.0, "offline": True, "fidelity": 0.98},
        {"format": "Interactive HTML", "availability": 1.0, "offline": True, "fidelity": 1.0},
        {"format": "JSON", "availability": 1.0, "offline": True, "fidelity": 1.0},
        {"format": "CSV", "availability": 1.0, "offline": True, "fidelity": 0.85},
        {"format": "PDF", "availability": 0.85, "offline": True, "fidelity": 0.90},
        {"format": "DOCX", "availability": 0.90, "offline": True, "fidelity": 0.88},
        {"format": "PPTX", "availability": 0.90, "offline": True, "fidelity": 0.88},
    ])
    fig = px.bar(formats, x="format", y="fidelity", color="availability", range_y=[0, 1.05], title="Offline visual export capability")
    stages = pd.DataFrame({"stage": ["Figure JSON", "Accessible SVG", "Data table", "Provenance", "Document assembly", "Integrity manifest"], "status": [1, 1, 1, 1, 1, 1]})
    fig2 = px.bar(stages, x="stage", y="status", range_y=[0, 1.1], title="Deterministic report-rendering pipeline")
    bundle = pd.DataFrame({"artifact": ["report.pdf", "report.docx", "slides.pptx", "figure.svg", "figure.html", "data.csv", "manifest.json"], "required": True})
    fig3 = px.pie(bundle, names="artifact", values=np.ones(len(bundle)), hole=0.45, title="Complete visual report bundle")
    return [
        _visual("Offline export readiness", "Shows supported visual/report outputs and expected fidelity.", "Renderer capability matrix", fig, formats, "Score 0–1", len(formats)),
        _visual("Rendering pipeline", "Confirms that figures, data and provenance are assembled deterministically.", "Static report pipeline state", fig2, stages, "Pass state"),
        _visual("Report bundle contents", "Summarises the reproducibility artifacts included in a complete visual export.", "Bundle composition", fig3, bundle, "Artifacts"),
    ]


def _visual_regression(seed: int = 128) -> list[ViewerVisual]:
    rng = _rng(seed)
    pages = ["Home", "Genome browser", "Molecular viewer", "Pathology", "Microscopy", "Flow gating", "Mass spectrum", "Phylogeny", "Plate map", "Pedigree", "Outbreak", "Pangenome", "Single-cell", "Visual workspace"]
    states = ["Default", "Empty", "Error", "Result", "High contrast"]
    records = []
    for page in pages:
        for state in states:
            status = rng.choice(["Pass", "Pass", "Pass", "Review"], p=[0.72, 0.12, 0.08, 0.08])
            records.append({"page": page, "state": state, "status": status, "pixel_delta_percent": float(rng.beta(0.6, 18) * 8), "semantic_delta": int(rng.integers(0, 4))})
    data = pd.DataFrame(records)
    pivot = data.pivot(index="page", columns="state", values="pixel_delta_percent")
    fig = px.imshow(pivot, aspect="auto", color_continuous_scale="YlOrRd", title="Visual-regression change heatmap", labels={"color": "Pixel delta %"})
    status = data.groupby("status", as_index=False).size().rename(columns={"size": "scenarios"})
    fig2 = px.pie(status, names="status", values="scenarios", hole=0.45, title="Baseline review status")
    page_summary = data.groupby("page", as_index=False).agg(max_pixel_delta=("pixel_delta_percent", "max"), semantic_changes=("semantic_delta", "sum"))
    fig3 = px.scatter(page_summary, x="max_pixel_delta", y="semantic_changes", hover_name="page", size="max_pixel_delta", title="Semantic versus pixel change")
    return [
        _visual("Visual-regression heatmap", "Shows page/theme/state combinations with the largest screenshot changes.", "Baseline pixel-difference matrix", fig, data, "% pixels changed", len(data)),
        _visual("Baseline review status", "Summarises scenarios that pass automatically or need human review.", "Scenario status aggregation", fig2, status, "Scenarios"),
        _visual("Semantic and pixel change", "Separates structural UI changes from purely visual differences.", "Semantic fingerprint versus pixel delta", fig3, page_summary, "Change metrics"),
    ]


_VIEWER_BUILDERS: dict[str, Callable[..., list[ViewerVisual]]] = {
    "genome_browser": _genome_browser,
    "molecular_3d": _molecular_3d,
    "pathology": _pathology,
    "microscopy": _microscopy,
    "flow_gating": _flow_gating,
    "mass_spectrometry": _mass_spectrometry,
    "phylogenetic_tree": _phylogenetic_tree,
    "plate_map": _plate_map,
    "pedigree": _pedigree,
    "outbreak_map": _outbreak_map,
    "pangenome_graph": _pangenome_graph,
    "single_cell": _single_cell,
    "sequence_track": _sequence_track,
    "multiomics": _multiomics,
    "bioprocess_live": _bioprocess_live,
    "workflow_dag": _workflow_dag,
    "freezer_map": _freezer_map,
    "static_reporting": _static_reporting,
    "visual_regression": _visual_regression,
}


@st.cache_data(show_spinner=False, max_entries=32)
def _cached_demo_viewer(viewer_key: str) -> list[ViewerVisual]:
    return _VIEWER_BUILDERS[viewer_key]()


def build_advanced_viewer_visuals(viewer_key: str, **kwargs: Any) -> list[ViewerVisual]:
    if viewer_key not in _VIEWER_BUILDERS:
        raise KeyError(f"Unknown advanced viewer: {viewer_key}")
    native_result = kwargs.pop("_native_result", None)
    if native_result is not None:
        from biointel.native.viewers import build_native_viewer_visuals

        visuals = build_native_viewer_visuals(viewer_key, native_result)
    else:
        # Demonstration/default data are deterministic and shared across reruns. Uploaded images,
        # structures and parameterized views bypass this cache so changes render immediately.
        visuals = _VIEWER_BUILDERS[viewer_key](**kwargs) if kwargs else _cached_demo_viewer(viewer_key)
    if not visuals:
        raise RuntimeError(f"Viewer {viewer_key} produced no visuals")
    return visuals


def _read_uploaded_image(upload: Any) -> np.ndarray | None:
    if upload is None:
        return None
    try:
        with Image.open(io.BytesIO(upload.getvalue())) as source:
            source.thumbnail((1200, 1200))
            return np.asarray(source.convert("RGB"), dtype=float) / 255.0
    except Exception:
        return None


def _viewer_controls(viewer_key: str, prefix: str) -> dict[str, Any]:
    from biointel.native.formats import INTERACTIVE_NATIVE_BYTES, parse_native_source, supported_extensions_for_viewer
    from biointel.ui.workbench import stage_large_upload

    kwargs: dict[str, Any] = {}
    source_mode = st.radio(
        "Viewer data source",
        ["Native scientific file", "Deterministic demonstration"],
        horizontal=True,
        key=f"{prefix}_source_mode",
    )
    if source_mode.startswith("Native"):
        extensions = supported_extensions_for_viewer(viewer_key)
        if extensions:
            st.caption("Native reader formats: " + " · ".join(f".{extension}" for extension in extensions[:20]) + (f" · +{len(extensions)-20} more" if len(extensions) > 20 else ""))
        upload = st.file_uploader(
            "Upload native scientific evidence",
            type=extensions or None,
            key=f"{prefix}_native_upload",
            help="Maximum 1 GB per file. Files above 100 MB are staged and inspected by the background worker.",
        )
        if upload is None:
            st.info("Upload a native scientific file, or switch to the deterministic demonstration to inspect the viewer immediately.")
            kwargs["_awaiting_native_upload"] = True
            return kwargs
        size = int(getattr(upload, "size", 0) or 0)
        upload_identity = str(getattr(upload, "file_id", "") or "")
        if not upload_identity:
            try:
                upload_identity = hashlib.sha256(upload.getbuffer()).hexdigest()
            except Exception:
                upload_identity = f"{getattr(upload, 'name', '')}:{size}"
        if size > INTERACTIVE_NATIVE_BYTES:
            manifest_key = f"{prefix}_native_large_manifest"
            signature_key = f"{prefix}_native_large_signature"
            large_signature = f"{upload_identity}:{getattr(upload, 'name', '')}:{size}"
            if st.session_state.get(signature_key) != large_signature:
                with st.spinner("Staging large native file and creating a background-safe inspection job…"):
                    st.session_state[manifest_key] = stage_large_upload(upload, module_key=f"native_{viewer_key}", project_root=Path(__file__).resolve().parents[3])
                    st.session_state[signature_key] = large_signature
            manifest = st.session_state[manifest_key]
            st.success(f"Large native file staged safely. Background job: {manifest['job_id']}")
            render_operational_canvas(
                "Large-file staging status",
                {key: value for key, value in manifest.items() if key != "staged_path"},
                workflow=("Upload", "Protected staging", "Background inspection", "Viewer handoff"),
            )
            kwargs["_awaiting_native_upload"] = True
            return kwargs
        max_records = st.select_slider(
            "Interactive native record limit",
            options=[5_000, 10_000, 25_000, 50_000, 100_000],
            value=50_000,
            key=f"{prefix}_native_records",
            help="The parser is streaming where possible; this limit bounds in-memory preview records.",
        )
        try:
            result_key = f"{prefix}_native_parse_result"
            signature_key = f"{prefix}_native_parse_signature"
            parse_signature = f"{upload_identity}:{getattr(upload, 'name', '')}:{size}:{viewer_key}:{int(max_records)}"
            if st.session_state.get(signature_key) != parse_signature:
                with st.spinner("Parsing native scientific evidence…"):
                    st.session_state[result_key] = parse_native_source(upload, preferred_viewer=viewer_key, max_records=int(max_records))
                    st.session_state[signature_key] = parse_signature
            native_result = st.session_state[result_key]
            kwargs["_native_result"] = native_result
            summary = native_result.summary()
            summary.pop("preview_array", None)
            st.success(f"Native {native_result.format_key.upper()} evidence decoded · {native_result.record_count:,} preview records")
            with st.expander("Native file provenance and parser status", expanded=False):
                render_operational_canvas(
                    "Native parser status",
                    summary,
                    workflow=("Source", "Format detection", "Bounded preview", "Scientific visualization"),
                )
                if native_result.warnings:
                    for warning in native_result.warnings:
                        st.warning(warning)
        except Exception as exc:
            st.error(f"Native parser could not decode the uploaded file safely: {type(exc).__name__}: {exc}")
            kwargs["_awaiting_native_upload"] = True
        return kwargs

    if viewer_key == "genome_browser":
        kwargs["seed"] = 110
    elif viewer_key == "molecular_3d":
        upload = st.file_uploader("Optional PDB structure", type=["pdb"], key=f"{prefix}_pdb")
        if upload is not None and upload.size <= 50 * 1024 * 1024:
            kwargs["pdb_text"] = upload.getvalue().decode("utf-8", errors="replace")
    elif viewer_key in {"pathology", "microscopy"}:
        upload = st.file_uploader("Optional image", type=["png", "jpg", "jpeg", "tif", "tiff"], key=f"{prefix}_image")
        image = _read_uploaded_image(upload)
        if image is not None:
            kwargs["image"] = image
        if viewer_key == "pathology":
            kwargs["overlay_opacity"] = st.slider("Overlay opacity", 0.0, 1.0, 0.55, 0.05, key=f"{prefix}_opacity")
        else:
            col1, col2 = st.columns(2)
            kwargs["threshold"] = col1.slider("Segmentation threshold", 0.05, 0.95, 0.58, 0.01, key=f"{prefix}_threshold")
            kwargs["min_size"] = col2.slider("Minimum object size", 3, 300, 20, 1, key=f"{prefix}_min_size")
    elif viewer_key == "flow_gating":
        col1, col2 = st.columns(2)
        kwargs["x_gate"] = col1.number_input("FSC gate", min_value=0.0, value=55_000.0, step=1_000.0, key=f"{prefix}_x_gate")
        kwargs["y_gate"] = col2.number_input("SSC gate", min_value=0.0, value=45_000.0, step=1_000.0, key=f"{prefix}_y_gate")
    elif viewer_key == "phylogenetic_tree":
        newick = st.text_area("Optional Newick tree", value="", placeholder="((A:0.1,B:0.2):0.1,C:0.3);", key=f"{prefix}_newick")
        if newick.strip():
            kwargs["newick"] = newick.strip()
    elif viewer_key == "plate_map":
        plate = st.selectbox("Plate format", ["96 wells", "384 wells"], key=f"{prefix}_plate")
        kwargs["rows"], kwargs["columns"] = ((8, 12) if plate == "96 wells" else (16, 24))
    return kwargs


def render_advanced_scientific_viewer(
    viewer_key: str,
    *,
    key_prefix: str | None = None,
    heading: bool = True,
    compact: bool = False,
) -> None:
    if viewer_key not in ADVANCED_VIEWER_CATALOG:
        st.error(f"Unknown advanced viewer: {viewer_key}")
        return
    spec = ADVANCED_VIEWER_CATALOG[viewer_key]
    prefix = key_prefix or f"advanced_{viewer_key}"
    if heading:
        st.markdown(f"### {spec.icon} {spec.title}")
        st.caption(spec.description)
        st.markdown("**Connected modules:** " + " · ".join(spec.modules))
        st.markdown("**Accepted evidence formats:** " + " · ".join(spec.input_types))
    from biointel.statistics.rigor import infer_visual_statistics
    from biointel.ui.viewer_sync import apply_selection_to_visual, publish_selection, render_sync_status

    sync_selection = render_sync_status(viewer_key, key_prefix=prefix)
    kwargs = _viewer_controls(viewer_key, prefix)
    if kwargs.pop("_awaiting_native_upload", False):
        return
    native_mode = "_native_result" in kwargs
    try:
        visuals = build_advanced_viewer_visuals(viewer_key, **kwargs)
    except Exception as exc:
        st.error(f"The viewer could not prepare its visual data safely: {type(exc).__name__}: {exc}")
        return
    labels = [visual.title for visual in visuals]
    mode = st.radio("Viewer layout", ["Single viewer", "Compare two views"], horizontal=True, key=f"{prefix}_layout")
    if mode == "Single viewer":
        selected = st.selectbox("View", labels, key=f"{prefix}_choice")
        chosen = visuals[labels.index(selected)]
        display_figure, display_data, sync_note = apply_selection_to_visual(chosen.figure, chosen.data, sync_selection)
        selected_data = scientific_chart_card(
            display_figure,
            title=chosen.title,
            interpretation=chosen.interpretation + (f" Linked focus: {sync_note}." if sync_note else ""),
            data=display_data,
            method=chosen.method,
            units=chosen.units,
            key=f"{prefix}_{labels.index(selected)}",
            module_key=viewer_key,
            evidence_status="real_imported" if native_mode else spec.evidence_status,
            statistics=infer_visual_statistics(display_data, source_count=chosen.source_count),
            source_record_count=chosen.source_count,
            aggregation_note=chosen.aggregation_note,
            configuration={"viewer": viewer_key, "view": selected, "native_mode": native_mode},
        )
        if not selected_data.empty:
            publish_selection(source_viewer=viewer_key, selected=selected_data, entity_type="native_record" if native_mode else "demonstration_record")
    else:
        left, right = st.columns(2, gap="large")
        left_label = left.selectbox("Left view", labels, key=f"{prefix}_left")
        right_options = [label for label in labels if label != left_label] or labels
        right_label = right.selectbox("Right view", right_options, key=f"{prefix}_right")
        for container, label, side in ((left, left_label, "left"), (right, right_label, "right")):
            chosen = visuals[labels.index(label)]
            display_figure, display_data, sync_note = apply_selection_to_visual(chosen.figure, chosen.data, sync_selection)
            with container:
                selected_data = scientific_chart_card(
                    display_figure, title=chosen.title,
                    interpretation=chosen.interpretation + (f" Linked focus: {sync_note}." if sync_note else ""),
                    data=display_data, method=chosen.method, units=chosen.units,
                    key=f"{prefix}_{side}_{labels.index(label)}", module_key=viewer_key,
                    evidence_status="real_imported" if native_mode else spec.evidence_status,
                    statistics=infer_visual_statistics(display_data, source_count=chosen.source_count),
                    source_record_count=chosen.source_count,
                    aggregation_note=chosen.aggregation_note,
                    configuration={"viewer": viewer_key, "view": label, "side": side, "native_mode": native_mode},
                )
                if not selected_data.empty:
                    publish_selection(source_viewer=viewer_key, selected=selected_data, entity_type="native_record" if native_mode else "demonstration_record")
    if not compact:
        with st.expander("Viewer capabilities and scientific boundary", expanded=False):
            st.write(spec.description)
            st.dataframe(pd.DataFrame({"Connected module": list(spec.modules)}), hide_index=True, width="stretch")
            st.info("Built-in viewers support local exploration and evidence review. Specialist interpretation, validated clinical use and vendor-certified raw-file handling still require the relevant external tools, databases and operating procedures.")


def render_embedded_viewer(viewer_key: str, *, key_prefix: str | None = None) -> None:
    spec = ADVANCED_VIEWER_CATALOG[viewer_key]
    prefix = key_prefix or f"embedded_{viewer_key}"
    st.divider()
    st.markdown(f"#### {spec.icon} Advanced viewer")
    st.caption(spec.description)
    open_viewer = st.toggle("Open advanced interactive viewer", value=False, key=f"{prefix}_open")
    if open_viewer:
        render_advanced_scientific_viewer(viewer_key, key_prefix=prefix, heading=False, compact=True)


def render_advanced_viewer_hub() -> None:
    st.markdown("### Advanced scientific viewer catalogue")
    st.caption("Nineteen optimized viewers cover raw scientific evidence, spatial/image/structure exploration, laboratory layouts and platform visual quality.")
    query = st.text_input("Search viewers", placeholder="genome, structure, microscopy, plate, pedigree…", key="advanced_viewer_search")
    options = list(ADVANCED_VIEWER_CATALOG.values())
    if query.strip():
        token = query.strip().lower()
        options = [spec for spec in options if token in (spec.title + " " + spec.description + " " + " ".join(spec.modules)).lower()]
    table = pd.DataFrame([{"Viewer": spec.title, "Purpose": spec.description, "Modules": ", ".join(spec.modules), "Inputs": ", ".join(spec.input_types)} for spec in options])
    st.dataframe(table, hide_index=True, width="stretch", height=min(520, 80 + 35 * max(len(table), 1)))
    if not options:
        st.info("No viewers match the current search.")
        return
    selected = st.selectbox("Open viewer", [spec.key for spec in options], format_func=lambda key: ADVANCED_VIEWER_CATALOG[key].title, key="advanced_viewer_hub_choice")
    render_advanced_scientific_viewer(selected, key_prefix=f"hub_{selected}")


__all__ = [
    "ADVANCED_VIEWER_CATALOG",
    "AdvancedViewerSpec",
    "ViewerVisual",
    "build_advanced_viewer_visuals",
    "render_advanced_scientific_viewer",
    "render_embedded_viewer",
    "render_advanced_viewer_hub",
]
