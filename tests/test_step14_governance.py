from __future__ import annotations

import io
import json
import zipfile
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from biointel.api.main import app
from biointel.cli import main as cli_main
from biointel.governance.governance_registry import (
    create_decision,
    create_milestone,
    governance_portfolio_summary,
    list_decisions,
    list_gates,
    list_milestones,
    project_governance_snapshot,
    update_milestone,
    upsert_gate,
)
from biointel.governance.reproducibility import (
    build_lineage_graph,
    build_project_evidence_package,
    inspect_project_evidence_package,
    project_readiness,
)
from biointel.operations.activity_center import visible_alerts
from biointel.operations.executive_summary import build_executive_summary
from biointel.portfolio.project_exchange import (
    export_project_bundle,
    import_project_bundle,
)
from biointel.portfolio.project_registry import (
    create_project,
    delete_project,
    list_projects,
)
from biointel.reports.workspace_report import (
    build_workspace_report_data,
    build_workspace_report_html,
)
from biointel.ui.navigation import PAGE_BY_KEY, PAGE_CATALOG
from biointel.utils.audit_log import (
    append_audit_event,
    verify_audit_chain,
)

ROOT = Path(__file__).resolve().parents[1]


def _root(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    for relative in (
        "models",
        "reports",
        "config",
        "cache/external",
    ):
        (root / relative).mkdir(parents=True, exist_ok=True)
    return root


def test_governance_milestone_lifecycle(
    tmp_path: Path,
) -> None:
    root = _root(tmp_path)
    registry = root / "reports" / "projects.sqlite3"
    project = create_project(
        registry,
        project_code="GOV-001",
        name="Governance Project",
    )
    milestone = create_milestone(
        registry,
        project.project_id,
        title="Complete external validation",
        status="In Progress",
        due_date=(date.today() + timedelta(days=14)).isoformat(),
        acceptance_criteria="Independent dataset reviewed.",
    )
    updated = update_milestone(
        registry,
        milestone.milestone_id,
        status="Completed",
        evidence_reference="validation_report.html",
    )
    assert updated.status == "Completed"
    assert updated.evidence_reference == "validation_report.html"
    snapshot = project_governance_snapshot(
        registry,
        project.project_id,
    )
    assert snapshot["summary"]["milestones_total"] == 1
    assert snapshot["summary"]["milestones_completed"] == 1


def test_decision_and_gate_register(
    tmp_path: Path,
) -> None:
    root = _root(tmp_path)
    registry = root / "reports" / "projects.sqlite3"
    project = create_project(
        registry,
        project_code="DEC-001",
        name="Decision Project",
    )
    decision = create_decision(
        registry,
        project.project_id,
        title="Use grouped target split",
        decision="Adopt target-group split for final evaluation.",
        status="Approved",
        rationale="Reduce target leakage.",
        approver_label="Scientific reviewer",
    )
    gate = upsert_gate(
        registry,
        project.project_id,
        gate_name="Release approval",
        status="Conditional",
        reviewer_label="Release reviewer",
        conditions="Complete external validation.",
    )
    assert decision.status == "Approved"
    assert gate.status == "Conditional"
    assert len(list_decisions(registry, project.project_id)) == 1
    assert len(list_gates(registry, project.project_id)) == 1


def test_governance_portfolio_summary(
    tmp_path: Path,
) -> None:
    root = _root(tmp_path)
    registry = root / "reports" / "projects.sqlite3"
    project = create_project(
        registry,
        project_code="SUM-001",
        name="Summary Project",
    )
    create_milestone(
        registry,
        project.project_id,
        title="Dataset freeze",
        status="Completed",
    )
    create_decision(
        registry,
        project.project_id,
        title="Freeze dataset",
        decision="Use version 1.0.",
    )
    upsert_gate(
        registry,
        project.project_id,
        gate_name="Data readiness",
        status="Approved",
    )
    summary = governance_portfolio_summary(registry)
    assert summary["projects_with_governance"] == 1
    assert summary["milestones_completed"] == 1
    assert summary["approved_decisions"] == 1
    assert summary["gates_approved"] == 1


def test_project_exchange_roundtrip(
    tmp_path: Path,
) -> None:
    root = _root(tmp_path)
    registry = root / "reports" / "projects.sqlite3"
    source = create_project(
        registry,
        project_code="EXP-001",
        name="Exchange Project",
        objective="Portable governance record.",
    )
    create_milestone(
        registry,
        source.project_id,
        title="Milestone A",
    )
    create_decision(
        registry,
        source.project_id,
        title="Decision A",
        decision="Proceed.",
    )
    upsert_gate(
        registry,
        source.project_id,
        gate_name="Data readiness",
        status="Approved",
    )

    bundle = export_project_bundle(
        registry,
        source.project_id,
    )
    imported = import_project_bundle(
        registry,
        bundle,
        project_code="EXP-002",
        name_suffix="Copy",
    )
    assert imported.project_code == "EXP-002"
    snapshot = project_governance_snapshot(
        registry,
        imported.project_id,
    )
    assert snapshot["summary"]["milestones_total"] == 1
    assert snapshot["summary"]["decisions_total"] == 1
    assert snapshot["summary"]["gates_total"] == 1


def test_project_delete_cascades_governance_records(
    tmp_path: Path,
) -> None:
    root = _root(tmp_path)
    registry = root / "reports" / "projects.sqlite3"
    project = create_project(
        registry,
        project_code="DEL-014",
        name="Delete Governance",
    )
    create_milestone(
        registry,
        project.project_id,
        title="Delete me",
    )
    create_decision(
        registry,
        project.project_id,
        title="Delete decision",
        decision="Delete.",
    )
    upsert_gate(
        registry,
        project.project_id,
        gate_name="Data readiness",
        status="Approved",
    )
    assert delete_project(registry, project.project_id)
    assert list_milestones(registry, project.project_id) == []
    assert list_decisions(registry, project.project_id) == []
    assert list_gates(registry, project.project_id) == []


def test_invalid_project_import_is_rejected_before_creation(
    tmp_path: Path,
) -> None:
    root = _root(tmp_path)
    registry = root / "reports" / "projects.sqlite3"
    source = create_project(
        registry,
        project_code="BAD-001",
        name="Invalid Import Source",
    )
    payload = export_project_bundle(
        registry,
        source.project_id,
    )
    payload["governance"]["milestones"] = [
        {
            "title": "Invalid milestone",
            "status": "Not a valid status",
        }
    ]
    with pytest.raises(ValueError, match="milestone status"):
        import_project_bundle(
            registry,
            payload,
            project_code="BAD-002",
        )
    assert all(project.project_code != "BAD-002" for project in list_projects(registry))


def test_audit_hash_chain_and_tamper_detection(
    tmp_path: Path,
) -> None:
    audit = tmp_path / "audit.jsonl"
    append_audit_event(
        audit,
        "project_created",
        "success",
        {"project_id": "prj-1"},
    )
    append_audit_event(
        audit,
        "gate_approved",
        "success",
        {"project_id": "prj-1"},
    )
    valid = verify_audit_chain(audit)
    assert valid["valid"] is True
    assert valid["chained_events"] == 2

    lines = audit.read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[0])
    first["status"] = "tampered"
    lines[0] = json.dumps(first, sort_keys=True)
    audit.write_text("\n".join(lines) + "\n", encoding="utf-8")
    invalid = verify_audit_chain(audit)
    assert invalid["valid"] is False
    assert invalid["errors"]


def test_readiness_and_lineage_for_governed_project(
    tmp_path: Path,
) -> None:
    root = _root(tmp_path)
    registry = root / "reports" / "projects.sqlite3"
    project = create_project(
        registry,
        project_code="RDY-001",
        name="Readiness Project",
        objective="Build release evidence.",
        owner_label="Research lead",
        target_date=(date.today() + timedelta(days=30)).isoformat(),
    )
    create_milestone(
        registry,
        project.project_id,
        title="Validation complete",
        status="Completed",
    )
    create_decision(
        registry,
        project.project_id,
        title="Release strategy",
        decision="Controlled internal release.",
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
    assert 0 <= readiness["percent"] <= 100
    assert readiness["label"]
    lineage = build_lineage_graph(
        root,
        project.project_id,
    )
    node_types = {node["type"] for node in lineage["nodes"]}
    assert {"project", "milestone", "decision", "gate"} <= node_types


def test_evidence_package_integrity_and_contents(
    tmp_path: Path,
) -> None:
    root = _root(tmp_path)
    registry = root / "reports" / "projects.sqlite3"
    project = create_project(
        registry,
        project_code="PKG-001",
        name="Evidence Package Project",
    )
    create_milestone(
        registry,
        project.project_id,
        title="Package milestone",
    )
    package = build_project_evidence_package(
        root,
        project.project_id,
    )
    summary = inspect_project_evidence_package(package)
    assert summary.project_code == "PKG-001"
    assert "PROJECT_REPORT.html" in summary.files
    assert "governance/milestones.json" in summary.files


def test_evidence_package_detects_tampering(
    tmp_path: Path,
) -> None:
    root = _root(tmp_path)
    registry = root / "reports" / "projects.sqlite3"
    project = create_project(
        registry,
        project_code="PKG-002",
        name="Tamper Test",
    )
    package = build_project_evidence_package(
        root,
        project.project_id,
    )
    source = zipfile.ZipFile(io.BytesIO(package), "r")
    buffer = io.BytesIO()
    with (
        source,
        zipfile.ZipFile(
            buffer,
            "w",
            compression=zipfile.ZIP_DEFLATED,
        ) as target,
    ):
        for info in source.infolist():
            content = source.read(info.filename)
            if info.filename == "project/project.json":
                content = b'{"tampered": true}'
            target.writestr(info.filename, content)

    with pytest.raises(ValueError, match="Checksum mismatch"):
        inspect_project_evidence_package(buffer.getvalue())


def test_governance_alerts_for_blocked_and_rejected(
    tmp_path: Path,
) -> None:
    root = _root(tmp_path)
    registry = root / "reports" / "projects.sqlite3"
    project = create_project(
        registry,
        project_code="ALT-001",
        name="Alert Project",
        status="Active",
    )
    create_milestone(
        registry,
        project.project_id,
        title="Blocked work",
        status="Blocked",
    )
    upsert_gate(
        registry,
        project.project_id,
        gate_name="Release approval",
        status="Rejected",
        conditions="Insufficient validation evidence.",
    )
    titles = {alert.title for alert in visible_alerts(root)}
    assert "ALT-001 milestone is blocked" in titles
    assert "ALT-001 governance gate rejected" in titles


def test_executive_summary_has_governance_component(
    tmp_path: Path,
) -> None:
    root = _root(tmp_path)
    registry = root / "reports" / "projects.sqlite3"
    project = create_project(
        registry,
        project_code="EXG-001",
        name="Executive Governance",
        status="Active",
    )
    create_milestone(
        registry,
        project.project_id,
        title="Milestone",
    )
    create_decision(
        registry,
        project.project_id,
        title="Decision",
        decision="Proceed.",
    )
    upsert_gate(
        registry,
        project.project_id,
        gate_name="Data readiness",
        status="Approved",
    )
    summary = build_executive_summary(root)
    assert summary["score_components"]["governance"] == 15
    assert summary["governance"]["gates_approved"] == 1


def test_workspace_report_includes_governance_and_audit(
    tmp_path: Path,
) -> None:
    root = _root(tmp_path)
    registry = root / "reports" / "projects.sqlite3"
    project = create_project(
        registry,
        project_code="RPT-014",
        name="Governance Report",
    )
    create_milestone(
        registry,
        project.project_id,
        title="Report milestone",
    )
    append_audit_event(
        root / "reports" / "audit.jsonl",
        "report_test",
        "success",
    )
    report = build_workspace_report_data(
        root,
        title="Step 14 Report",
    )
    assert "governance_summary" in report
    assert "audit_integrity" in report
    rendered = build_workspace_report_html(report)
    assert "Governance summary" in rendered
    assert "Audit integrity" in rendered


def test_step14_navigation_and_pages() -> None:
    assert len(PAGE_CATALOG) >= 71
    for key, filename in (
        ("governance_hub", "30_Governance_Hub.py"),
        ("evidence_studio", "31_Evidence_Package_Studio.py"),
        ("release_readiness", "32_Release_Readiness_Lineage.py"),
    ):
        page = PAGE_BY_KEY[key]
        assert page.path.endswith(filename)
        source = ROOT / page.path
        assert source.is_file()
        content = source.read_text(encoding="utf-8")
        assert "apply_theme()" in content
        assert "hero(" in content


def test_step14_api_endpoints() -> None:
    client = TestClient(app)
    for endpoint in (
        "/governance/summary",
        "/audit/integrity",
    ):
        response = client.get(endpoint)
        assert response.status_code == 200

    unknown = client.get("/projects/prj-does-not-exist/readiness")
    assert unknown.status_code == 404


def test_step14_cli_governance_and_package(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = _root(tmp_path)
    monkeypatch.chdir(root)

    assert (
        cli_main(
            [
                "project-create",
                "--code",
                "CLI-014",
                "--name",
                "Step 14 CLI",
            ]
        )
        == 0
    )
    project_payload = json.loads(capsys.readouterr().out)
    project_id = project_payload["project_id"]

    assert (
        cli_main(
            [
                "milestone-create",
                "--project-id",
                project_id,
                "--title",
                "CLI milestone",
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert (
        cli_main(
            [
                "decision-record",
                "--project-id",
                project_id,
                "--title",
                "CLI decision",
                "--decision",
                "Proceed.",
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert (
        cli_main(
            [
                "gate-set",
                "--project-id",
                project_id,
                "--gate",
                "Release approval",
                "--status",
                "Approved",
            ]
        )
        == 0
    )
    capsys.readouterr()

    output = root / "reports" / "generated" / "evidence.zip"
    assert (
        cli_main(
            [
                "evidence-package",
                "--project-id",
                project_id,
                "--output",
                str(output),
            ]
        )
        == 0
    )
    package_payload = json.loads(capsys.readouterr().out)
    assert package_payload["project_code"] == "CLI-014"
    assert output.is_file()

    assert cli_main(["audit-verify"]) == 0
    audit_payload = json.loads(capsys.readouterr().out)
    assert "valid" in audit_payload
