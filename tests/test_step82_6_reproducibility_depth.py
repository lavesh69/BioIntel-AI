from __future__ import annotations

import hashlib
import json
from pathlib import Path

from biointel.scientific.reproducibility_depth import assess_reproducibility_depth

ROOT = Path(__file__).resolve().parents[1]


def test_catalog_adds_official_multisite_single_cell_and_proteomics_evidence() -> None:
    catalog = json.loads((ROOT / "data/real_scientific_pack/catalog.json").read_text(encoding="utf-8"))
    assert catalog["software_version"] == "8.2.6"
    ids = {item["id"] for item in catalog["datasets"]}
    assert {
        "maqc_gse5350_multisite",
        "cptac_phase1_multisite",
        "pxd002114_multilab_qc",
        "tenx_pbmc3k_reference",
    }.issubset(ids)
    for item in catalog["datasets"]:
        for metadata in item["file_metadata"]:
            path = ROOT / metadata["path"]
            assert path.is_file()
            assert hashlib.sha256(path.read_bytes()).hexdigest() == metadata["sha256"]


def test_reproducibility_scores_separate_implementation_from_real_outcomes() -> None:
    scores = {item.area: item for item in assess_reproducibility_depth(ROOT)}
    assert scores["Multi-site reproducibility"].implementation_score == 10.0
    assert scores["Single-cell depth"].implementation_score == 10.0
    assert scores["Proteomics depth"].implementation_score == 10.0
    assert scores["Prospective wet-lab validation"].implementation_score == 10.0
    assert scores["Prospective wet-lab validation"].evidence_score == 3.0


def test_prospective_site_pack_contains_no_fabricated_outcomes() -> None:
    base = ROOT / "data/prospective_validation_site_pack"
    assert (base / "BioIntel_Prospective_Validation_Site_Pack.zip").is_file()
    outcome = (base / "blinded_outcome_import.csv").read_text(encoding="utf-8").splitlines()
    assert len(outcome) == 1
    assert "observed_value" in outcome[0]
    assert "contains no fabricated laboratory outcomes" in (base / "README.md").read_text(encoding="utf-8")


def test_ui_exposes_evidence_level_and_site_pack() -> None:
    source = (ROOT / "src/biointel/ui/starter_kits.py").read_text(encoding="utf-8")
    assert "Evidence level" in source
    assert "Prospective Validation Site Pack" in source
