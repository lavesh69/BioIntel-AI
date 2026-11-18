from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.scientific.evidence_lake import ScientificEvidenceLake
from biointel.scientific.provider_hub import OFFICIAL_PROVIDERS, ProviderHub


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Synchronize checksum-bound records from official scientific providers."
    )
    parser.add_argument("provider", choices=["chembl", "uniprot", "clinicaltrials", "rcsb"])
    parser.add_argument("--query", default="kinase")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--pdb-id", default="1CRN")
    args = parser.parse_args()
    hub = ProviderHub(ROOT / "data" / "real_evidence" / "provider_cache")
    lake = ScientificEvidenceLake(ROOT / "reports" / "scientific_evidence.sqlite3")
    info = OFFICIAL_PROVIDERS[args.provider]
    lake.register_provider(
        provider=args.provider,
        official_host=info["host"],
        resource_type="live_sync",
        licence=info["licence"],
        api_url=info["base_url"],
    )
    if args.provider == "chembl":
        payload, snapshot = hub.chembl_activity(
            limit=args.limit, assay_type="B", pchembl_value__gte=5
        )
        records = payload.get("activities", [])
    elif args.provider == "uniprot":
        payload, snapshot = hub.uniprot_search(args.query, size=args.limit)
        records = payload.get("results", [])
    elif args.provider == "clinicaltrials":
        payload, snapshot = hub.clinical_trials(args.query, page_size=args.limit)
        records = payload.get("studies", [])
    else:
        payload, snapshot = hub.rcsb_entry(args.pdb_id)
        records = [payload]
    normalized = []
    for index, record in enumerate(records):
        normalized.append(
            {
                "provider_record_id": str(
                    record.get("activity_id")
                    or record.get("primaryAccession")
                    or record.get("protocolSection", {})
                    .get("identificationModule", {})
                    .get("nctId")
                    or record.get("rcsb_id")
                    or index
                ),
                "entity_type": args.provider,
                "organism": record.get("target_organism"),
                "taxonomy_id": None,
                "assay_type": record.get("standard_type"),
                "target_id": record.get("target_chembl_id"),
                "molecule_id": record.get("molecule_chembl_id"),
                "publication_id": record.get("document_chembl_id"),
                "clinical_trial_id": record.get("protocolSection", {})
                .get("identificationModule", {})
                .get("nctId"),
                "structure_id": record.get("rcsb_id"),
                "value": record.get("standard_value"),
                "unit": record.get("standard_units"),
                "relation": record.get("standard_relation"),
                "confidence_score": record.get("target_confidence_score"),
                "source_url": snapshot.url,
                "payload": record,
            }
        )
    imported = lake.import_snapshot(
        provider=args.provider,
        resource_type="live_sync",
        release=snapshot.last_modified or snapshot.retrieved_at[:10],
        source_url=snapshot.url,
        licence=info["licence"],
        records=normalized,
        retrieved_at=snapshot.retrieved_at,
        review_status="pending",
        metadata={
            "etag": snapshot.etag,
            "source_sha256": snapshot.sha256,
            "content_type": snapshot.content_type,
        },
    )
    print(
        json.dumps(
            {"snapshot": imported.__dict__, "summary": lake.summary()}, indent=2, default=str
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
