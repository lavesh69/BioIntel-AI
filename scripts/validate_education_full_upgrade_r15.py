"""Validate a reconstructed BioIntel Education Full Upgrade R15 release."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.education.local_transcription import local_transcription_readiness  # noqa: E402
from verify_windows_wheelhouse import verify as verify_wheelhouse  # noqa: E402

REPORTS = [
    "BIOINTEL_EDUCATION_FULL_UPGRADE_REPORT.md",
    "BIOINTEL_EDUCATION_R15_TEST_RESULTS.json",
    "BIOINTEL_LOCAL_TRANSCRIPTION_REPORT.md",
    "BIOINTEL_DEPLOYMENT_BOUNDARIES.md",
    "BIOINTEL_SECURITY_AND_GOVERNANCE.md",
    "BIOINTEL_PRESERVATION_REPORT.md",
    "BIOINTEL_WINDOWS_OFFLINE_INSTALLER_REPORT.md",
    "BIOINTEL_PERFORMANCE_REPORT.md",
    "BIOINTEL_EDUCATION_R15_CHANGELOG.md",
    "RECONSTRUCT_BIOINTEL_EDUCATION_R15.md",
    "local-transcription-qualification.json",
    "deployment-readiness.json",
    "windows-wheelhouse-verification.json",
    "streamlit-apptest.json",
    "bounded-load-probe.json",
    "preservation-summary.json",
]
ROUTES = [141, 153, 155, 339, 340, 342, 343, 344, 345, 354]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--output", default="")
    parser.add_argument("--allow-userdata", action="store_true")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    failures: list[str] = []
    report_dir = root / "reports" / "education_full_upgrade_r15"
    for name in REPORTS:
        path = report_dir / name
        if not path.is_file() or path.stat().st_size == 0:
            failures.append(f"missing report: {name}")
    tests_path = report_dir / "BIOINTEL_EDUCATION_R15_TEST_RESULTS.json"
    if tests_path.is_file():
        tests = json.loads(tests_path.read_text(encoding="utf-8"))
        suite = tests.get("education_shiro_phase16", {})
        if tests.get("status") != "passed" or suite.get("tests") != 254 or suite.get("failed") != 0:
            failures.append("254-test result evidence mismatch")
        if tests.get("streamlit", {}).get("passed") != 10 or tests.get("streamlit", {}).get("exceptions") != 0:
            failures.append("Streamlit evidence mismatch")
    preservation_path = report_dir / "preservation-summary.json"
    if preservation_path.is_file():
        preservation = json.loads(preservation_path.read_text(encoding="utf-8"))
        if not preservation.get("passed") or any(preservation.get("removed_counts", {}).values()):
            failures.append("preservation gate failed")
    model_dir = root / "models" / "education" / "faster-whisper-tiny"
    manifest_path = model_dir / "MODEL_MANIFEST_SHA256.json"
    if not manifest_path.is_file():
        failures.append("model manifest missing")
    else:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for row in manifest.get("files", []):
            path = model_dir / row["path"]
            if not path.is_file() or path.stat().st_size != row["size_bytes"] or sha256(path) != row["sha256"]:
                failures.append(f"model integrity failed: {row['path']}")
    readiness = local_transcription_readiness(root)
    if not readiness["ready"]:
        failures.append("local transcription readiness failed: " + readiness.get("reason", ""))
    wheelhouse = verify_wheelhouse(root)
    if not wheelhouse.get("valid") or wheelhouse.get("wheel_count") != 141:
        failures.append("141-wheel offline wheelhouse gate failed")
    pages = list((root / "pages").glob("*.py"))
    for route_id in ROUTES:
        matches = [path for path in pages if path.name.startswith(f"{route_id}_")]
        if not matches:
            failures.append(f"route {route_id} missing")
        elif "apply_theme" not in matches[0].read_text(encoding="utf-8"):
            failures.append(f"route {route_id} theme missing")
    required_source = [
        "src/biointel/education/local_transcription.py",
        "src/biointel/education/phase16_runtime/service.py",
        "src/biointel/education/phase16_runtime/schema.py",
        "scripts/run_education_transcription_worker.py",
        "release/USER_DATA_SEED_MANIFEST_SHA256.json",
        "scripts/qualify_education_local_transcription.py",
        "config/education_full_upgrade.env.template",
        "tests/test_education_full_local_upgrade.py",
    ]
    for relative in required_source:
        if not (root / relative).is_file():
            failures.append(f"required source missing: {relative}")
    api_text = (root / "src/biointel/education/api.py").read_text(encoding="utf-8")
    for suffix in ("/execute", "/candidate", "/approve", "/reject"):
        if f'/phase16/transcription-jobs/{{job_id}}{suffix}' not in api_text:
            failures.append(f"transcription API missing: {suffix}")
    if not args.allow_userdata and (root / "UserData").exists():
        failures.append("packaged release must not contain UserData")
    if any((model_dir / ".cache").rglob("*")) if (model_dir / ".cache").exists() else False:
        failures.append("packaged release contains model download cache")
    result = {
        "schema": "biointel.education.full-upgrade-r15.validation.v1",
        "root": str(root),
        "status": "passed" if not failures else "failed",
        "checks": {"tests": 254, "streamlit_routes": 10, "wheel_count": wheelhouse.get("wheel_count"), "model_ready": readiness["ready"], "userdata_excluded": not (root / "UserData").exists()},
        "failures": failures,
    }
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    print(payload)
    if args.output:
        output = Path(args.output).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload + "\n", encoding="utf-8")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())