from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel import __version__
from biointel.api.security_store import ApiSecurityStore
from biointel.data.relationship_integrity import relationship_summary
from biointel.database.integrity_guards import install_integrity_guards
from biointel.genomics.fastq import fastq_qc, paired_end_qc, parse_fastq
from biointel.genomics.variants import genotype_matrix, parse_vcf, variant_summary
from biointel.integrations.public_sync import sync_status
from biointel.intelligence.data_intelligence import all_database_health
from biointel.jobs.local_queue import LocalJobQueue
from biointel.training.model_artifact import load_model_artifact
from biointel.ui.navigation import PAGE_CATALOG
from biointel.utils.exceptions import FeatureSchemaMismatchError


def main() -> None:
    assert __version__ == (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    pages = [ROOT / "app.py", *sorted((ROOT / "pages").glob("*.py"))]
    assert len(pages) >= 71
    for page in pages:
        source = page.read_text(encoding="utf-8")
        compile(source, str(page), "exec")
        assert "st.json(" not in source
        assert "st.title(" not in source
        if page.name != "app.py":
            assert "st.set_page_config(" in source
            assert source.index("st.set_page_config(") < source.index("apply_theme()")
        assert "hero(" in source
    assert len(PAGE_CATALOG) >= 71

    health = all_database_health(ROOT)
    assert health["database_count"] >= 13
    assert health["healthy_count"] == health["database_count"]
    assert health["health_percent"] == 100.0

    guards = install_integrity_guards(ROOT)
    assert len(guards) == 5
    assert all(
        result.integrity == "ok" and result.foreign_key_findings == 0 for result in guards.values()
    )

    relationships = relationship_summary(ROOT)
    assert relationships["broken_edges"] == 0
    assert relationships["orphan_findings"] == 0

    security = ApiSecurityStore(ROOT / "reports" / "api_security.sqlite3")
    assert security.status()["error_count"] == 0

    queue = LocalJobQueue(ROOT / "reports" / "jobs.sqlite3")
    orchestration = queue.orchestration_summary()
    assert orchestration["jobs"] >= 120
    assert orchestration["workers"] >= 1

    sync = sync_status(ROOT)
    assert "normalized_records" in sync and "runs" in sync

    r1 = parse_fastq("@pair/1\nACGTACGT\n+\nIIIIIIII\n")
    r2 = parse_fastq("@pair/2\nTGCATGCA\n+\nIIIIIIII\n")
    assert fastq_qc(r1).q30_percent == 100.0
    assert paired_end_qc(r1, r2).synchronized_pairs == 1

    vcf = parse_vcf(
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tS1\n"
        "1\t10\t.\tA\tG\t50\tPASS\tDP=20;AF=0.1\tGT:DP\t0/1:20\n"
    )
    summary = variant_summary(vcf)
    assert summary.snps == 1 and summary.samples == 1 and summary.mean_depth == 20.0
    assert genotype_matrix(vcf).iloc[0]["S1"] == "0/1"

    models = sorted((ROOT / "models").glob("*.joblib"))
    compatible_models = 0
    for model in models:
        try:
            load_model_artifact(model, trusted_root=ROOT / "models")
            compatible_models += 1
        except FeatureSchemaMismatchError:
            # Public-reference benchmark artifacts can coexist with the native
            # BioIntel artifact schema but are not counted as deployable DTI models.
            continue
    assert compatible_models >= 23

    required = [
        ROOT / "reports" / "generated" / "step33_platform_summary.json",
        ROOT / "requirements-production.txt",
        ROOT / "docker-compose.production.yml",
        ROOT / "Dockerfile.production",
        ROOT / "config" / "production.example.env",
        ROOT / "BUILD_STEP33_PLATFORM_WINDOWS.bat",
        ROOT / "VERIFY_STEP33_WINDOWS.bat",
        ROOT / "RUN_PRODUCTION_STACK_WINDOWS.bat",
        ROOT / "RUN_LOCAL_WORKER_WINDOWS.bat",
        ROOT / "scripts" / "run_local_worker.py",
        ROOT / "docs" / "STEP33_PRODUCTION_SCIENTIFIC_PLATFORM.md",
    ]
    assert all(path.is_file() for path in required)

    payload = {
        "version": __version__,
        "screens": len(pages),
        "databases": health["database_count"],
        "healthy_databases": health["healthy_count"],
        "models": len(models),
        "relationship_broken_edges": relationships["broken_edges"],
        "job_orchestration": orchestration,
        "scientific_sync_records": sync["normalized_records"],
        "scientific_boundary": "Bundled models remain synthetic/reference and scientific release remains evidence-gated.",
    }
    output = ROOT / "reports" / "generated" / "step33_verification_summary.json"
    output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    print("Step 33 production scientific platform verification passed")


if __name__ == "__main__":
    main()
