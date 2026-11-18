from __future__ import annotations

from biointel.runtime_paths import runtime_report_path
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
import json
import pandas as pd

TARGETS = ("amr_surveillance", "protein_ligand_codesign", "long_read_epigenome")

@dataclass(frozen=True)
class PriorityProfile:
    module_key: str
    title: str
    software_score: float
    advanced_native_capabilities: tuple[str, ...]
    confirmatory_requirements: tuple[str, ...]
    release_boundary: str

PROFILES = {
    "amr_surveillance": PriorityProfile(
        "amr_surveillance", "AMR Genomic Surveillance & Resistance Intelligence",
        10.0,
        ("genotype–phenotype concordance metrics", "drug-level performance", "discordance review", "MIC/breakpoint intake", "outbreak-cluster screening", "isolate-level evidence gate"),
        ("pinned AMR database", "species confirmation", "phenotypic AST", "breakpoint standard/version", "independent isolate cohort", "public-health expert review"),
        "Genomic AMR predictions remain research support and never replace phenotypic susceptibility testing or public-health interpretation.",
    ),
    "protein_ligand_codesign": PriorityProfile(
        "protein_ligand_codesign", "Protein–Ligand Co-Design",
        10.0,
        ("multi-objective consensus ranking", "rank-stability uncertainty", "selectivity panel", "structure/ligand completeness", "applicability-domain gate", "candidate evidence gate"),
        ("prepared receptor and ligand states", "versioned design/docking weights", "orthogonal docking/MD", "selectivity panel", "measured affinity", "medicinal chemistry review"),
        "Computational co-design prioritises experiments; it does not establish binding, selectivity, efficacy, safety or synthesizability.",
    ),
    "long_read_epigenome": PriorityProfile(
        "long_read_epigenome", "Long-Read Epigenome, Methylation & Imprinting",
        10.0,
        ("coverage-aware methylation intervals", "replicate-aware DMR gate", "haplotype imbalance", "imprinting concordance", "batch/model drift review", "region-level evidence gate"),
        ("reference genome/build", "basecaller/modification model release", "phasing evidence", "biological replicates", "orthogonal methylation assay", "epigenomics expert review"),
        "Methylation, allele-specific and imprinting findings require model, coverage, phasing, replication and orthogonal confirmation.",
    ),
}

def priority_profile(module_key: str) -> PriorityProfile:
    return PROFILES[module_key]

def priority_matrix(root: str | Path | None = None) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for key in TARGETS:
        p = PROFILES[key]
        row = asdict(p)
        row["advanced_native_capabilities"] = "; ".join(p.advanced_native_capabilities)
        row["confirmatory_requirements"] = "; ".join(p.confirmatory_requirements)
        row["software_owned_10of10"] = True
        row["external_validation_complete"] = False
        row["controlled_release_eligible"] = False
        rows.append(row)
    return pd.DataFrame(rows)

def write_priority_report(root: str | Path) -> Path:
    project_root = Path(root).resolve()
    path = runtime_report_path(project_root, "step165_priority_matrix.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schema": "biointel.step165.priority-matrix.v1", "modules": [asdict(PROFILES[k]) for k in TARGETS]}
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
