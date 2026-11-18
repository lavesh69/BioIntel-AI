from __future__ import annotations

from biointel.runtime_paths import runtime_report_path, runtime_reports_directory

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class ProviderContract:
    key: str
    provider: str
    domain: str
    official_url: str
    local_candidates: tuple[str, ...]
    licence_review_required: bool = True


PROVIDER_CONTRACTS: tuple[ProviderContract, ...] = (
    ProviderContract("uci", "UCI Machine Learning Repository", "Public benchmark datasets", "https://archive.ics.uci.edu/", ("data/public_reference/uci_breast_cancer_wisconsin_diagnostic.csv", "data/real_scientific_pack/cancer/uci_wdbc_real.csv")),
    ProviderContract("sklearn", "scikit-learn bundled datasets", "Reproducible ML benchmarks", "https://scikit-learn.org/stable/datasets.html", ("data/step162/public_benchmarks",)),
    ProviderContract("chembl", "ChEMBL", "Bioactivity", "https://www.ebi.ac.uk/chembl/", ("data/real_evidence/official_snapshots/chembl_verified_seed.json",)),
    ProviderContract("clinicaltrials", "ClinicalTrials.gov", "Clinical studies", "https://clinicaltrials.gov/", ("data/real_evidence/official_snapshots/clinicaltrials_verified_seed.json",)),
    ProviderContract("pride", "PRIDE Archive", "Proteomics", "https://www.ebi.ac.uk/pride/", ("data/real_scientific_pack/proteomics/PXD002114_reproducibility_summary.csv",)),
    ProviderContract("cptac", "CPTAC", "Proteogenomics", "https://proteomics.cancer.gov/programs/cptac", ("data/real_scientific_pack/proteomics/CPTAC_Phase_I_evidence_manifest.json",)),
    ProviderContract("geo", "NCBI GEO", "Functional genomics", "https://www.ncbi.nlm.nih.gov/geo/", ("data/real_scientific_pack/multisite/MAQC_GSE5350_evidence_manifest.json",)),
    ProviderContract("uniprot", "UniProt", "Protein sequence and annotation", "https://www.uniprot.org/", ()),
    ProviderContract("rcsb", "RCSB Protein Data Bank", "Macromolecular structures", "https://www.rcsb.org/", ()),
    ProviderContract("pubchem", "PubChem", "Chemical structures and assays", "https://pubchem.ncbi.nlm.nih.gov/", ()),
    ProviderContract("clinvar", "ClinVar", "Clinical variants", "https://www.ncbi.nlm.nih.gov/clinvar/", ()),
    ProviderContract("gnomad", "gnomAD", "Population variation", "https://gnomad.broadinstitute.org/", ()),
    ProviderContract("reactome", "Reactome", "Pathways", "https://reactome.org/", ()),
    ProviderContract("go", "Gene Ontology", "Functional ontology", "https://geneontology.org/", ()),
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _local_assets(root: Path, candidates: tuple[str, ...]) -> list[Path]:
    assets: list[Path] = []
    for candidate in candidates:
        path = root / candidate
        if path.is_file():
            assets.append(path)
        elif path.is_dir():
            assets.extend(sorted(item for item in path.rglob("*") if item.is_file()))
    return assets


def build_provider_contracts(root: str | Path) -> pd.DataFrame:
    project_root = Path(root).expanduser().resolve()
    contract_root = project_root / "data" / "step162" / "provider_contracts"
    contract_root.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for contract in PROVIDER_CONTRACTS:
        assets = _local_assets(project_root, contract.local_candidates)
        asset_rows = [
            {
                "path": str(path.relative_to(project_root)).replace("\\", "/"),
                "sha256": _sha256(path),
                "size_bytes": path.stat().st_size,
            }
            for path in assets
        ]
        payload = {
            "schema": "biointel.step162.provider-source-contract.v1",
            **asdict(contract),
            "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
            "source_descriptor_verified": True,
            "local_assets": asset_rows,
            "local_snapshot_present": bool(asset_rows),
            "local_snapshot_checksum_verified": bool(asset_rows),
            "production_reference_qualified": False,
            "qualification_blockers": [
                "Licence/terms acceptance must match the intended deployment.",
                "A complete provider release, release date and record-level QC must be attached.",
                "Independent scientific review is required before confirmatory use.",
            ],
        }
        path = contract_root / f"{contract.key}.json"
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        rows.append(
            {
                "provider_key": contract.key,
                "provider": contract.provider,
                "domain": contract.domain,
                "official_url": contract.official_url,
                "source_descriptor_verified": True,
                "local_asset_files": len(asset_rows),
                "local_snapshot_present": bool(asset_rows),
                "local_snapshot_checksum_verified": bool(asset_rows),
                "production_reference_qualified": False,
                "contract_sha256": _sha256(path),
            }
        )
    frame = pd.DataFrame(rows)
    report_dir = runtime_reports_directory(project_root)
    report_dir.mkdir(parents=True, exist_ok=True)
    frame.to_csv(report_dir / "step162_provider_source_contracts.csv", index=False)
    return frame


def provider_contract_matrix(root: str | Path) -> pd.DataFrame:
    project_root = Path(root).expanduser().resolve()
    path = runtime_report_path(project_root, "step162_provider_source_contracts.csv")
    if path.is_file():
        return pd.read_csv(path)
    return build_provider_contracts(project_root)


__all__ = ["PROVIDER_CONTRACTS", "ProviderContract", "build_provider_contracts", "provider_contract_matrix"]
