from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from biointel.native.formats import NativeParseResult


def _visual(title: str, interpretation: str, method: str, figure: go.Figure, data: pd.DataFrame, units: str | None = None, source_count: int | None = None, aggregation_note: str | None = None):
    from biointel.ui.advanced_scientific_viewers import ViewerVisual

    figure.update_layout(margin=dict(l=45, r=20, t=70, b=45), height=560, legend_title_text="")
    return ViewerVisual(title, interpretation, method, figure, data.reset_index(drop=True), units, source_count, aggregation_note)


def _numeric_columns(frame: pd.DataFrame) -> list[str]:
    return [str(column) for column in frame.select_dtypes(include=[np.number]).columns]


def _first_column(frame: pd.DataFrame, candidates: list[str]) -> str | None:
    lower = {str(column).lower(): str(column) for column in frame.columns}
    for candidate in candidates:
        if candidate.lower() in lower:
            return lower[candidate.lower()]
    return None


def _genome_visuals(result: NativeParseResult):
    data = result.primary.copy()
    visuals = []
    chrom_col = _first_column(data, ["chrom", "chromosome", "reference", "seqid"])
    pos_col = _first_column(data, ["position", "pos", "start"])
    end_col = _first_column(data, ["end"])
    if chrom_col and pos_col and not data.empty:
        subset = data.head(50_000).copy()
        subset[pos_col] = pd.to_numeric(subset[pos_col], errors="coerce")
        subset = subset.dropna(subset=[pos_col])
        y_col = _first_column(subset, ["quality", "score", "depth", "mapping_quality", "allele_frequency"])
        if y_col is None:
            subset["record_index"] = np.arange(len(subset))
            y_col = "record_index"
        color = _first_column(subset, ["variant_type", "filter", "feature_type", "impact", "reference"])
        fig = px.scatter(subset, x=pos_col, y=y_col, color=color, facet_row=chrom_col if subset[chrom_col].nunique() <= 8 else None, hover_data=[column for column in subset.columns[:12]], title="Native genomic evidence track")
        visuals.append(_visual("Native genomic evidence", "Displays positions from the uploaded genomic file without converting them to a generic demonstration table.", f"Native {result.format_key.upper()} parser", fig, subset, source_count=result.total_records, aggregation_note="bounded to the first 50,000 plotted records" if len(data) > 50_000 else None))
        counts = subset.groupby(chrom_col, as_index=False).size().rename(columns={"size": "records"}).sort_values("records", ascending=False)
        fig2 = px.bar(counts.head(50), x=chrom_col, y="records", title="Records by chromosome/reference")
        visuals.append(_visual("Chromosome/reference coverage", "Summarises native records across reference sequences.", "Record-count aggregation", fig2, counts, "Records"))
        if end_col:
            subset[end_col] = pd.to_numeric(subset[end_col], errors="coerce")
            subset["feature_length"] = subset[end_col] - subset[pos_col]
            fig3 = px.histogram(subset.dropna(subset=["feature_length"]), x="feature_length", nbins=60, title="Genomic feature-length distribution")
            visuals.append(_visual("Feature-length distribution", "Reveals interval-size structure and extreme genomic regions.", "End minus start", fig3, subset[[chrom_col, pos_col, end_col, "feature_length"]], "Bases"))
    if not visuals:
        fig = go.Figure().add_annotation(text="The native file was verified but no directly plottable genomic coordinates were decoded.", x=0.5, y=0.5, showarrow=False)
        visuals.append(_visual("Native genomic file status", "Use the configured samtools/bcftools adapter for indexed binary alignment or variant processing.", "Native format inspection", fig, data, source_count=result.total_records))
    return visuals


def _molecular_visuals(result: NativeParseResult):
    atoms = result.primary.copy()
    if atoms.empty or not {"x", "y", "z"}.issubset(atoms.columns):
        raise ValueError("Structure parser returned no atom coordinates")
    plot_atoms = atoms.head(100_000)
    color = "chain" if "chain" in plot_atoms.columns else "element"
    size = np.where(plot_atoms.get("element", pd.Series(index=plot_atoms.index, dtype=str)).astype(str).eq("H"), 2.0, 5.0)
    fig = px.scatter_3d(plot_atoms, x="x", y="y", z="z", color=color, hover_data=[column for column in ["atom", "residue_name", "residue_number", "chain", "element", "bfactor"] if column in plot_atoms.columns], title="Native atom-coordinate structure")
    fig.update_traces(marker={"size": size, "opacity": 0.85})
    visuals = [_visual("Native 3D molecular structure", "Renders atom coordinates directly from PDB/mmCIF evidence.", f"Biopython {result.format_key.upper()} structure parser", fig, plot_atoms, "Å", result.total_records, "first 100,000 atoms" if len(atoms) > 100_000 else None)]
    if "bfactor" in atoms.columns:
        residue = atoms.groupby([column for column in ["chain", "residue_number", "residue_name"] if column in atoms.columns], as_index=False).agg(mean_bfactor=("bfactor", "mean"), atoms=("atom", "size"))
        fig2 = px.line(residue, x="residue_number", y="mean_bfactor", color="chain" if "chain" in residue.columns else None, title="Residue confidence/flexibility profile")
        visuals.append(_visual("Residue B-factor profile", "Highlights flexible or low-confidence structural regions.", "Mean atom B-factor per residue", fig2, residue, "Å²"))
    element = atoms.groupby("element", as_index=False).size().rename(columns={"size": "atoms"}) if "element" in atoms.columns else pd.DataFrame()
    if not element.empty:
        fig3 = px.bar(element.sort_values("atoms", ascending=False), x="element", y="atoms", title="Atomic composition")
        visuals.append(_visual("Atomic composition", "Summarises elements represented in the uploaded structure.", "Atom count by element", fig3, element, "Atoms"))
    return visuals



def _spatial_table_visuals(result: NativeParseResult):
    data = result.primary.copy()
    x = _first_column(data, ["x", "pixel_x", "spatial_x", "array_col", "column"])
    y = _first_column(data, ["y", "pixel_y", "spatial_y", "array_row", "row"])
    if not x or not y:
        raise ValueError("Spatial table requires x/y coordinate columns")
    color = _first_column(data, ["expression", "intensity", "value", "cluster", "region", "cell_type"])
    size = _first_column(data, ["area", "count", "weight", "density"])
    subset = data.head(300_000)
    fig = px.scatter(subset, x=x, y=y, color=color, size=size, render_mode="webgl", opacity=0.75, title="Native spatial-coordinate evidence")
    fig.update_yaxes(autorange="reversed", scaleanchor="x", scaleratio=1)
    visuals = [_visual("Native spatial map", "Displays uploaded tissue, spot or object coordinates with available signal metadata.", "Native coordinate-table rendering", fig, subset, "Image/tissue coordinates", result.total_records, "first 300,000 records" if len(data) > 300_000 else None)]
    if color and pd.api.types.is_numeric_dtype(pd.to_numeric(data[color], errors="coerce")):
        distribution = pd.DataFrame({color: pd.to_numeric(data[color], errors="coerce")}).dropna()
        fig2 = px.histogram(distribution.head(500_000), x=color, nbins=80, title=f"{color} distribution")
        visuals.append(_visual("Spatial signal distribution", "Summarises the uploaded spatial signal before region-level interpretation.", "Native signal histogram", fig2, distribution, color, result.total_records))
    return visuals


def _microscopy_table_visuals(result: NativeParseResult):
    data = result.primary.copy()
    numeric = _numeric_columns(data)
    if len(numeric) < 2:
        raise ValueError("Microscopy measurement table requires at least two numeric features")
    x, y = numeric[:2]
    color = _first_column(data, ["condition", "phenotype", "class", "sample", "well"])
    subset = data.head(300_000)
    fig = px.scatter(subset, x=x, y=y, color=color, render_mode="webgl", opacity=0.6, hover_data=[column for column in data.columns[:10]], title="Native microscopy phenotype space")
    visuals = [_visual("Native phenotype space", "Explores object-level measurements decoded from the uploaded microscopy table.", "Object-feature scatter", fig, subset, "Native feature units", result.total_records, "first 300,000 objects" if len(data) > 300_000 else None)]
    for column in numeric[:3]:
        fig_hist = px.histogram(data.head(500_000), x=column, nbins=80, title=f"{column} distribution")
        visuals.append(_visual(f"{column} distribution", "Shows object-level measurement structure and outliers.", "Native object-feature histogram", fig_hist, data[[column]].head(500_000), column, result.total_records))
    return visuals[:4]

def _image_visuals(result: NativeParseResult, *, microscopy: bool):
    array = result.metadata.get("preview_array")
    if not isinstance(array, np.ndarray):
        raise ValueError("Image preview was not decoded")
    fig = px.imshow(array, title="Native scientific image preview")
    fig.update_xaxes(showticklabels=False)
    fig.update_yaxes(showticklabels=False)
    visuals = [_visual("Native image canvas", "Displays the uploaded image preview with bounded, aspect-preserving downsampling.", "Pillow native image reader", fig, result.primary, "Pixels", result.total_records, "preview is downsampled" if result.truncated else None)]
    gray = np.mean(array.astype(float), axis=2)
    hist = pd.DataFrame({"intensity": gray.ravel()})
    fig2 = px.histogram(hist.sample(min(len(hist), 100_000), random_state=42), x="intensity", nbins=80, title="Image intensity distribution")
    visuals.append(_visual("Intensity distribution", "Reveals saturation, low contrast and multi-population image signal.", "RGB mean intensity histogram", fig2, hist.head(100_000), "8-bit intensity"))
    if microscopy:
        threshold = float(np.quantile(gray, 0.75))
        mask = gray >= threshold
        overlay = np.dstack([array[..., 0], np.maximum(array[..., 1], mask * 255), array[..., 2]]) if array.dtype != float else np.dstack([array[..., 0], np.maximum(array[..., 1], mask), array[..., 2]])
        fig3 = px.imshow(overlay, title="Threshold segmentation overlay")
        fig3.update_xaxes(showticklabels=False); fig3.update_yaxes(showticklabels=False)
        stats = pd.DataFrame([{"threshold": threshold, "foreground_pixels": int(mask.sum()), "foreground_fraction": float(mask.mean())}])
        visuals.append(_visual("Segmentation overlay", "Provides a transparent baseline mask for review; specialist segmentation engines can replace it.", "75th-percentile intensity threshold", fig3, stats, "Pixels"))
    return visuals


def _flow_visuals(result: NativeParseResult):
    data = result.primary.copy()
    numeric = _numeric_columns(data)
    if len(numeric) < 2:
        raise ValueError("FCS/native table requires at least two numeric parameters")
    x, y = numeric[:2]
    subset = data[[x, y] + [column for column in data.columns if column not in {x, y}][:4]].head(200_000)
    fig = px.scatter(subset, x=x, y=y, opacity=0.25, render_mode="webgl", title=f"Native event density: {x} versus {y}")
    visuals = [_visual("Native flow-cytometry events", "Plots decoded FCS events using the first two native parameters.", f"Native FCS parser · {len(data):,} events", fig, subset, "Instrument units", result.total_records, "first 200,000 events" if len(data) > 200_000 else None)]
    for channel in numeric[:3]:
        fig_hist = px.histogram(data.head(500_000), x=channel, nbins=100, title=f"{channel} distribution")
        visuals.append(_visual(f"{channel} distribution", "Shows channel intensity structure for gate placement and control comparison.", "Native event histogram", fig_hist, data[[channel]].head(500_000), "Instrument units", result.total_records, "first 500,000 events" if len(data) > 500_000 else None))
    return visuals[:4]


def _mass_visuals(result: NativeParseResult):
    peaks = result.primary.copy()
    visuals = []
    if not peaks.empty and {"mz", "intensity"}.issubset(peaks.columns):
        subset = peaks.sort_values("intensity", ascending=False).head(20_000).sort_values("mz")
        fig = go.Figure(go.Scatter(x=subset["mz"], y=subset["intensity"], mode="markers", marker={"size": 4}, customdata=subset[[column for column in ["spectrum_id", "spectrum_index", "ms_level", "scan_time", "precursor_mz"] if column in subset.columns]], hovertemplate="m/z %{x:.5f}<br>Intensity %{y:.3g}<extra></extra>"))
        fig.update_layout(title="Native mass spectrum peaks", xaxis_title="m/z", yaxis_title="Intensity")
        visuals.append(_visual("Native mass spectrum", "Displays decoded m/z-intensity pairs from mzML/MGF evidence.", f"Native {result.format_key.upper()} parser", fig, subset, "m/z and intensity", result.total_records, "top 20,000 intensity-ranked peaks" if len(peaks) > 20_000 else None))
    spectra = result.secondary.get("spectra", pd.DataFrame())
    if not spectra.empty and "scan_time" in spectra.columns:
        fig2 = px.line(spectra.sort_values("scan_time"), x="scan_time", y="tic", color="ms_level" if "ms_level" in spectra.columns else None, title="Total-ion chromatogram")
        visuals.append(_visual("Total-ion chromatogram", "Tracks total ion signal across native scan time.", "Sum of decoded spectrum intensities", fig2, spectra, "Intensity"))
    chrom = result.secondary.get("chromatograms", pd.DataFrame())
    if not chrom.empty and {"time", "intensity"}.issubset(chrom.columns):
        fig3 = px.line(chrom, x="time", y="intensity", color="chromatogram_id" if "chromatogram_id" in chrom.columns else None, title="Native chromatogram")
        visuals.append(_visual("Native chromatogram", "Displays chromatogram arrays stored in the mzML file.", "Decoded binary chromatogram arrays", fig3, chrom, "Time / intensity"))
    if not visuals:
        raise ValueError("No plottable peaks or chromatogram arrays were decoded")
    return visuals


def _tree_visuals(result: NativeParseResult):
    nodes = result.primary.copy(); edges = result.secondary.get("edges", pd.DataFrame()).copy()
    if nodes.empty or edges.empty:
        raise ValueError("Tree parser returned no nodes or edges")
    by_id = nodes.set_index("id")
    fig = go.Figure()
    for edge in edges.itertuples():
        if edge.source not in by_id.index or edge.target not in by_id.index:
            continue
        a, b = by_id.loc[edge.source], by_id.loc[edge.target]
        fig.add_trace(go.Scatter(x=[a.x, b.x], y=[b.y, b.y], mode="lines", line={"width": 1}, showlegend=False, hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=[a.x, a.x], y=[a.y, b.y], mode="lines", line={"width": 1}, showlegend=False, hoverinfo="skip"))
    terminals = nodes[nodes["terminal"].astype(bool)]
    fig.add_trace(go.Scatter(x=terminals["x"], y=terminals["y"], mode="markers+text", text=terminals["label"], textposition="middle right", marker={"size": 8}, name="Tips"))
    fig.update_layout(title="Native phylogenetic tree", xaxis_title="Branch length", yaxis={"visible": False}, showlegend=False)
    fig2 = px.histogram(nodes, x="branch_length", nbins=50, title="Branch-length distribution")
    return [
        _visual("Native phylogenetic tree", "Renders the uploaded Newick/Nexus topology and branch lengths.", f"Biopython {result.format_key} parser", fig, nodes, "Branch length", result.total_records),
        _visual("Branch-length distribution", "Highlights unusually long or compressed branches.", "Native branch-length histogram", fig2, nodes[["id", "branch_length", "terminal"]], "Branch length"),
    ]


def _plate_visuals(result: NativeParseResult):
    data = result.primary.copy()
    well = _first_column(data, ["well", "well_id", "position"])
    value = _first_column(data, ["value", "signal", "od", "ct", "cq", "intensity", "concentration"])
    if well and value:
        parsed = data[well].astype(str).str.extract(r"(?P<row>[A-Za-z]+)(?P<column>\d+)")
        data = data.join(parsed)
        data["column"] = pd.to_numeric(data["column"], errors="coerce")
        data[value] = pd.to_numeric(data[value], errors="coerce")
        pivot = data.pivot_table(index="row", columns="column", values=value, aggfunc="mean")
        fig = go.Figure(go.Heatmap(z=pivot.values, x=pivot.columns, y=pivot.index, colorbar={"title": value}))
        fig.update_layout(title="Native plate signal map")
        visuals = [_visual("Native plate map", "Places uploaded well-level values into their physical plate coordinates.", "Well-name parsing and heatmap aggregation", fig, data, value, result.total_records)]
        if "role" in data.columns:
            summary = data.groupby("role", as_index=False)[value].agg(["mean", "std", "count"]).reset_index()
            fig2 = px.bar(summary, x="role", y="mean", error_y="std", text="count", title="Plate role comparison")
            visuals.append(_visual("Plate role comparison", "Compares standards, controls and samples from the uploaded layout.", "Role-level mean and standard deviation", fig2, summary, value))
        return visuals
    raise ValueError("Plate table requires a well column and a numeric signal/value column")


def _pedigree_visuals(result: NativeParseResult):
    data = result.primary.copy()
    individual = _first_column(data, ["individual_id", "id", "sample"])
    father = _first_column(data, ["father_id", "father"])
    mother = _first_column(data, ["mother_id", "mother"])
    if not individual:
        raise ValueError("Pedigree input requires an individual identifier")
    generations: dict[str, int] = {}
    ids = data[individual].astype(str).tolist()
    for _ in range(10):
        changed = False
        for row in data.itertuples(index=False):
            values = row._asdict()
            person = str(values[individual])
            parents = [str(values.get(column, "")) for column in [father, mother] if column]
            parent_generations = [generations[p] for p in parents if p in generations and p not in {"0", "", "nan"}]
            generation = (max(parent_generations) + 1) if parent_generations else generations.get(person, 0)
            if generations.get(person) != generation:
                generations[person] = generation; changed = True
        if not changed: break
    data["generation"] = data[individual].astype(str).map(generations).fillna(0).astype(int)
    data["x"] = data.groupby("generation").cumcount() + 1
    data["y"] = -data["generation"]
    by_id = data.set_index(data[individual].astype(str))
    fig = go.Figure()
    for row in data.itertuples(index=False):
        values = row._asdict(); person = str(values[individual])
        for parent_col in [father, mother]:
            if not parent_col: continue
            parent = str(values.get(parent_col, ""))
            if parent in by_id.index and parent not in {"0", "", "nan"}:
                a, b = by_id.loc[parent], by_id.loc[person]
                fig.add_trace(go.Scatter(x=[a["x"], b["x"]], y=[a["y"], b["y"]], mode="lines", showlegend=False, hoverinfo="skip"))
    phenotype = _first_column(data, ["phenotype", "affected", "status"])
    fig.add_trace(go.Scatter(x=data["x"], y=data["y"], mode="markers+text", text=data[individual].astype(str), textposition="bottom center", marker={"size": 24, "color": pd.to_numeric(data[phenotype], errors="coerce") if phenotype else data["generation"], "colorscale": "Viridis", "line": {"width": 1}}, name="Individuals"))
    fig.update_layout(title="Native pedigree and segregation", xaxis={"visible": False}, yaxis={"visible": False})
    return [_visual("Native pedigree", "Renders family relationships directly from PED/FAM or mapped pedigree columns.", "Parent-child graph reconstruction", fig, data, "Generation", result.total_records)]


def _outbreak_visuals(result: NativeParseResult):
    data = result.primary.copy()
    lat = _first_column(data, ["lat", "latitude"]); lon = _first_column(data, ["lon", "lng", "longitude"])
    if not lat or not lon:
        raise ValueError("Outbreak table requires latitude and longitude")
    color = _first_column(data, ["cluster", "lineage", "pathogen", "host"])
    size = _first_column(data, ["cases", "count", "amr_score", "weight"])
    date = _first_column(data, ["date", "collection_date", "time"])
    fig = px.scatter_geo(data.head(100_000), lat=lat, lon=lon, color=color, size=size, hover_data=[column for column in data.columns[:10]], animation_frame=date if date and data[date].nunique() <= 200 else None, title="Native outbreak geography")
    visuals = [_visual("Native outbreak map", "Maps uploaded sample or event coordinates with available cluster and time metadata.", "Geographic point rendering", fig, data.head(100_000), "Latitude/longitude", result.total_records, "first 100,000 points" if len(data) > 100_000 else None)]
    if date:
        trend = data.assign(_date=pd.to_datetime(data[date], errors="coerce")).dropna(subset=["_date"]).groupby(pd.Grouper(key="_date", freq="W")).size().reset_index(name="records")
        fig2 = px.line(trend, x="_date", y="records", markers=True, title="Outbreak records over time")
        visuals.append(_visual("Outbreak timeline", "Shows temporal accumulation or decline in the uploaded records.", "Weekly record aggregation", fig2, trend, "Records/week"))
    return visuals


def _pangenome_visuals(result: NativeParseResult):
    nodes = result.primary.copy(); edges = result.secondary.get("edges", pd.DataFrame()).copy()
    if nodes.empty:
        raise ValueError("GFA contains no segment records")
    count = len(nodes)
    angles = np.linspace(0, 2 * np.pi, count, endpoint=False)
    nodes["x"] = np.cos(angles); nodes["y"] = np.sin(angles)
    by_id = nodes.set_index("id")
    fig = go.Figure()
    for edge in edges.head(50_000).itertuples(index=False):
        if edge.source in by_id.index and edge.target in by_id.index:
            a, b = by_id.loc[edge.source], by_id.loc[edge.target]
            fig.add_trace(go.Scatter(x=[a.x, b.x], y=[a.y, b.y], mode="lines", line={"width": 1}, opacity=0.35, showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=nodes["x"], y=nodes["y"], mode="markers", text=nodes["id"], marker={"size": 7 + 15 * pd.to_numeric(nodes.get("length", 1), errors="coerce").fillna(1) / max(float(pd.to_numeric(nodes.get("length", 1), errors="coerce").fillna(1).max()), 1)}, hovertemplate="%{text}<extra></extra>"))
    fig.update_layout(title="Native GFA segment graph", xaxis={"visible": False}, yaxis={"visible": False})
    length = pd.to_numeric(nodes.get("length", pd.Series(dtype=float)), errors="coerce")
    fig2 = px.histogram(pd.DataFrame({"length": length.dropna()}), x="length", nbins=60, title="Segment-length distribution")
    return [
        _visual("Native pangenome graph", "Renders GFA segments and links directly from the uploaded graph.", "GFA S/L record graph", fig, nodes, "Graph layout", result.total_records, "first 50,000 edges" if len(edges) > 50_000 else None),
        _visual("Segment-length distribution", "Shows core graph size structure and possible fragmented regions.", "Native GFA segment lengths", fig2, nodes[[column for column in ["id", "length"] if column in nodes.columns]], "Bases"),
    ]


def _single_cell_visuals(result: NativeParseResult):
    data = result.primary.copy()
    numeric = _numeric_columns(data)
    x = next((column for column in numeric if column.lower().endswith(("_1", "1")) and any(token in column.lower() for token in ["umap", "tsne", "pca"])), numeric[0] if numeric else None)
    y = next((column for column in numeric if column != x and column.lower().endswith(("_2", "2")) and any(token in column.lower() for token in ["umap", "tsne", "pca"])), numeric[1] if len(numeric) > 1 else None)
    if not x or not y:
        raise ValueError("Single-cell input requires at least two embedding/numeric columns")
    color = _first_column(data, ["cell_type", "cluster", "leiden", "condition", "batch"])
    subset = data.head(300_000)
    fig = px.scatter(subset, x=x, y=y, color=color, opacity=0.5, render_mode="webgl", hover_data=[column for column in data.columns[:10]], title="Native single-cell embedding")
    visuals = [_visual("Native single-cell embedding", "Displays the stored UMAP/t-SNE/PCA coordinates and metadata from H5AD or a mapped table.", f"Native {result.format_key.upper()} reader", fig, subset, "Embedding units", result.total_records, "first 300,000 cells" if len(data) > 300_000 else None)]
    if color:
        counts = data.groupby(color, as_index=False).size().rename(columns={"size": "cells"}).sort_values("cells", ascending=False)
        fig2 = px.bar(counts.head(50), x=color, y="cells", title="Cell population composition")
        visuals.append(_visual("Cell population composition", "Summarises native cluster or cell-type abundance.", "Metadata category counts", fig2, counts, "Cells"))
    return visuals


def _sequence_visuals(result: NativeParseResult):
    data = result.primary.copy()
    if result.format_key == "fasta" and not data.empty:
        first = data.iloc[0]
        sequence = str(first.get("sequence", ""))
        window = max(10, min(200, len(sequence) // 100 or 10))
        rows = []
        for start in range(0, len(sequence), window):
            chunk = sequence[start:start+window]
            rows.append({"start": start + 1, "end": start + len(chunk), "gc_fraction": (chunk.count("G") + chunk.count("C")) / max(len(chunk), 1), "hydrophobic_fraction": sum(char in "AILMFWVY" for char in chunk) / max(len(chunk), 1)})
        profile = pd.DataFrame(rows)
        fig = px.line(profile, x="start", y=["gc_fraction", "hydrophobic_fraction"], title=f"Native sequence profile: {first.get('record_id', 'sequence')}")
        fig2 = px.bar(data.head(100), x="record_id", y="length", title="Sequence lengths")
        return [
            _visual("Native sequence profile", "Shows composition along the uploaded FASTA sequence.", f"Sliding window of {window} residues/bases", fig, profile, "Fraction"),
            _visual("Sequence length comparison", "Compares native FASTA records by length.", "FASTA record lengths", fig2, data.head(100), "Bases/residues", result.total_records),
        ]
    if {"start", "end"}.issubset(data.columns):
        fig = px.timeline(data.head(10_000), x_start="start", x_end="end", y="feature_type" if "feature_type" in data.columns else "name", color="strand" if "strand" in data.columns else None, title="Native feature track")
        return [_visual("Native feature track", "Displays uploaded genomic or protein feature intervals.", f"Native {result.format_key.upper()} intervals", fig, data.head(10_000), "Coordinates", result.total_records, "first 10,000 features" if len(data) > 10_000 else None)]
    raise ValueError("Sequence-track viewer requires FASTA or interval features")


def _multiomics_visuals(result: NativeParseResult):
    data = result.primary.copy()
    source = _first_column(data, ["source", "gene", "from", "feature"]); target = _first_column(data, ["target", "protein", "to", "pathway"]); value = _first_column(data, ["value", "weight", "score", "correlation"])
    if not source or not target:
        raise ValueError("Multi-omics relationship table requires source and target columns")
    subset = data.head(50_000).copy()
    labels = list(dict.fromkeys(subset[source].astype(str).tolist() + subset[target].astype(str).tolist()))
    index = {label: i for i, label in enumerate(labels)}
    weights = pd.to_numeric(subset[value], errors="coerce").fillna(1).abs().tolist() if value else [1] * len(subset)
    fig = go.Figure(go.Sankey(node={"label": labels}, link={"source": subset[source].astype(str).map(index), "target": subset[target].astype(str).map(index), "value": weights}))
    fig.update_layout(title="Native cross-omics relationship flow")
    return [_visual("Native multi-omics relationship", "Traces uploaded feature-to-feature or feature-to-pathway links.", "Sankey rendering of mapped relationships", fig, subset, "Relationship weight", result.total_records, "first 50,000 links" if len(data) > 50_000 else None)]


def _bioprocess_visuals(result: NativeParseResult):
    data = result.primary.copy(); time = _first_column(data, ["time", "hours", "timestamp", "elapsed_time"])
    numeric = [column for column in _numeric_columns(data) if column != time]
    if not time or not numeric:
        raise ValueError("Bioprocess input requires time and at least one numeric process variable")
    batch = _first_column(data, ["batch", "reactor", "run", "vessel"])
    melted = data.melt(id_vars=[column for column in [time, batch] if column], value_vars=numeric[:8], var_name="variable", value_name="value")
    fig = px.line(melted, x=time, y="value", color="variable", line_dash=batch if batch else None, title="Native bioprocess trajectories")
    return [_visual("Native process trajectories", "Displays uploaded process variables over time with optional batch separation.", "Long-format process time-series rendering", fig, melted, "Native units", result.total_records)]


def _workflow_visuals(result: NativeParseResult):
    nodes = result.primary.copy(); edges = result.secondary.get("edges", pd.DataFrame()).copy()
    if nodes.empty:
        raise ValueError("Workflow JSON contains no nodes")
    id_col = _first_column(nodes, ["id", "key", "name", "node_id"]) or nodes.columns[0]
    count = len(nodes); angle = np.linspace(0, 2 * np.pi, count, endpoint=False)
    nodes["x"] = np.cos(angle); nodes["y"] = np.sin(angle)
    by_id = nodes.set_index(nodes[id_col].astype(str))
    source_col = _first_column(edges, ["source", "from", "parent"]); target_col = _first_column(edges, ["target", "to", "child"])
    fig = go.Figure()
    if source_col and target_col:
        for edge in edges.head(50_000).itertuples(index=False):
            values = edge._asdict(); source = str(values[source_col]); target = str(values[target_col])
            if source in by_id.index and target in by_id.index:
                a, b = by_id.loc[source], by_id.loc[target]
                fig.add_trace(go.Scatter(x=[a.x, b.x], y=[a.y, b.y], mode="lines", showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=nodes["x"], y=nodes["y"], mode="markers+text", text=nodes[id_col].astype(str), textposition="top center", marker={"size": 18}))
    fig.update_layout(title="Native workflow DAG", xaxis={"visible": False}, yaxis={"visible": False})
    return [_visual("Native workflow DAG", "Renders uploaded workflow nodes and dependencies.", "Workflow JSON node-edge graph", fig, nodes, "Graph layout", result.total_records)]


def _freezer_visuals(result: NativeParseResult):
    data = result.primary.copy(); row = _first_column(data, ["row", "rack_row", "box_row"]); col = _first_column(data, ["column", "col", "rack_column", "box_column"]); value = _first_column(data, ["status", "occupied", "risk", "expiry_days", "temperature"])
    if not row or not col:
        raise ValueError("Inventory table requires row and column positions")
    data[col] = pd.to_numeric(data[col], errors="coerce")
    if value and pd.api.types.is_numeric_dtype(pd.to_numeric(data[value], errors="coerce")):
        data["_value"] = pd.to_numeric(data[value], errors="coerce")
    else:
        data["_value"] = pd.Categorical(data[value] if value else "occupied").codes
    pivot = data.pivot_table(index=row, columns=col, values="_value", aggfunc="mean")
    fig = go.Figure(go.Heatmap(z=pivot.values, x=pivot.columns, y=pivot.index, colorbar={"title": value or "status"}))
    fig.update_layout(title="Native storage position map")
    return [_visual("Native freezer/sample map", "Places uploaded inventory records into rack, box or freezer coordinates.", "Storage-coordinate heatmap", fig, data, value or "Status", result.total_records)]


def _generic_visuals(result: NativeParseResult):
    data = result.primary.copy(); numeric = _numeric_columns(data)
    if numeric:
        fig = px.histogram(data.head(100_000), x=numeric[0], nbins=60, title=f"Native {numeric[0]} distribution")
        return [_visual("Native data distribution", "Provides a safe view of decoded native records.", f"Native {result.format_key.upper()} reader", fig, data.head(100_000), numeric[0], result.total_records, "first 100,000 records" if len(data) > 100_000 else None)]
    fig = go.Figure().add_annotation(text=f"{len(data):,} native records decoded", x=0.5, y=0.5, showarrow=False)
    return [_visual("Native file summary", "The file was decoded successfully but contains no numeric field for a chart.", f"Native {result.format_key.upper()} reader", fig, data, source_count=result.total_records)]


def build_native_viewer_visuals(viewer_key: str, result: NativeParseResult):
    if viewer_key == "genome_browser": return _genome_visuals(result)
    if viewer_key == "molecular_3d": return _molecular_visuals(result)
    if viewer_key == "pathology": return _image_visuals(result, microscopy=False) if isinstance(result.metadata.get("preview_array"), np.ndarray) else _spatial_table_visuals(result)
    if viewer_key == "microscopy": return _image_visuals(result, microscopy=True) if isinstance(result.metadata.get("preview_array"), np.ndarray) else _microscopy_table_visuals(result)
    if viewer_key == "flow_gating": return _flow_visuals(result)
    if viewer_key == "mass_spectrometry": return _mass_visuals(result)
    if viewer_key == "phylogenetic_tree": return _tree_visuals(result)
    if viewer_key == "plate_map": return _plate_visuals(result)
    if viewer_key == "pedigree": return _pedigree_visuals(result)
    if viewer_key == "outbreak_map": return _outbreak_visuals(result)
    if viewer_key == "pangenome_graph": return _pangenome_visuals(result)
    if viewer_key == "single_cell": return _single_cell_visuals(result)
    if viewer_key == "sequence_track": return _sequence_visuals(result)
    if viewer_key == "multiomics": return _multiomics_visuals(result)
    if viewer_key == "bioprocess_live": return _bioprocess_visuals(result)
    if viewer_key == "workflow_dag": return _workflow_visuals(result)
    if viewer_key == "freezer_map": return _freezer_visuals(result)
    return _generic_visuals(result)


__all__ = ["build_native_viewer_visuals"]
