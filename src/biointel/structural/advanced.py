from __future__ import annotations

import math
import re
from collections import Counter

import numpy as np
import pandas as pd
from Bio.PDB import NeighborSearch, PPBuilder, ShrakeRupley

from biointel.structural.pdb_analysis import PROTEIN, parse_structure

BACKBONE_ATOMS = {"N", "CA", "C", "O"}


def experimental_metadata(text: str, *, format_hint: str | None = None) -> dict[str, object]:
    text = str(text)
    metadata: dict[str, object] = {
        "format": "mmCIF"
        if str(format_hint or "").lower() in {"cif", "mmcif"} or text.lstrip().startswith("data_")
        else "PDB",
        "experimental_method": None,
        "resolution_angstrom": None,
        "r_work": None,
        "r_free": None,
    }
    patterns = [
        ("experimental_method", r"EXPDTA\s+(.+)", r"_exptl\.method\s+['\"]?([^\n'\"]+)"),
        (
            "resolution_angstrom",
            r"RESOLUTION\.\s+([0-9.]+)\s+ANGSTROMS",
            r"_refine\.ls_d_res_high\s+([0-9.]+)",
        ),
        (
            "r_work",
            r"R VALUE\s+\(WORKING SET\)\s*:\s*([0-9.]+)",
            r"_refine\.ls_R_factor_R_work\s+([0-9.]+)",
        ),
        ("r_free", r"FREE R VALUE\s*:\s*([0-9.]+)", r"_refine\.ls_R_factor_R_free\s+([0-9.]+)"),
    ]
    for key, pdb_pattern, cif_pattern in patterns:
        match = re.search(
            cif_pattern if metadata["format"] == "mmCIF" else pdb_pattern, text, flags=re.IGNORECASE
        )
        if match:
            value = match.group(1).strip()
            if key != "experimental_method":
                try:
                    value = float(value)
                except ValueError:
                    pass
            metadata[key] = value
    return metadata


def structure_quality_report(
    text: str, *, format_hint: str | None = None
) -> tuple[pd.DataFrame, dict[str, object]]:
    structure = parse_structure(text, format_hint=format_hint)
    residue_rows = []
    altloc_atoms = 0
    zero_occupancy = 0
    atoms = list(structure.get_atoms())
    b_factors = []
    occupancies = []
    for residue in structure.get_residues():
        name = residue.get_resname().strip().upper()
        if name not in PROTEIN:
            continue
        atom_names = {atom.get_name().strip() for atom in residue}
        missing = sorted(BACKBONE_ATOMS - atom_names)
        residue_atoms = list(residue)
        residue_b = [float(atom.get_bfactor()) for atom in residue_atoms]
        residue_occ = [
            float(atom.get_occupancy()) if atom.get_occupancy() is not None else np.nan
            for atom in residue_atoms
        ]
        for atom in residue_atoms:
            if atom.get_altloc().strip():
                altloc_atoms += 1
            occupancy = atom.get_occupancy()
            if occupancy is not None and float(occupancy) <= 0:
                zero_occupancy += 1
        b_factors.extend(residue_b)
        occupancies.extend([value for value in residue_occ if np.isfinite(value)])
        residue_rows.append(
            {
                "chain": residue.get_parent().id,
                "residue_number": residue.id[1],
                "insertion_code": residue.id[2].strip(),
                "residue": name,
                "missing_backbone_atoms": ", ".join(missing),
                "backbone_complete": not missing,
                "mean_b_factor": float(np.mean(residue_b)) if residue_b else np.nan,
                "minimum_occupancy": float(np.nanmin(residue_occ))
                if np.isfinite(residue_occ).any()
                else np.nan,
            }
        )
    residue_table = pd.DataFrame(residue_rows)
    chain_breaks = 0
    for chain in structure.get_chains():
        previous_ca = None
        for residue in chain:
            if residue.get_resname().strip().upper() not in PROTEIN or "CA" not in residue:
                continue
            current = residue["CA"].coord
            if previous_ca is not None and np.linalg.norm(current - previous_ca) > 4.5:
                chain_breaks += 1
            previous_ca = current
    metadata = experimental_metadata(text, format_hint=format_hint)
    summary = {
        **metadata,
        "atoms": len(atoms),
        "protein_residues": len(residue_table),
        "incomplete_backbone_residues": int((~residue_table["backbone_complete"]).sum())
        if not residue_table.empty
        else 0,
        "alternate_location_atoms": altloc_atoms,
        "zero_occupancy_atoms": zero_occupancy,
        "mean_b_factor": float(np.mean(b_factors)) if b_factors else None,
        "median_b_factor": float(np.median(b_factors)) if b_factors else None,
        "mean_occupancy": float(np.mean(occupancies)) if occupancies else None,
        "chain_break_candidates": chain_breaks,
    }
    return residue_table, summary


def ramachandran_table(text: str, *, format_hint: str | None = None) -> pd.DataFrame:
    structure = parse_structure(text, format_hint=format_hint)
    rows = []
    builder = PPBuilder()
    for model in structure:
        for chain in model:
            for peptide in builder.build_peptides(chain):
                residues = list(peptide)
                for residue, (phi, psi) in zip(residues, peptide.get_phi_psi_list()):
                    phi_degrees = math.degrees(phi) if phi is not None else np.nan
                    psi_degrees = math.degrees(psi) if psi is not None else np.nan
                    if np.isfinite(phi_degrees) and np.isfinite(psi_degrees):
                        if -160 <= phi_degrees <= -20 and -90 <= psi_degrees <= 45:
                            region = "alpha"
                        elif -180 <= phi_degrees <= -40 and 45 <= psi_degrees <= 180:
                            region = "beta"
                        elif 20 <= phi_degrees <= 120 and -100 <= psi_degrees <= 100:
                            region = "left-handed"
                        else:
                            region = "other/review"
                    else:
                        region = "terminal/unavailable"
                    rows.append(
                        {
                            "chain": chain.id,
                            "residue_number": residue.id[1],
                            "residue": residue.get_resname().strip().upper(),
                            "phi": phi_degrees,
                            "psi": psi_degrees,
                            "region": region,
                        }
                    )
    return pd.DataFrame(
        rows, columns=["chain", "residue_number", "residue", "phi", "psi", "region"]
    )


def solvent_accessibility(
    text: str, *, format_hint: str | None = None
) -> tuple[pd.DataFrame, pd.DataFrame]:
    structure = parse_structure(text, format_hint=format_hint)
    ShrakeRupley().compute(structure, level="R")
    rows = []
    for residue in structure.get_residues():
        name = residue.get_resname().strip().upper()
        if name not in PROTEIN:
            continue
        sasa = float(getattr(residue, "sasa", 0.0))
        rows.append(
            {
                "chain": residue.get_parent().id,
                "residue_number": residue.id[1],
                "residue": name,
                "sasa": sasa,
                "exposure_class": "exposed"
                if sasa >= 50
                else "intermediate"
                if sasa >= 20
                else "buried",
            }
        )
    table = pd.DataFrame(rows)
    chain_summary = (
        table.groupby("chain", as_index=False).agg(
            total_sasa=("sasa", "sum"),
            mean_residue_sasa=("sasa", "mean"),
            residues=("residue", "size"),
        )
        if not table.empty
        else pd.DataFrame(columns=["chain", "total_sasa", "mean_residue_sasa", "residues"])
    )
    return table, chain_summary


def chain_interface_contacts(
    text: str,
    *,
    cutoff: float = 5.0,
    format_hint: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    structure = parse_structure(text, format_hint=format_hint)
    protein_atoms = [
        atom
        for atom in structure.get_atoms()
        if atom.get_parent().get_resname().strip().upper() in PROTEIN
    ]
    search = NeighborSearch(protein_atoms)
    contacts: dict[tuple[str, int, str, int], float] = {}
    for atom in protein_atoms:
        residue = atom.get_parent()
        chain = residue.get_parent().id
        for neighbour in search.search(atom.coord, cutoff, level="A"):
            other_residue = neighbour.get_parent()
            other_chain = other_residue.get_parent().id
            if chain == other_chain:
                continue
            pair = sorted(
                [(str(chain), int(residue.id[1])), (str(other_chain), int(other_residue.id[1]))]
            )
            key = (pair[0][0], pair[0][1], pair[1][0], pair[1][1])
            distance = float(np.linalg.norm(atom.coord - neighbour.coord))
            contacts[key] = min(distance, contacts.get(key, float("inf")))
    rows = [
        {
            "chain_a": key[0],
            "residue_a": key[1],
            "chain_b": key[2],
            "residue_b": key[3],
            "minimum_distance": value,
        }
        for key, value in contacts.items()
    ]
    table = pd.DataFrame(
        rows, columns=["chain_a", "residue_a", "chain_b", "residue_b", "minimum_distance"]
    )
    if table.empty:
        summary = pd.DataFrame(columns=["interface", "residue_contacts", "minimum_distance"])
    else:
        table["interface"] = table["chain_a"] + "–" + table["chain_b"]
        summary = table.groupby("interface", as_index=False).agg(
            residue_contacts=("minimum_distance", "size"),
            minimum_distance=("minimum_distance", "min"),
        )
    return table, summary


def residue_contact_network(
    text: str,
    *,
    cutoff: float = 8.0,
    format_hint: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    structure = parse_structure(text, format_hint=format_hint)
    ca_atoms = []
    for residue in structure.get_residues():
        if residue.get_resname().strip().upper() in PROTEIN and "CA" in residue:
            ca_atoms.append(residue["CA"])
    search = NeighborSearch(ca_atoms)
    edges = set()
    for atom in ca_atoms:
        residue = atom.get_parent()
        node = f"{residue.get_parent().id}:{residue.id[1]}:{residue.get_resname().strip()}"
        for neighbour in search.search(atom.coord, cutoff, level="A"):
            other = neighbour.get_parent()
            other_node = f"{other.get_parent().id}:{other.id[1]}:{other.get_resname().strip()}"
            if node != other_node:
                edges.add(tuple(sorted((node, other_node))))
    edge_table = pd.DataFrame(edges, columns=["source", "target"])
    degree = Counter()
    for left, right in edges:
        degree[left] += 1
        degree[right] += 1
    node_table = (
        pd.DataFrame(
            [
                {"node": node, "degree": value, "hub_candidate": value >= 8}
                for node, value in degree.items()
            ]
        ).sort_values("degree", ascending=False)
        if degree
        else pd.DataFrame(columns=["node", "degree", "hub_candidate"])
    )
    return edge_table, node_table
