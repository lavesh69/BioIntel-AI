from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go

try:  # Optional in the lightweight core profile.
    import networkx as nx
except ImportError:  # pragma: no cover
    nx = None

from biointel.structural.pdb_analysis import parse_structure

PROTEIN_RESIDUES = {
    "ALA",
    "ARG",
    "ASN",
    "ASP",
    "CYS",
    "GLN",
    "GLU",
    "GLY",
    "HIS",
    "ILE",
    "LEU",
    "LYS",
    "MET",
    "PHE",
    "PRO",
    "SER",
    "THR",
    "TRP",
    "TYR",
    "VAL",
}


@dataclass(frozen=True)
class StructureViewSummary:
    total_atoms: int
    selected_atoms: int
    displayed_atoms: int
    sampled: bool
    preset: str
    ligand_atoms: int
    protein_atoms: int


def structure_atom_table(text: str, *, format_hint: str = "pdb") -> pd.DataFrame:
    """Convert a PDB/mmCIF structure into a stable atom-level visualization table."""

    structure = parse_structure(text, format_hint=format_hint)
    rows: list[dict[str, Any]] = []
    for atom in structure.get_atoms():
        residue = atom.get_parent()
        residue_name = residue.get_resname().strip().upper()
        chain = str(residue.get_parent().id)
        if residue_name in PROTEIN_RESIDUES:
            group = "Protein"
        elif residue_name in {"HOH", "WAT"}:
            group = "Water"
        else:
            group = "Ligand / other"
        rows.append(
            {
                "x": float(atom.coord[0]),
                "y": float(atom.coord[1]),
                "z": float(atom.coord[2]),
                "atom": atom.get_name().strip(),
                "element": str(getattr(atom, "element", "") or "").strip().upper(),
                "residue": residue_name,
                "residue_number": int(residue.id[1]),
                "insertion_code": str(residue.id[2]).strip(),
                "chain": chain,
                "group": group,
            }
        )
    return pd.DataFrame(rows)


def _preserving_sample(frame: pd.DataFrame, maximum_atoms: int) -> tuple[pd.DataFrame, bool]:
    if len(frame) <= maximum_atoms:
        return frame.copy(), False
    protected = frame[(frame["group"] != "Protein") | (frame["atom"] == "CA")]
    protected = protected.drop_duplicates()
    remaining_budget = max(0, maximum_atoms - len(protected))
    protein_pool = frame.drop(index=protected.index, errors="ignore")
    if remaining_budget and not protein_pool.empty:
        sampled_protein = protein_pool.sample(
            min(remaining_budget, len(protein_pool)), random_state=42
        )
        sampled = pd.concat([protected, sampled_protein], ignore_index=True)
    else:
        sampled = protected.head(maximum_atoms).copy()
    return sampled, True


def select_structure_atoms(
    atoms: pd.DataFrame,
    *,
    selected_chains: list[str] | tuple[str, ...],
    visible_groups: list[str] | tuple[str, ...],
    preset: str = "Backbone + ligands",
    maximum_atoms: int = 8_000,
    ligand_focus_radius: float = 10.0,
) -> tuple[pd.DataFrame, StructureViewSummary]:
    """Apply view-preset filtering while preserving ligands and C-alpha atoms."""

    selected = atoms[
        atoms["chain"].astype(str).isin([str(value) for value in selected_chains])
        & atoms["group"].isin(list(visible_groups))
    ].copy()
    normalized = str(preset).strip().lower()
    if normalized == "backbone + ligands":
        displayed = selected[
            ((selected["group"] == "Protein") & (selected["atom"] == "CA"))
            | (selected["group"] == "Ligand / other")
            | ((selected["group"] == "Water") & False)
        ].copy()
    elif normalized == "c-alpha trace":
        displayed = selected[
            (selected["group"] == "Protein") & (selected["atom"] == "CA")
        ].copy()
    elif normalized == "ligand focus":
        ligands = selected[selected["group"] == "Ligand / other"]
        if ligands.empty:
            displayed = selected[
                ((selected["group"] == "Protein") & (selected["atom"] == "CA"))
                | (selected["group"] == "Ligand / other")
            ].copy()
        else:
            ligand_coordinates = ligands[["x", "y", "z"]].to_numpy(dtype=float)
            all_coordinates = selected[["x", "y", "z"]].to_numpy(dtype=float)
            minimum_squared = np.full(len(selected), np.inf, dtype=float)
            for chunk_start in range(0, len(ligand_coordinates), 256):
                chunk = ligand_coordinates[chunk_start : chunk_start + 256]
                squared = ((all_coordinates[:, None, :] - chunk[None, :, :]) ** 2).sum(axis=2)
                minimum_squared = np.minimum(minimum_squared, squared.min(axis=1))
            displayed = selected[minimum_squared <= float(ligand_focus_radius) ** 2].copy()
    else:  # All selected atoms
        displayed = selected.copy()

    displayed, sampled = _preserving_sample(displayed, int(maximum_atoms))
    summary = StructureViewSummary(
        total_atoms=len(atoms),
        selected_atoms=len(selected),
        displayed_atoms=len(displayed),
        sampled=sampled,
        preset=preset,
        ligand_atoms=int((displayed["group"] == "Ligand / other").sum()),
        protein_atoms=int((displayed["group"] == "Protein").sum()),
    )
    return displayed, summary


def build_structure_figure(
    atoms: pd.DataFrame,
    *,
    height: int = 780,
    point_size: float = 4.5,
    opacity: float = 0.78,
    show_backbone: bool = True,
    projection: str = "Perspective",
    title: str = "Interactive molecular-coordinate view",
) -> go.Figure:
    """Create a large, camera-stable 3D structure figure with readable traces."""

    figure = go.Figure()
    if show_backbone:
        backbone = atoms[
            (atoms["group"] == "Protein") & (atoms["atom"] == "CA")
        ].sort_values(["chain", "residue_number", "insertion_code"])
        for chain, chain_frame in backbone.groupby("chain", sort=True):
            figure.add_trace(
                go.Scatter3d(
                    x=chain_frame["x"],
                    y=chain_frame["y"],
                    z=chain_frame["z"],
                    mode="lines+markers",
                    name=f"Backbone · chain {chain}",
                    line={"width": max(3, int(round(point_size)))},
                    marker={"size": max(2.0, point_size - 1.0), "opacity": 0.9},
                    customdata=chain_frame[
                        ["atom", "residue", "residue_number", "chain", "element"]
                    ].to_numpy(),
                    hovertemplate=(
                        "Atom %{customdata[0]}<br>Residue %{customdata[1]} "
                        "%{customdata[2]}<br>Chain %{customdata[3]}"
                        "<extra>Backbone</extra>"
                    ),
                )
            )

    group_settings = {
        "Protein": {"size": point_size, "symbol": "circle", "opacity": opacity},
        "Ligand / other": {
            "size": point_size + 4.0,
            "symbol": "diamond",
            "opacity": min(1.0, opacity + 0.15),
        },
        "Water": {
            "size": max(2.0, point_size - 1.5),
            "symbol": "circle-open",
            "opacity": max(0.25, opacity - 0.25),
        },
    }
    for group in ("Protein", "Ligand / other", "Water"):
        group_frame = atoms[atoms["group"] == group]
        if group_frame.empty:
            continue
        settings = group_settings[group]
        figure.add_trace(
            go.Scatter3d(
                x=group_frame["x"],
                y=group_frame["y"],
                z=group_frame["z"],
                mode="markers",
                name=group,
                marker={
                    "size": settings["size"],
                    "symbol": settings["symbol"],
                    "opacity": settings["opacity"],
                    "line": {"width": 0.4},
                },
                customdata=group_frame[
                    ["atom", "residue", "residue_number", "chain", "element"]
                ].to_numpy(),
                hovertemplate=(
                    "Atom %{customdata[0]} (%{customdata[4]})<br>"
                    "Residue %{customdata[1]} %{customdata[2]}<br>"
                    "Chain %{customdata[3]}<extra>%{fullData.name}</extra>"
                ),
            )
        )

    projection_type = "orthographic" if projection.lower().startswith("ortho") else "perspective"
    axis = {
        "showbackground": True,
        "backgroundcolor": "rgba(0,0,0,0)",
        "gridcolor": "rgba(128,128,128,0.18)",
        "zerolinecolor": "rgba(128,128,128,0.28)",
        "showspikes": False,
    }
    figure.update_layout(
        title={"text": title, "x": 0.01, "xanchor": "left"},
        height=int(height),
        margin={"l": 0, "r": 0, "t": 48, "b": 0},
        scene={
            "xaxis": {**axis, "title": "X (Å)"},
            "yaxis": {**axis, "title": "Y (Å)"},
            "zaxis": {**axis, "title": "Z (Å)"},
            "aspectmode": "data",
            "camera": {
                "projection": {"type": projection_type},
                "eye": {"x": 1.45, "y": 1.45, "z": 1.15},
            },
            "dragmode": "orbit",
        },
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.01, "x": 0.0},
        uirevision="biointel-structure-camera-v68",
    )
    return figure


def build_residue_network_figure(
    edges: pd.DataFrame,
    nodes: pd.DataFrame,
    *,
    height: int = 720,
    maximum_nodes: int = 350,
) -> go.Figure | None:
    """Render a residue-contact graph when NetworkX is available."""

    if nx is None or edges.empty or nodes.empty:
        return None
    graph = nx.Graph()
    graph.add_edges_from(edges[["source", "target"]].itertuples(index=False, name=None))
    degree_lookup = nodes.set_index("node")["degree"].to_dict()
    if graph.number_of_nodes() > maximum_nodes:
        keep = sorted(
            graph.nodes,
            key=lambda node: (-int(degree_lookup.get(node, graph.degree(node))), str(node)),
        )[:maximum_nodes]
        graph = graph.subgraph(keep).copy()
    if not graph.nodes:
        return None
    positions = nx.spring_layout(graph, seed=42, k=max(0.08, 1.7 / np.sqrt(len(graph))))
    edge_x: list[float | None] = []
    edge_y: list[float | None] = []
    for source, target in graph.edges:
        x0, y0 = positions[source]
        x1, y1 = positions[target]
        edge_x.extend([float(x0), float(x1), None])
        edge_y.extend([float(y0), float(y1), None])
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=edge_x,
            y=edge_y,
            mode="lines",
            line={"width": 0.7, "color": "rgba(130,145,170,0.38)"},
            hoverinfo="skip",
            name="Contacts",
        )
    )
    ordered_nodes = list(graph.nodes)
    degrees = [int(degree_lookup.get(node, graph.degree(node))) for node in ordered_nodes]
    figure.add_trace(
        go.Scatter(
            x=[float(positions[node][0]) for node in ordered_nodes],
            y=[float(positions[node][1]) for node in ordered_nodes],
            mode="markers",
            text=[f"{node}<br>Degree: {degree}" for node, degree in zip(ordered_nodes, degrees, strict=True)],
            hovertemplate="%{text}<extra></extra>",
            marker={
                "size": [max(7, min(24, 6 + degree * 1.6)) for degree in degrees],
                "color": degrees,
                "colorscale": "Viridis",
                "showscale": True,
                "colorbar": {"title": "Degree"},
                "line": {"width": 0.7},
            },
            name="Residues",
        )
    )
    figure.update_layout(
        title="Residue contact network",
        height=int(height),
        margin={"l": 10, "r": 10, "t": 50, "b": 10},
        xaxis={"visible": False},
        yaxis={"visible": False},
        hovermode="closest",
        showlegend=False,
        uirevision="biointel-residue-network-v68",
    )
    return figure
