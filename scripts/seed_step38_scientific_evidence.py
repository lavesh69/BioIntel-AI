from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.scientific.evidence_lake import ScientificEvidenceLake
from biointel.scientific.provider_hub import OFFICIAL_PROVIDERS


def main() -> int:
    lake = ScientificEvidenceLake(ROOT / "reports" / "scientific_evidence.sqlite3")
    resource_map = {
        "chembl": "bioactivity",
        "uniprot": "protein_sequence",
        "pubchem": "compound_and_bioassay",
        "rcsb": "protein_structure",
        "clinicaltrials": "clinical_trials",
        "clinvar": "clinical_variants",
        "geo": "gene_expression",
        "bindingdb": "binding_affinity",
        "uci": "clinical_reference_dataset",
    }
    for provider, info in OFFICIAL_PROVIDERS.items():
        lake.register_provider(
            provider=provider,
            official_host=info["host"],
            resource_type=resource_map[provider],
            licence=info["licence"],
            api_url=info["base_url"],
            metadata={"official": True, "seed_only": True},
        )

    snapshot_dir = ROOT / "data" / "real_evidence" / "official_snapshots"
    for filename in ("chembl_verified_seed.json", "clinicaltrials_verified_seed.json"):
        payload = json.loads((snapshot_dir / filename).read_text(encoding="utf-8"))
        lake.import_snapshot(
            provider=payload["provider"],
            resource_type=payload["resource_type"],
            release=payload["release"],
            source_url=payload["source_url"],
            licence=payload["licence"],
            records=payload["records"],
            retrieved_at=payload["retrieved_at"],
            review_status="pending",
            metadata={key: value for key, value in payload.items() if key not in {"records"}},
        )

    catalog = json.loads((snapshot_dir / "provider_seed_catalog.json").read_text(encoding="utf-8"))
    grouped: dict[str, list[dict]] = {}
    for row in catalog["records"]:
        grouped.setdefault(row["provider"], []).append(row)
    for provider, rows in grouped.items():
        lake.import_snapshot(
            provider=provider,
            resource_type="official_reference_seed",
            release="verified-reference-2026-07-05",
            source_url=rows[0]["source_url"],
            licence=OFFICIAL_PROVIDERS[provider]["licence"],
            records=rows,
            retrieved_at=catalog["created_at"],
            review_status="pending",
            metadata={"catalog_version": catalog["catalog_version"], "reference_only": True},
        )

    import pandas as pd

    uci_path = ROOT / "data" / "public_reference" / "uci_breast_cancer_wisconsin_diagnostic.csv"
    uci_frame = pd.read_csv(uci_path)
    uci_records = []
    for row in uci_frame.to_dict(orient="records"):
        uci_records.append(
            {
                "provider_record_id": row["sample_id"],
                "entity_type": "clinical_reference_sample",
                "organism": "Homo sapiens",
                "taxonomy_id": 9606,
                "source_url": "https://archive.ics.uci.edu/dataset/17/breast-cancer-wisconsin-diagnostic",
                "diagnosis_label": row["diagnosis_label"],
                "target": int(row["target"]),
                "features": {
                    key: value
                    for key, value in row.items()
                    if key not in {"sample_id", "target", "diagnosis_label"}
                },
            }
        )
    lake.import_snapshot(
        provider="uci",
        resource_type="clinical_reference_dataset",
        release="WDBC-1995-CC-BY-4.0",
        source_url="https://archive.ics.uci.edu/dataset/17/breast-cancer-wisconsin-diagnostic",
        licence="CC BY 4.0",
        records=uci_records,
        retrieved_at="2026-07-05T00:00:00Z",
        review_status="approved",
        metadata={
            "doi": "10.24432/C5DW2B",
            "instances": 569,
            "features": 30,
            "release_eligible_for_dti": False,
        },
    )

    print(json.dumps({"summary": lake.summary(), "integrity": lake.verify_integrity()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
