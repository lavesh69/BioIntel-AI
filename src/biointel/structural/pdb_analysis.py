from __future__ import annotations

from dataclasses import asdict, dataclass
from io import StringIO

import numpy as np
from Bio.PDB import MMCIFParser, NeighborSearch, PDBParser


@dataclass(frozen=True)
class StructureSummary:
    models: int
    chains: int
    residues: int
    atoms: int
    protein_residues: int
    nucleic_residues: int
    waters: int
    ligands: dict[str, int]
    chain_lengths: dict[str, int]
    centroid: tuple[float, float, float]
    radius_of_gyration: float


PROTEIN = {
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
NUCLEIC = {"A", "C", "G", "U", "DA", "DC", "DG", "DT"}


def parse_structure(
    text: str,
    *,
    format_hint: str | None = None,
    maximum_text_bytes: int = 25 * 1024 * 1024,
    maximum_atoms: int = 2_000_000,
):
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Structure text is empty.")
    if "\x00" in text:
        raise ValueError("Structure text contains null bytes.")
    encoded_size = len(text.encode("utf-8", errors="replace"))
    if encoded_size > int(maximum_text_bytes):
        raise ValueError(
            f"Structure text is {encoded_size / (1024 * 1024):.1f} MB; "
            "reduce the file or use the external large-structure workflow."
        )
    hint = str(format_hint or "").lower()
    looks_like_cif = hint in {"cif", "mmcif"} or text.lstrip().startswith("data_")
    parser = MMCIFParser(QUIET=True) if looks_like_cif else PDBParser(QUIET=True)
    format_name = "mmCIF" if looks_like_cif else "PDB"
    try:
        structure = parser.get_structure("biointel", StringIO(text))
    except Exception as exc:
        raise ValueError(f"Could not parse {format_name}: {exc}") from exc
    atoms = list(structure.get_atoms())
    if not atoms:
        raise ValueError(f"Parsed {format_name} contains no atoms.")
    if len(atoms) > int(maximum_atoms):
        raise ValueError(
            f"Parsed structure contains {len(atoms):,} atoms; the interactive limit is {int(maximum_atoms):,}."
        )
    coordinates = np.asarray([atom.coord for atom in atoms], dtype=float)
    if not np.all(np.isfinite(coordinates)):
        raise ValueError("Structure contains non-finite atomic coordinates.")
    return structure


def parse_pdb(text: str):
    """Backward-compatible PDB parser entry point."""
    return parse_structure(text, format_hint="pdb")


def structure_summary(text: str, *, format_hint: str | None = None) -> StructureSummary:
    structure = parse_structure(text, format_hint=format_hint)
    models = list(structure)
    chains = list(structure.get_chains())
    residues = list(structure.get_residues())
    atoms = list(structure.get_atoms())
    if not atoms:
        raise ValueError("PDB contains no atoms.")
    coords = np.array([atom.coord for atom in atoms], dtype=float)
    centroid = coords.mean(axis=0)
    rg = float(np.sqrt(((coords - centroid) ** 2).sum(axis=1).mean()))
    ligands = {}
    waters = protein = nucleic = 0
    lengths = {}
    for chain in chains:
        length = 0
        for residue in chain:
            name = residue.get_resname().strip().upper()
            het = residue.id[0]
            if name in PROTEIN:
                protein += 1
                length += 1
            elif name in NUCLEIC:
                nucleic += 1
                length += 1
            elif name in {"HOH", "WAT"}:
                waters += 1
            elif het.strip():
                ligands[name] = ligands.get(name, 0) + 1
        lengths[chain.id] = length
    return StructureSummary(
        len(models),
        len(chains),
        len(residues),
        len(atoms),
        protein,
        nucleic,
        waters,
        ligands,
        lengths,
        tuple(round(float(x), 3) for x in centroid),
        round(rg, 3),
    )


def ligand_contacts(
    text: str,
    *,
    cutoff: float = 4.0,
    format_hint: str | None = None,
) -> list[dict]:
    structure = parse_structure(text, format_hint=format_hint)
    atoms = list(structure.get_atoms())
    ligand_atoms = [
        a
        for a in atoms
        if a.get_parent().get_resname().strip().upper() not in PROTEIN | NUCLEIC | {"HOH", "WAT"}
        and a.get_parent().id[0].strip()
    ]
    protein_atoms = [a for a in atoms if a.get_parent().get_resname().strip().upper() in PROTEIN]
    contacts = {}
    neighbour_search = NeighborSearch(protein_atoms) if protein_atoms else None
    for ligand in ligand_atoms:
        nearby = neighbour_search.search(ligand.coord, float(cutoff), level="A") if neighbour_search else []
        for atom in nearby:
            distance = float(np.linalg.norm(ligand.coord - atom.coord))
            residue = atom.get_parent()
            chain = residue.get_parent().id
            ligand_residue = ligand.get_parent()
            key = (
                chain,
                residue.id[1],
                residue.get_resname(),
                ligand_residue.get_resname(),
                ligand_residue.get_parent().id,
                ligand_residue.id[1],
            )
            contacts[key] = min(distance, contacts.get(key, 999))
    return [
        {
            "chain": k[0],
            "residue_number": k[1],
            "residue": k[2],
            "ligand": k[3],
            "ligand_chain": k[4],
            "ligand_residue_number": k[5],
            "minimum_distance": round(v, 3),
        }
        for k, v in sorted(contacts.items())
    ]


def summary_dict(result):
    return asdict(result)
