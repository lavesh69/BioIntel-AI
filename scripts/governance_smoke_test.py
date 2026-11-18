from __future__ import annotations

import tempfile
from datetime import date, timedelta
from pathlib import Path

from biointel.governance.governance_registry import (
    create_decision,
    create_milestone,
    upsert_gate,
)
from biointel.governance.reproducibility import (
    build_project_evidence_package,
    inspect_project_evidence_package,
    project_readiness,
)
from biointel.portfolio.project_registry import create_project
from biointel.utils.audit_log import verify_audit_chain


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="biointel-governance-") as temporary:
        root = Path(temporary)
        for relative in (
            "models",
            "reports",
            "config",
            "cache/external",
        ):
            (root / relative).mkdir(
                parents=True,
                exist_ok=True,
            )

        registry = root / "reports" / "projects.sqlite3"
        project = create_project(
            registry,
            project_code="SMOKE-014",
            name="Governance Smoke Test",
            status="Active",
            priority="High",
            objective="Verify Step 14 governance controls.",
            owner_label="Automated smoke test",
            target_date=(date.today() + timedelta(days=30)).isoformat(),
        )
        create_milestone(
            registry,
            project.project_id,
            title="Evidence package generated",
            status="Completed",
        )
        create_decision(
            registry,
            project.project_id,
            title="Use controlled package",
            decision="Generate checksum-verified ZIP.",
        )
        upsert_gate(
            registry,
            project.project_id,
            gate_name="Release approval",
            status="Approved",
        )

        readiness = project_readiness(
            root,
            project.project_id,
        )
        assert readiness["percent"] > 0

        package = build_project_evidence_package(
            root,
            project.project_id,
        )
        summary = inspect_project_evidence_package(package)
        assert summary.project_code == "SMOKE-014"

        audit = verify_audit_chain(root / "reports" / "audit.jsonl")
        assert audit["valid"]
        assert audit["chained_events"] >= 4

    print("BioIntel Step 24 Scientific Performance governance smoke test passed")


if __name__ == "__main__":
    main()
