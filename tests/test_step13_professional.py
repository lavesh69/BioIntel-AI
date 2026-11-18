from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from biointel.api.main import app
from biointel.cli import main as cli_main
from biointel.operations.activity_center import (
    dismiss_alert,
    load_activity_state,
    visible_alerts,
)
from biointel.operations.executive_summary import (
    build_executive_summary,
)
from biointel.portfolio.project_registry import (
    create_project,
    delete_project,
    get_project,
    list_project_events,
    list_projects,
    portfolio_summary,
    update_project,
)
from biointel.reports.workspace_report import (
    build_workspace_report_data,
    build_workspace_report_html,
)
from biointel.ui.navigation import PAGE_BY_KEY, PAGE_CATALOG
from biointel.ui.preferences import UiPreferences
from biointel.utils.local_data import list_managed_files
from biointel.utils.workspace_backup import (
    create_workspace_backup,
    inspect_workspace_backup,
)

ROOT = Path(__file__).resolve().parents[1]


def test_project_registry_crud_and_events(
    tmp_path: Path,
) -> None:
    registry = tmp_path / "projects.sqlite3"
    target = (date.today() + timedelta(days=30)).isoformat()

    created = create_project(
        registry,
        project_code="BTX-001",
        name="Kinase Validation",
        status="Active",
        priority="High",
        objective="Validate a lead series.",
        owner_label="Research Team",
        tags="kinase, validation",
        target_date=target,
        dataset_sha256="abc123",
        model_filename="model.joblib",
    )
    assert created.project_code == "BTX-001"
    assert created.tags == ("kinase", "validation")
    assert get_project(registry, created.project_id) == created

    updated = update_project(
        registry,
        created.project_id,
        status="Validation",
        priority="Critical",
        notes="External validation started.",
    )
    assert updated.status == "Validation"
    assert updated.priority == "Critical"

    events = list_project_events(
        registry,
        project_id=created.project_id,
    )
    assert len(events) == 2
    assert {event.event_type for event in events} == {
        "created",
        "updated",
    }

    assert delete_project(registry, created.project_id)
    assert list_projects(registry) == []


def test_project_registry_rejects_duplicate_code(
    tmp_path: Path,
) -> None:
    registry = tmp_path / "projects.sqlite3"
    create_project(
        registry,
        project_code="DUP-001",
        name="First",
    )
    with pytest.raises(ValueError, match="already exists"):
        create_project(
            registry,
            project_code="dup-001",
            name="Second",
        )


def test_portfolio_summary_tracks_overdue_and_due_soon(
    tmp_path: Path,
) -> None:
    registry = tmp_path / "projects.sqlite3"
    create_project(
        registry,
        project_code="OLD-001",
        name="Overdue",
        status="Active",
        priority="Critical",
        target_date=(date.today() - timedelta(days=2)).isoformat(),
    )
    create_project(
        registry,
        project_code="SOON-001",
        name="Due soon",
        status="Validation",
        target_date=(date.today() + timedelta(days=7)).isoformat(),
    )
    summary = portfolio_summary(registry)
    assert summary["total"] == 2
    assert summary["active"] == 2
    assert summary["critical"] == 1
    assert summary["overdue"] == 1
    assert summary["due_soon"] == 1


def test_activity_alerts_include_project_risks(
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    for relative in (
        "models",
        "reports",
        "config",
        "cache/external",
    ):
        (root / relative).mkdir(parents=True, exist_ok=True)

    create_project(
        root / "reports" / "projects.sqlite3",
        project_code="RISK-001",
        name="Risk Project",
        status="Active",
        priority="High",
        target_date=(date.today() - timedelta(days=1)).isoformat(),
    )

    alerts = visible_alerts(root)
    titles = {alert.title for alert in alerts}
    assert "RISK-001 is overdue" in titles
    assert "RISK-001 has no linked dataset" in titles
    assert "RISK-001 has no linked model" in titles

    overdue = next(alert for alert in alerts if alert.title == "RISK-001 is overdue")
    dismiss_alert(root, overdue.item_id)
    remaining = visible_alerts(root)
    assert overdue.item_id not in {alert.item_id for alert in remaining}
    assert overdue.item_id in load_activity_state(root)["dismissed"]


def test_executive_summary_includes_portfolio(
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    for relative in (
        "models",
        "reports",
        "config",
        "cache/external",
    ):
        (root / relative).mkdir(parents=True, exist_ok=True)

    create_project(
        root / "reports" / "projects.sqlite3",
        project_code="EXE-001",
        name="Executive Project",
        status="Active",
        dataset_sha256="dataset123",
        model_filename="model.joblib",
    )

    summary = build_executive_summary(root)
    assert summary["portfolio"]["total"] == 1
    assert summary["portfolio"]["active"] == 1
    assert 0 <= summary["maturity_score"] <= 100
    assert summary["maturity_label"]


def test_workspace_report_contains_projects_and_executive(
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    for relative in (
        "models",
        "reports",
        "config",
        "cache/external",
    ):
        (root / relative).mkdir(parents=True, exist_ok=True)

    create_project(
        root / "reports" / "projects.sqlite3",
        project_code="REP-001",
        name="<b>Report Project</b>",
        status="Planning",
    )
    report = build_workspace_report_data(
        root,
        title="Professional Portfolio",
    )
    assert report["projects"][0]["project_code"] == "REP-001"
    assert "executive_summary" in report

    rendered = build_workspace_report_html(report)
    assert "Project portfolio" in rendered
    assert "Executive summary" in rendered
    assert "<b>Report Project</b>" not in rendered
    assert "&lt;b&gt;Report Project&lt;/b&gt;" in rendered


def test_project_files_are_managed_and_backed_up(
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    (root / "models").mkdir(parents=True)
    (root / "reports").mkdir()
    (root / "cache" / "external").mkdir(parents=True)

    create_project(
        root / "reports" / "projects.sqlite3",
        project_code="BKP-001",
        name="Backup Project",
    )

    managed = list_managed_files(root)
    assert any(item.relative_path == "reports/projects.sqlite3" for item in managed)

    backup = create_workspace_backup(root)
    summary = inspect_workspace_backup(backup)
    assert "reports/projects.sqlite3" in summary.files


def test_step13_navigation_and_pages() -> None:
    assert len(PAGE_CATALOG) >= 71
    for key, filename in (
        ("executive_overview", "27_Executive_Overview.py"),
        ("project_portfolio", "28_Project_Portfolio.py"),
        ("activity_center", "29_Activity_Risk_Center.py"),
    ):
        page = PAGE_BY_KEY[key]
        assert page.path.endswith(filename)
        source = ROOT / page.path
        assert source.is_file()
        content = source.read_text(encoding="utf-8")
        assert "apply_theme()" in content
        assert "hero(" in content


def test_professional_palette_is_default() -> None:
    preferences = UiPreferences()
    assert preferences.palette == "Executive"


def test_step13_api_endpoints() -> None:
    client = TestClient(app)
    for endpoint, key in (
        ("/portfolio/projects", "projects"),
        ("/operations/alerts", "alerts"),
        ("/operations/timeline", "timeline"),
    ):
        response = client.get(endpoint)
        assert response.status_code == 200
        assert key in response.json()

    executive = client.get("/executive/summary")
    assert executive.status_code == 200
    assert "maturity_score" in executive.json()


def test_step13_cli_project_and_summary_commands(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "project"
    for relative in (
        "models",
        "reports",
        "config",
        "cache/external",
    ):
        (root / relative).mkdir(parents=True, exist_ok=True)

    monkeypatch.chdir(root)
    assert (
        cli_main(
            [
                "project-create",
                "--code",
                "CLI-001",
                "--name",
                "CLI Project",
                "--status",
                "Active",
            ]
        )
        == 0
    )
    created = json.loads(capsys.readouterr().out)
    assert created["project_code"] == "CLI-001"

    assert cli_main(["project-list"]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert len(listed["projects"]) == 1

    output = root / "reports" / "generated" / "executive.json"
    assert (
        cli_main(
            [
                "executive-summary",
                "--output",
                str(output),
            ]
        )
        == 0
    )
    summary = json.loads(capsys.readouterr().out)
    assert summary["portfolio"]["total"] == 1
    assert output.is_file()

    activity_output = root / "reports" / "generated" / "activity.json"
    assert (
        cli_main(
            [
                "activity-export",
                "--output",
                str(activity_output),
            ]
        )
        == 0
    )
    activity_payload = json.loads(capsys.readouterr().out)
    assert "alerts" in activity_payload
    assert activity_output.is_file()


def test_activity_state_contains_no_sensitive_payload(
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    for relative in (
        "models",
        "reports",
        "config",
        "cache/external",
    ):
        (root / relative).mkdir(parents=True, exist_ok=True)

    alerts = visible_alerts(root)
    if alerts:
        dismiss_alert(root, alerts[0].item_id)
    payload = (root / "reports" / "activity_state.json").read_text(encoding="utf-8")
    lowered = payload.lower()
    assert "sequence" not in lowered
    assert "smiles" not in lowered
    assert "password" not in lowered
