from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from scipy import ndimage

from .advanced_scientific_viewers import ViewerVisual, _rng, _visual

def _genome_browser(seed: int = 110) -> list[ViewerVisual]:
    rng = _rng(seed)
    start = 1_000_000
    end = 1_060_000
    bins = np.arange(start, end + 1, 500)
    coverage = 35 + 12 * np.sin(np.linspace(0, 7 * np.pi, len(bins))) + rng.normal(0, 4, len(bins))
    coverage = np.clip(coverage, 0, None)
    variants = pd.DataFrame({
        "position": rng.integers(start, end, 55),
        "impact": rng.choice(["HIGH", "MODERATE", "LOW", "MODIFIER"], 55, p=[0.08, 0.22, 0.35, 0.35]),
        "allele_frequency": np.round(rng.beta(0.8, 4.5, 55), 4),
        "variant": [f"v{i+1}" for i in range(55)],
    }).sort_values("position")
    genes = pd.DataFrame([
        {"feature": "GENE1", "start": start + 4_000, "end": start + 19_000, "strand": "+", "track": "Gene models"},
        {"feature": "GENE2", "start": start + 23_000, "end": start + 39_000, "strand": "-", "track": "Gene models"},
        {"feature": "GENE3", "start": start + 43_000, "end": start + 58_000, "strand": "+", "track": "Gene models"},
    ])
    peaks = pd.DataFrame({
        "start": rng.integers(start, end - 2_000, 15),
        "width": rng.integers(300, 2_000, 15),
        "signal": rng.uniform(2, 14, 15),
    })
    peaks["end"] = peaks["start"] + peaks["width"]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=bins, y=coverage, mode="lines", fill="tozeroy", name="Coverage", customdata=np.arange(len(bins))))
    impact_y = {"MODIFIER": 1.15, "LOW": 1.28, "MODERATE": 1.41, "HIGH": 1.54}
    fig.add_trace(go.Scatter(
        x=variants["position"], y=variants["impact"].map(impact_y), mode="markers", name="Variants",
        marker={"size": 7 + variants["allele_frequency"] * 18},
        text=variants["variant"] + " · " + variants["impact"], hovertemplate="%{text}<br>Position %{x}<extra></extra>",
        yaxis="y2", customdata=np.arange(len(variants)),
    ))
    for row in genes.itertuples():
        fig.add_shape(type="rect", x0=row.start, x1=row.end, y0=0.48, y1=0.68, xref="x", yref="paper", line_width=1)
        fig.add_annotation(x=(row.start + row.end) / 2, y=0.58, yref="paper", text=f"{row.feature} {row.strand}", showarrow=False)
    for row in peaks.itertuples():
        fig.add_shape(type="rect", x0=row.start, x1=row.end, y0=0.12, y1=0.12 + min(row.signal / 45, 0.26), xref="x", yref="paper", line_width=0)
    fig.update_layout(
        title="Synchronized genomic tracks · chr7 demo interval", xaxis_title="Genomic coordinate", yaxis_title="Coverage",
        yaxis2={"overlaying": "y", "side": "right", "range": [1, 1.65], "showticklabels": False, "title": "Variant impact"},
        hovermode="x unified",
    )
    browser_data = pd.concat([
        pd.DataFrame({"record_type": "coverage", "position": bins, "value": coverage}),
        variants.rename(columns={"allele_frequency": "value"}).assign(record_type="variant"),
    ], ignore_index=True, sort=False)
    fig2 = px.scatter(variants, x="position", y="allele_frequency", color="impact", size="allele_frequency", hover_name="variant", title="Variant evidence at the selected interval")
    fig2.update_xaxes(range=[start, end])
    fig3 = px.bar(peaks.sort_values("signal", ascending=False), x="start", y="signal", hover_data=["end", "width"], title="Accessible/peak regions")
    return [
        _visual("Genome track browser", "Coordinates, coverage, gene models, peaks and variants remain aligned while zooming.", "Multi-track coordinate canvas", fig, browser_data, "Genomic coordinate / read depth", len(browser_data)),
        _visual("Variant interval explorer", "Highlights variant position, impact and allele frequency in the selected interval.", "Variant scatter with impact encoding", fig2, variants, "Allele frequency"),
        _visual("Peak and regulatory signal", "Ranks candidate accessible or regulatory intervals by signal.", "Interval-signal bar view", fig3, peaks, "Relative signal"),
    ]

def _parse_pdb_atoms(text: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        if not line.startswith(("ATOM", "HETATM")) or len(line) < 54:
            continue
        try:
            rows.append({
                "record": line[:6].strip(), "atom": line[12:16].strip(), "residue": line[17:20].strip(),
                "chain": line[21:22].strip() or "A", "residue_id": int(line[22:26]),
                "x": float(line[30:38]), "y": float(line[38:46]), "z": float(line[46:54]),
                "element": (line[76:78].strip() if len(line) >= 78 else line[12:14].strip()).title(),
            })
        except (ValueError, TypeError):
            continue
    return pd.DataFrame(rows)

def _demo_atoms(seed: int = 111) -> pd.DataFrame:
    rng = _rng(seed)
    t = np.linspace(0, 8 * np.pi, 180)
    backbone = pd.DataFrame({
        "record": "ATOM", "atom": "CA", "residue": rng.choice(["ALA", "GLY", "SER", "LEU", "TYR"], len(t)),
        "chain": np.where(np.arange(len(t)) < 100, "A", "B"), "residue_id": np.arange(1, len(t) + 1),
        "x": 10 * np.cos(t), "y": 10 * np.sin(t), "z": np.linspace(-25, 25, len(t)), "element": "C",
    })
    ligand = pd.DataFrame({
        "record": "HETATM", "atom": ["C1", "C2", "N1", "O1", "C3", "O2"], "residue": "LIG", "chain": "L",
        "residue_id": 1, "x": rng.normal(0, 1.5, 6), "y": rng.normal(0, 1.5, 6), "z": rng.normal(0, 1.5, 6),
        "element": ["C", "C", "N", "O", "C", "O"],
    })
    return pd.concat([backbone, ligand], ignore_index=True)

def _molecular_3d(seed: int = 111, pdb_text: str | None = None) -> list[ViewerVisual]:
    atoms = _parse_pdb_atoms(pdb_text or "")
    if atoms.empty:
        atoms = _demo_atoms(seed)
    protein = atoms[atoms["record"] == "ATOM"].copy()
    ligand = atoms[atoms["record"] == "HETATM"].copy()
    fig = go.Figure()
    for chain, group in protein.groupby("chain", sort=False):
        group = group.sort_values("residue_id")
        fig.add_trace(go.Scatter3d(x=group["x"], y=group["y"], z=group["z"], mode="lines+markers", name=f"Chain {chain}", marker={"size": 2}, line={"width": 5}, customdata=group[["residue", "residue_id", "atom"]], hovertemplate="%{customdata[0]} %{customdata[1]} · %{customdata[2]}<extra></extra>"))
    if not ligand.empty:
        fig.add_trace(go.Scatter3d(x=ligand["x"], y=ligand["y"], z=ligand["z"], mode="markers", name="Ligand", marker={"size": 8, "symbol": "diamond"}, text=ligand["element"], hovertemplate="Ligand %{text}<extra></extra>"))
    fig.update_layout(title="Interactive molecular scene", scene={"xaxis_title": "X (Å)", "yaxis_title": "Y (Å)", "zaxis_title": "Z (Å)", "aspectmode": "data"})
    if ligand.empty or protein.empty:
        contacts = pd.DataFrame(columns=["residue", "residue_id", "distance"])
    else:
        centre = ligand[["x", "y", "z"]].mean().to_numpy()
        coords = protein[["x", "y", "z"]].to_numpy()
        protein["distance"] = np.sqrt(((coords - centre) ** 2).sum(axis=1))
        contacts = protein.nsmallest(25, "distance")[["chain", "residue", "residue_id", "distance"]]
    fig2 = px.bar(contacts.sort_values("distance"), x="distance", y=contacts["chain"].astype(str) + ":" + contacts["residue"] + contacts["residue_id"].astype(str), orientation="h", title="Nearest residues to ligand/pocket centre") if not contacts.empty else go.Figure()
    if contacts.empty:
        fig2.update_layout(title="No ligand atoms available for contact ranking")
    residue_profile = protein.groupby(["chain", "residue_id"], as_index=False).agg(x=("x", "mean"), y=("y", "mean"), z=("z", "mean"))
    residue_profile["radial_distance"] = np.sqrt(residue_profile[["x", "y", "z"]].pow(2).sum(axis=1))
    fig3 = px.line(residue_profile, x="residue_id", y="radial_distance", color="chain", title="Residue geometry profile")
    return [
        _visual("3D molecular structure", "Inspects chains, residues and ligand atoms in an interactive 3D coordinate scene.", "PDB/mmCIF atom-coordinate rendering", fig, atoms, "Å", len(atoms)),
        _visual("Pocket contact ranking", "Ranks residues nearest the ligand or pocket centre for targeted review.", "Euclidean atom-to-centroid distance", fig2, contacts, "Å"),
        _visual("Residue geometry profile", "Shows residue-level spatial variation along each chain.", "Mean residue coordinate radial distance", fig3, residue_profile, "Å"),
    ]

def _synthetic_tissue(seed: int = 112, size: int = 220) -> tuple[np.ndarray, np.ndarray, pd.DataFrame]:
    rng = _rng(seed)
    y, x = np.mgrid[-1:1:complex(size), -1:1:complex(size)]
    base = 0.25 + 0.35 * np.exp(-((x + 0.25) ** 2 + (y + 0.1) ** 2) / 0.12)
    base += 0.45 * np.exp(-((x - 0.35) ** 2 + (y - 0.25) ** 2) / 0.08)
    texture = rng.normal(0, 0.08, (size, size))
    image = np.clip(base + texture, 0, 1)
    expression = np.clip(1.2 * np.exp(-((x - 0.2) ** 2 + (y + 0.15) ** 2) / 0.15) + rng.normal(0, 0.05, (size, size)), 0, None)
    points = pd.DataFrame({
        "x": rng.integers(0, size, 1200), "y": rng.integers(0, size, 1200),
    })
    points["expression"] = expression[points["y"], points["x"]]
    points["region"] = np.where(points["x"] < size / 2, "Left tissue", "Right tissue")
    return image, expression, points

def _pathology(seed: int = 112, image: np.ndarray | None = None, overlay_opacity: float = 0.55) -> list[ViewerVisual]:
    if image is None:
        image, expression, points = _synthetic_tissue(seed)
    else:
        gray = image.mean(axis=2) if image.ndim == 3 else image.astype(float)
        gray = (gray - np.nanmin(gray)) / max(float(np.nanmax(gray) - np.nanmin(gray)), 1e-9)
        image = gray
        expression = ndimage.gaussian_filter(gray, sigma=max(1, gray.shape[0] / 80))
        rng = _rng(seed)
        points = pd.DataFrame({"x": rng.integers(0, gray.shape[1], 1000), "y": rng.integers(0, gray.shape[0], 1000)})
        points["expression"] = expression[points["y"], points["x"]]
        points["region"] = np.where(points["x"] < gray.shape[1] / 2, "Left tissue", "Right tissue")
    fig = go.Figure()
    fig.add_trace(go.Heatmap(z=image, colorscale="Gray", showscale=False, hoverinfo="skip"))
    fig.add_trace(go.Heatmap(z=expression, colorscale="Viridis", opacity=float(overlay_opacity), colorbar={"title": "Expression"}))
    fig.update_layout(title="Tissue image with spatial expression overlay", yaxis={"autorange": "reversed", "scaleanchor": "x"})
    fig2 = px.scatter(points, x="x", y="y", color="expression", symbol="region", title="Spatial spot/cell expression map", opacity=0.72)
    fig2.update_yaxes(autorange="reversed", scaleanchor="x")
    region_summary = points.groupby("region", as_index=False).agg(mean_expression=("expression", "mean"), spots=("expression", "size"))
    fig3 = px.bar(region_summary, x="region", y="mean_expression", text="spots", title="Region-level expression summary")
    overlay_data = points.copy()
    return [
        _visual("Whole-slide spatial overlay", "Combines tissue morphology and an adjustable spatial signal layer.", "Raster overlay with synchronized coordinates", fig, overlay_data, "Image pixels / relative expression", int(image.size), "Raster shown at preview resolution"),
        _visual("Spatial spot explorer", "Supports zooming and reviewing individual spots or cell-like observations.", "Coordinate scatter with expression encoding", fig2, points, "Relative expression"),
        _visual("Region comparison", "Compares mean expression and observation counts across annotated tissue regions.", "Region aggregation", fig3, region_summary, "Mean relative expression"),
    ]

def _microscopy(seed: int = 113, image: np.ndarray | None = None, threshold: float = 0.58, min_size: int = 20) -> list[ViewerVisual]:
    rng = _rng(seed)
    if image is None:
        size = 240
        y, x = np.mgrid[:size, :size]
        arr = rng.normal(0.08, 0.025, (size, size))
        for _ in range(75):
            cx, cy = rng.integers(8, size - 8, 2)
            radius = rng.uniform(2.5, 7.5)
            arr += rng.uniform(0.45, 1.0) * np.exp(-((x - cx) ** 2 + (y - cy) ** 2) / (2 * radius**2))
        image = np.clip(arr, 0, 1)
    else:
        if image.ndim == 3:
            image = image.mean(axis=2)
        image = image.astype(float)
        image = (image - np.nanmin(image)) / max(float(np.nanmax(image) - np.nanmin(image)), 1e-9)
    mask = image >= float(threshold)
    labels, _ = ndimage.label(mask)
    objects = ndimage.find_objects(labels)
    rows: list[dict[str, Any]] = []
    cleaned = np.zeros_like(labels)
    new_id = 0
    for object_id, slc in enumerate(objects, start=1):
        if slc is None:
            continue
        object_mask = labels[slc] == object_id
        area = int(object_mask.sum())
        if area < int(min_size):
            continue
        new_id += 1
        cleaned[slc][object_mask] = new_id
        ys, xs = np.where(labels == object_id)
        rows.append({"object_id": new_id, "area": area, "centroid_x": float(xs.mean()), "centroid_y": float(ys.mean()), "mean_intensity": float(image[labels == object_id].mean())})
    object_table = pd.DataFrame(rows)
    fig = go.Figure()
    fig.add_trace(go.Heatmap(z=image, colorscale="Gray", showscale=False, hoverinfo="skip"))
    if not object_table.empty:
        fig.add_trace(go.Scatter(x=object_table["centroid_x"], y=object_table["centroid_y"], mode="markers+text", text=object_table["object_id"], textposition="top center", name="Detected objects", marker={"size": np.clip(np.sqrt(object_table["area"]) * 2, 5, 26), "color": object_table["mean_intensity"], "colorscale": "Turbo", "showscale": True}))
    fig.update_layout(title="Microscopy image with segmentation overlay", yaxis={"autorange": "reversed", "scaleanchor": "x"})
    fig2 = px.histogram(object_table, x="area", nbins=30, marginal="box", title="Detected object-size distribution") if not object_table.empty else go.Figure()
    fig3 = px.scatter(object_table, x="area", y="mean_intensity", size="area", hover_name="object_id", title="Morphology and intensity phenotype space") if not object_table.empty else go.Figure()
    if object_table.empty:
        fig2.update_layout(title="No objects passed the current threshold and size filter")
        fig3.update_layout(title="No morphology observations available")
    return [
        _visual("Segmentation overlay editor", "Shows the raw image and current object detections for threshold review.", "Intensity thresholding, connected components and minimum-area filtering", fig, object_table, "Pixels / normalized intensity", int(image.size), "Preview-resolution segmentation"),
        _visual("Object-size distribution", "Reveals object heterogeneity and potential debris or merged objects.", "Connected-component area distribution", fig2, object_table, "Pixels"),
        _visual("Morphology phenotype space", "Relates object area to fluorescence/intensity for outlier review.", "Object-level scatter", fig3, object_table, "Pixels / normalized intensity"),
    ]

def _flow_gating(seed: int = 114, x_gate: float = 55_000, y_gate: float = 45_000) -> list[ViewerVisual]:
    rng = _rng(seed)
    populations = [("Lymphocytes", 26_000, 18_000, 6_000, 4_500, 1800), ("Monocytes", 55_000, 42_000, 8_500, 7_000, 900), ("Granulocytes", 88_000, 70_000, 10_000, 8_000, 1200), ("Debris", 8_000, 6_000, 4_000, 3_500, 500)]
    frames = []
    for label, mx, my, sx, sy, count in populations:
        frames.append(pd.DataFrame({"FSC_A": rng.normal(mx, sx, count), "SSC_A": rng.normal(my, sy, count), "truth": label}))
    data = pd.concat(frames, ignore_index=True)
    data["gate"] = np.select(
        [(data["FSC_A"] >= x_gate) & (data["SSC_A"] >= y_gate), (data["FSC_A"] < x_gate) & (data["SSC_A"] >= y_gate), (data["FSC_A"] >= x_gate) & (data["SSC_A"] < y_gate)],
        ["Q2 high/high", "Q1 low/high", "Q4 high/low"], default="Q3 low/low",
    )
    fig = px.scatter(data.sample(min(len(data), 4500), random_state=seed), x="FSC_A", y="SSC_A", color="gate", opacity=0.35, title="FSC/SSC gating canvas", render_mode="webgl")
    fig.add_vline(x=x_gate, line_dash="dash")
    fig.add_hline(y=y_gate, line_dash="dash")
    summary = data.groupby("gate", as_index=False).size().rename(columns={"size": "events"})
    summary["percent"] = 100 * summary["events"] / summary["events"].sum()
    fig2 = px.bar(summary, x="gate", y="percent", text="events", title="Gated population composition")
    truth_gate = pd.crosstab(data["truth"], data["gate"], normalize="index") * 100
    fig3 = px.imshow(truth_gate, text_auto=".1f", aspect="auto", title="Gate transfer/identity matrix", labels={"color": "% of source population"})
    matrix_data = truth_gate.reset_index().melt(id_vars="truth", var_name="gate", value_name="percent")
    return [
        _visual("Flow-cytometry gating canvas", "Supports interactive zoom and quadrant thresholds for population review.", "FSC/SSC scatter with configurable gates", fig, data, "Instrument intensity", len(data), "Displayed points are bounded for browser performance"),
        _visual("Population composition", "Reports event count and proportion in each active gate.", "Gate aggregation", fig2, summary, "% events"),
        _visual("Gate identity matrix", "Shows how simulated biological populations distribute across the active gate definition.", "Row-normalized cross-tabulation", fig3, matrix_data, "% of source population"),
    ]

def _mass_spectrometry(seed: int = 115) -> list[ViewerVisual]:
    rng = _rng(seed)
    rt = np.linspace(0, 22, 1800)
    intensity = rng.lognormal(-0.4, 0.35, len(rt))
    peak_centres = [2.4, 4.8, 7.1, 9.6, 12.2, 16.4, 19.2]
    for centre in peak_centres:
        intensity += rng.uniform(3e4, 1.4e5) * np.exp(-((rt - centre) ** 2) / (2 * rng.uniform(0.025, 0.18) ** 2))
    chromatogram = pd.DataFrame({"retention_time": rt, "intensity": intensity})
    fig = px.line(chromatogram, x="retention_time", y="intensity", title="Total-ion chromatogram")
    fig.update_yaxes(type="log")
    mz = np.sort(rng.uniform(80, 1_200, 420))
    ms1 = pd.DataFrame({"mz": mz, "intensity": rng.pareto(2.2, len(mz)) * 1e5})
    top_idx = rng.choice(len(ms1), 15, replace=False)
    ms1.loc[top_idx, "intensity"] *= rng.uniform(10, 80, len(top_idx))
    fig2 = go.Figure(go.Bar(x=ms1["mz"], y=ms1["intensity"], width=0.7))
    fig2.update_layout(title="MS1 centroid spectrum", xaxis_title="m/z", yaxis_title="Intensity")
    fragments = pd.DataFrame({"mz": np.sort(rng.uniform(40, 650, 90)), "intensity": rng.gamma(1.5, 2e4, 90)})
    fragments["annotation"] = [f"b{i+1}" if i % 2 == 0 else f"y{i+1}" for i in range(len(fragments))]
    fig3 = go.Figure(go.Bar(x=fragments["mz"], y=fragments["intensity"], text=fragments["annotation"], hovertemplate="%{text}<br>m/z %{x:.4f}<br>Intensity %{y:.0f}<extra></extra>"))
    fig3.update_layout(title="MS/MS fragment spectrum", xaxis_title="m/z", yaxis_title="Intensity")
    return [
        _visual("Chromatogram viewer", "Displays chromatographic peak shape, retention time and dynamic range.", "Synthetic TIC preview", fig, chromatogram, "Minutes / intensity units", len(chromatogram)),
        _visual("MS1 spectrum", "Supports zooming across precursor/isotope features and relative abundance.", "Centroid peak spectrum", fig2, ms1, "m/z / intensity"),
        _visual("MS/MS fragment annotation", "Shows fragment evidence and labels for identification review.", "Fragment-ion stick spectrum", fig3, fragments, "m/z / intensity"),
    ]

