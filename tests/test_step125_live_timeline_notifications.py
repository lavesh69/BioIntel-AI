from __future__ import annotations

from pathlib import Path

from biointel.ui.live_experience import LiveExperienceStore
from biointel.ui.workflow import WorkflowRun, _live_timeline_html


def test_live_run_persists_stages_and_completion(tmp_path: Path) -> None:
    store = LiveExperienceStore(tmp_path / "live.sqlite3")
    run_id = store.start_run("Variant analysis", page_key="variant_workbench")
    store.add_stage(run_id, sequence_no=1, label="Validate VCF", progress=0.15)
    store.add_stage(run_id, sequence_no=2, label="Annotate variants", detail="VEP adapter", progress=0.75)
    store.finish_run(run_id, status="completed", elapsed_seconds=2.5, manifest={"ok": True})

    run = store.recent_runs(limit=1)[0]
    stages = store.stages(run_id)
    assert run.status == "completed"
    assert run.progress == 1.0
    assert run.page_key == "variant_workbench"
    assert [stage.label for stage in stages] == ["Validate VCF", "Annotate variants"]
    assert all(stage.status == "completed" for stage in stages)


def test_notification_dedup_read_dismiss_and_export(tmp_path: Path) -> None:
    store = LiveExperienceStore(tmp_path / "live.sqlite3")
    first = store.notify(
        "Analysis failed", "Schema mismatch", level="error", source="analysis",
        action_target="variant_workbench", dedupe_key="same-event",
    )
    second = store.notify(
        "Analysis failed", "Schema mismatch", level="error", source="analysis",
        action_target="variant_workbench", dedupe_key="same-event",
    )
    assert first == second
    notices = store.notifications()
    assert len(notices) == 1
    assert notices[0].occurrence_count == 2
    assert store.unread_count() == 1

    store.mark_read([first])
    assert store.unread_count() == 0
    store.dismiss(first)
    assert store.notifications() == []
    exported = store.export_state()
    assert exported["schema"] == "biointel.live_experience.v1"


def test_inline_timeline_html_is_accessible() -> None:
    run = WorkflowRun(label="Protein design", started_at_utc="2026-01-01T00:00:00+00:00", started_monotonic=0.0)
    run.stages = [
        {"label": "Validate structure", "detail": "Chain A", "progress": 0.2},
        {"label": "Generate sequences", "detail": "ProteinMPNN", "progress": 0.7},
    ]
    html = _live_timeline_html(run, terminal_status="running")
    assert 'aria-label="Live analysis timeline"' in html
    assert "Validate structure" in html
    assert "ProteinMPNN" in html
    assert "70%" in html


def test_step125_shell_contains_timeline_and_notification_controls() -> None:
    theme = Path("src/biointel/ui/theme.py").read_text(encoding="utf-8")
    css = Path("src/biointel/ui/premium_visuals.css").read_text(encoding="utf-8")
    assert "Live Analysis Timeline" in theme
    assert "Scientific Notification Center" in theme
    assert "Mark read" in theme and "Dismiss" in theme
    assert "Pause" in theme and "Resume" in theme and "Cancel" in theme
    assert ".bio-live-timeline" in css
    assert "prefers-reduced-motion" in css
