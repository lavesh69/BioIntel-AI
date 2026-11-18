from __future__ import annotations

import hashlib
import json
import py_compile
import tempfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_VERSION = "13.2.0"
LOCKED = {
    "pages/6_DTI_Predictor.py": "84b3ecec1356b7239a057459210af4cd130c57c08dd9449b7239d1fe5954e0cc",
    "pages/74_DTI_Validation_Evidence_Center.py": "a700a8a21649b49cf0e3a1521d2afad45039b83b767c2fe730b93fee7d4f7f11",
    "pages/109_Lab_Instrument_Import_Center.py": "22b5aba5bfea37bb1ef330ed7cca3773467463f883189602d96a0151311c8f70",
    "pages/126_LIMS_ELN_and_Sample_Chain_of_Custody_Hub.py": "eadaef1a283a5fa11ce6b243aa561508ba9ceba9f6fdcc207f4853ccf7d86905",
    "pages/157_Instrument_Integration_Hub_2.py": "cf3a5f94756def0007dbff31184ec276d90b03fc6d6e1ca792c87189e5ab7d6d",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def record(name: str, passed: bool, detail: str) -> dict[str, object]:
    return {"name": name, "passed": bool(passed), "detail": detail}


def main() -> int:
    import sys

    sys.path.insert(0, str(ROOT / "src"))
    from biointel.ui.live_experience import LiveExperienceStore

    checks: list[dict[str, object]] = []
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    checks.append(record("Version", version == EXPECTED_VERSION, version))

    config = json.loads((ROOT / "config/step125_live_timeline_notifications.json").read_text(encoding="utf-8"))
    checks.append(record("Step 125 configuration", config.get("release") == EXPECTED_VERSION, str(config.get("schema"))))

    with tempfile.TemporaryDirectory(prefix="biointel-step125-") as temporary:
        store = LiveExperienceStore(Path(temporary) / "live.sqlite3")
        run_id = store.start_run("Verification analysis", page_key="performance_jobs")
        store.add_stage(run_id, sequence_no=1, label="Validate", progress=0.2)
        store.add_stage(run_id, sequence_no=2, label="Analyse", progress=0.8)
        store.finish_run(run_id, status="completed", elapsed_seconds=0.1, manifest={"verified": True})
        notice_id = store.notify(
            "Verification complete", "Timeline and notification persistence passed.",
            level="success", source="verification", action_target="performance_jobs",
            dedupe_key="step125-verification",
        )
        store.notify(
            "Verification complete", "Timeline and notification persistence passed.",
            level="success", source="verification", action_target="performance_jobs",
            dedupe_key="step125-verification",
        )
        persisted_run = store.recent_runs(limit=1)[0]
        stages = store.stages(run_id)
        notices = store.notifications()
        checks.append(record(
            "Persistent live timeline",
            persisted_run.status == "completed" and persisted_run.progress == 1.0 and len(stages) == 2,
            f"run={persisted_run.status}; stages={len(stages)}",
        ))
        checks.append(record(
            "Notification deduplication",
            len(notices) == 1 and notices[0].notification_id == notice_id and notices[0].occurrence_count == 2,
            f"notifications={len(notices)}; occurrences={notices[0].occurrence_count if notices else 0}",
        ))
        store.mark_read([notice_id])
        checks.append(record("Unread state", store.unread_count() == 0, f"unread={store.unread_count()}"))
        store.dismiss(notice_id)
        checks.append(record("Dismiss state", not store.notifications(), f"visible={len(store.notifications())}"))

    workflow = (ROOT / "src/biointel/ui/workflow.py").read_text(encoding="utf-8")
    theme = (ROOT / "src/biointel/ui/theme.py").read_text(encoding="utf-8")
    css = (ROOT / "src/biointel/ui/premium_visuals.css").read_text(encoding="utf-8")
    checks.append(record(
        "Workflow integration",
        all(token in workflow for token in ("_live_timeline_html", "store.start_run", "store.finish_run", "Analysis completed")),
        "inline stages and terminal notifications",
    ))
    checks.append(record(
        "Global centers",
        all(token in theme for token in ("Live Analysis Timeline", "Scientific Notification Center", "Mark read", "Dismiss", "Pause", "Resume", "Cancel")),
        "timeline, controls and notification actions",
    ))
    checks.append(record(
        "Accessible timeline styling",
        all(token in css for token in (".bio-live-timeline", ".bio-live-stage.running", "prefers-reduced-motion")),
        "responsive/reduced-motion CSS",
    ))

    compile_targets = [
        ROOT / "src/biointel/ui/live_experience.py",
        ROOT / "src/biointel/ui/workflow.py",
        ROOT / "src/biointel/ui/components.py",
        ROOT / "src/biointel/ui/theme.py",
    ]
    errors: list[str] = []
    for target in compile_targets:
        try:
            py_compile.compile(str(target), doraise=True)
        except py_compile.PyCompileError as exc:
            errors.append(str(exc))
    checks.append(record("Python compilation", not errors, "; ".join(errors) if errors else f"{len(compile_targets)}/{len(compile_targets)}"))

    locked = []
    for relative, expected in LOCKED.items():
        actual = sha256(ROOT / relative)
        locked.append({"path": relative, "expected": expected, "actual": actual, "byte_identical": actual == expected})
    checks.append(record("Locked modules", all(item["byte_identical"] for item in locked), f"{sum(bool(item['byte_identical']) for item in locked)}/{len(locked)}"))

    payload = {
        "schema": "biointel.step125-verification.v1",
        "version": version,
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "checks": checks,
        "locked_modules": locked,
        "passed": all(bool(item["passed"]) for item in checks),
    }
    output = ROOT / "reports/step125_live_timeline_notification_verification.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    for item in checks:
        print(f"{'PASS' if item['passed'] else 'FAIL'} | {item['name']} | {item['detail']}")
    print(f"REPORT | {output.relative_to(ROOT)}")
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
