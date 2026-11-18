from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.scientific.validation_depth import (
    ValidationEvidenceRegistry,
    sha256_file,
    sha256_text,
)


def main() -> int:
    target = ROOT / "reports" / "validation_evidence.sqlite3"
    if target.exists():
        target.unlink()
    registry = ValidationEvidenceRegistry(target)
    releases = [
        (
            "chembl",
            "verified-reference-seed-2026-07-05",
            "https://www.ebi.ac.uk/chembl/api/data/docs",
            ROOT / "data/real_evidence/official_snapshots/chembl_verified_seed.json",
            "CC BY-SA 3.0 / provider terms",
        ),
        (
            "clinicaltrials",
            "verified-reference-seed-2026-07-05",
            "https://clinicaltrials.gov/data-api/about-api",
            ROOT / "data/real_evidence/official_snapshots/clinicaltrials_verified_seed.json",
            "Public domain / provider terms",
        ),
        (
            "uci",
            "wdbc-benchmark-2026-07-05",
            "https://archive.ics.uci.edu/dataset/17/breast+cancer+wisconsin+diagnostic",
            ROOT / "reports/step38/uci_wdbc_real_benchmark.json",
            "CC BY 4.0",
        ),
    ]
    for provider, release, url, file_path, licence in releases:
        registry.register_provider_release(
            provider=provider,
            release_id=release,
            source_url=url,
            retrieved_at="2026-07-05T00:00:00+00:00",
            dataset_sha256=sha256_file(file_path),
            record_count=1,
            licence=licence,
            verified=True,
        )

    # Register honest protocol-ready records. They demonstrate readiness but cannot inflate completed evidence.
    dataset_hash = sha256_file(
        ROOT / "data/real_evidence/official_snapshots/chembl_verified_seed.json"
    )
    model_hash = sha256_file(ROOT / "models/packv5_5x_classification_extra_trees.joblib")
    common = {
        "domain": "dti",
        "study_type": "validation",
        "status": "registered",
        "sponsor_organization": "biointel-reference",
        "coordinator_organization": "biointel-reference",
        "source_provider": "chembl",
        "training_provider": "synthetic_reference",
        "dataset_sha256": dataset_hash,
        "model_sha256": model_hash,
        "protocol_sha256": sha256_text("step40 protocol-ready external DTI template"),
        "manifest_sha256": sha256_text("step40 immutable validation template manifest"),
        "preregistered_at": "2026-07-05T00:00:00+00:00",
        "locked_at": None,
        "completed_at": None,
        "blinded": False,
        "analytical_only": True,
    }
    registry.register_study(
        payload={
            **common,
            "study_id": "STEP40-EXT-DTI-PROTOCOL",
            "title": "Independent external DTI protocol",
            "evidence_class": "independent_external_analytical",
        }
    )
    registry.register_study(
        payload={
            **common,
            "study_id": "STEP40-PROSPECTIVE-PROTOCOL",
            "title": "Blinded prospective DTI protocol",
            "evidence_class": "prospective_blinded_analytical",
            "blinded": True,
        }
    )
    registry.register_study(
        payload={
            **common,
            "study_id": "STEP40-WETLAB-MULTISITE-PROTOCOL",
            "title": "Multi-site wet-lab replication protocol",
            "evidence_class": "wet_lab_multisite",
            "blinded": True,
            "analytical_only": False,
        }
    )

    output = {"summary": registry.summary(), "integrity": registry.verify_integrity()}
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
