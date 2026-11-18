from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class EvidenceDimension:
    area: str
    implementation_score: float
    evidence_score: float
    status: str
    boundary: str


def _catalog(root: Path) -> dict[str, Any]:
    return json.loads((root / "data/real_scientific_pack/catalog.json").read_text(encoding="utf-8"))


def assess_reproducibility_depth(root: Path) -> list[EvidenceDimension]:
    catalog = _catalog(root)
    ids = {item.get("id") for item in catalog.get("datasets", [])}
    required_multisite = {"maqc_gse5350_multisite", "cptac_phase1_multisite", "pxd002114_multilab_qc"}
    multisite_ready = required_multisite.issubset(ids)
    single_cell_ready = "tenx_pbmc3k_reference" in ids
    site_pack_ready = (root / "data/prospective_validation_site_pack/BioIntel_Prospective_Validation_Site_Pack.zip").is_file()
    return [
        EvidenceDimension(
            area="Multi-site reproducibility",
            implementation_score=10.0 if multisite_ready else 6.0,
            evidence_score=8.5 if multisite_ready else 5.5,
            status="official retrospective multi-site benchmarks integrated" if multisite_ready else "incomplete",
            boundary="The public studies are genuine multi-site evidence, but they are not new independent replications of every BioIntel module.",
        ),
        EvidenceDimension(
            area="Single-cell depth",
            implementation_score=10.0 if single_cell_ready else 7.0,
            evidence_score=8.3 if single_cell_ready else 7.2,
            status="official PBMC3k study manifest and reproducible QC reference integrated" if single_cell_ready else "incomplete",
            boundary="The bundled payload is study metadata/QC reference, not a full multi-donor clinical cohort.",
        ),
        EvidenceDimension(
            area="Proteomics depth",
            implementation_score=10.0 if multisite_ready else 7.0,
            evidence_score=8.7 if multisite_ready else 7.2,
            status="CPTAC and ProteomeXchange multi-laboratory benchmarks integrated" if multisite_ready else "incomplete",
            boundary="Raw spectra remain in official repositories; local files are verified study indices and evidence manifests.",
        ),
        EvidenceDimension(
            area="Prospective wet-lab validation",
            implementation_score=10.0 if site_pack_ready else 5.0,
            evidence_score=3.0,
            status="site-ready locked/blinded validation workflow" if site_pack_ready else "incomplete",
            boundary="Completed independent outcomes cannot be created by software and remain absent until real laboratories return signed results.",
        ),
    ]
