from __future__ import annotations

import numpy as np
import pandas as pd

from biointel.structural.pdb_analysis import PROTEIN, ligand_contacts, parse_structure


def ligand_defined_pockets(
    text: str,
    *,
    cutoff: float = 5.0,
    format_hint: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Summarize experimentally occupied ligand pockets without claiming de-novo detection."""
    contacts = pd.DataFrame(
        ligand_contacts(text, cutoff=cutoff, format_hint=format_hint)
    )
    if contacts.empty:
        return (
            pd.DataFrame(
                columns=[
                    "pocket_id",
                    "ligand",
                    "ligand_chain",
                    "ligand_residue_number",
                    "contact_residues",
                    "contact_chains",
                    "minimum_contact_distance",
                    "pocket_basis",
                ]
            ),
            contacts,
        )
    rows = []
    group_columns = ["ligand", "ligand_chain", "ligand_residue_number"]
    for key, group in contacts.groupby(group_columns, dropna=False):
        ligand, ligand_chain, ligand_number = key
        residues = sorted(
            {
                f"{row.chain}:{row.residue}{int(row.residue_number)}"
                for row in group.itertuples(index=False)
            }
        )
        rows.append(
            {
                "pocket_id": f"{ligand}:{ligand_chain}:{ligand_number}",
                "ligand": ligand,
                "ligand_chain": ligand_chain,
                "ligand_residue_number": ligand_number,
                "contact_residues": len(residues),
                "contact_chains": ";".join(sorted(set(group["chain"].astype(str)))),
                "minimum_contact_distance": round(float(group["minimum_distance"].min()), 3),
                "residue_set": ";".join(residues),
                "pocket_basis": "ligand-defined contact shell",
            }
        )
    return pd.DataFrame(rows), contacts


def protein_surface_hotspots(
    text: str,
    *,
    radius: float = 6.0,
    minimum_neighbors: int = 10,
    format_hint: str | None = None,
) -> pd.DataFrame:
    """Return dense protein-residue neighborhoods as a geometry screen, not a docking pocket score."""
    structure = parse_structure(text, format_hint=format_hint)
    residue_centroids: list[tuple[str, int, str, np.ndarray]] = []
    for residue in structure.get_residues():
        name = residue.get_resname().strip().upper()
        if name not in PROTEIN:
            continue
        atoms = [np.asarray(atom.coord, dtype=float) for atom in residue.get_atoms()]
        if not atoms:
            continue
        residue_centroids.append(
            (
                str(residue.get_parent().id),
                int(residue.id[1]),
                name,
                np.mean(np.vstack(atoms), axis=0),
            )
        )
    if not residue_centroids:
        return pd.DataFrame()
    coordinates = np.vstack([item[3] for item in residue_centroids])
    rows = []
    for index, item in enumerate(residue_centroids):
        distances = np.linalg.norm(coordinates - coordinates[index], axis=1)
        neighbors = np.where((distances > 0) & (distances <= float(radius)))[0]
        if len(neighbors) >= int(minimum_neighbors):
            rows.append(
                {
                    "chain": item[0],
                    "residue_number": item[1],
                    "residue": item[2],
                    "neighbor_residues": int(len(neighbors)),
                    "centroid_x": round(float(item[3][0]), 3),
                    "centroid_y": round(float(item[3][1]), 3),
                    "centroid_z": round(float(item[3][2]), 3),
                    "screening_basis": "dense residue-centroid neighborhood",
                    "warning": "Geometry screen only; validate with a dedicated pocket tool.",
                }
            )
    return pd.DataFrame(rows).sort_values("neighbor_residues", ascending=False) if rows else pd.DataFrame()
