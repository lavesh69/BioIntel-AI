"""Validate BioIntel Education Mega R14 source and evidence pack."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

REQUIRED_REPORTS = [
    "BIOINTEL_EDUCATION_MEGA_UPGRADE_REPORT.md",
    "BIOINTEL_EDUCATION_FEATURE_MATRIX.json",
    "BIOINTEL_EDUCATION_PRESERVATION_REPORT.md",
    "BIOINTEL_EDUCATION_DATABASE_MIGRATION_REPORT.md",
    "BIOINTEL_CLASSROOM_IMPLEMENTATION_REPORT.md",
    "BIOINTEL_ACADEMY_IMPLEMENTATION_REPORT.md",
    "BIOINTEL_LECTURE_STUDIO_IMPLEMENTATION_REPORT.md",
    "BIOINTEL_SHIRO_EDUCATION_INTEGRATION_REPORT.md",
    "BIOINTEL_EDUCATION_SECURITY_REPORT.md",
    "BIOINTEL_EDUCATION_ACCESSIBILITY_REPORT.md",
    "BIOINTEL_EDUCATION_PERFORMANCE_REPORT.md",
    "BIOINTEL_EDUCATION_WINDOWS_VALIDATION.md",
    "BIOINTEL_EDUCATION_TEST_RESULTS.json",
    "BIOINTEL_EDUCATION_CHANGELOG.md",
    "BIOINTEL_EDUCATION_KNOWN_LIMITATIONS.md",
]
REQUIRED_GUIDES = [
    "USER_GUIDE.md", "TEACHER_GUIDE.md", "STUDENT_GUIDE.md",
    "INSTITUTION_ADMINISTRATOR_GUIDE.md", "LECTURE_CREATOR_GUIDE.md",
    "SHIRO_AI_EDUCATION_GUIDE.md", "INSTALLATION_GUIDE.md",
    "TROUBLESHOOTING_GUIDE.md", "MIGRATION_AND_ROLLBACK_GUIDE.md",
]
ROUTES = [
    "pages/141_Shiro_AI_Studio.py",
    "pages/150_BioIntel_Education_Home_v17.py",
    "pages/151_BioIntel_Classroom_v17.py",
    "pages/153_BioIntel_Academy_Lecture_Studio.py",
    "pages/155_Education_Intelligence_Hub.py",
    "pages/172_Multilingual_Lecture_Intelligence.py",
    "pages/273_Shiro_AI.py",
    "pages/339_BioIntel_Education_Home.py",
    "pages/340_BioIntel_Classroom.py",
    "pages/342_BioIntel_Academy_and_Lecture_Studio.py",
    "pages/344_BioIntel_Examination_Command_Center.py",
    "pages/345_BioIntel_Education_Intelligence_Hub.py",
    "pages/343_BioIntel_Education_Universe.py",
]


def sha256(path):
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def validate(root):
    failures = []
    report_dir = root / "reports/education_pdf_mega_upgrade_r14"
    guide_dir = root / "docs/education_mega_r14"
    for name in REQUIRED_REPORTS:
        path = report_dir / name
        if not path.is_file() or path.stat().st_size == 0:
            failures.append("missing report: " + name)
    for name in REQUIRED_GUIDES:
        path = guide_dir / name
        if not path.is_file() or path.stat().st_size == 0:
            failures.append("missing guide: " + name)

    matrix_path = report_dir / "BIOINTEL_EDUCATION_FEATURE_MATRIX.json"
    if matrix_path.is_file():
        matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
        criteria = matrix.get("acceptance_criteria", [])
        if len(criteria) != 30:
            failures.append("feature matrix must contain 30 criteria")
        if any(item.get("status") != "passed" for item in criteria):
            failures.append("not all feature-matrix criteria passed")

    tests_path = report_dir / "BIOINTEL_EDUCATION_TEST_RESULTS.json"
    if tests_path.is_file():
        results = json.loads(tests_path.read_text(encoding="utf-8"))
        complete = results.get("suites", [{}])[0]
        if results.get("status") != "passed" or complete.get("passed") != 248 or complete.get("failed") != 0:
            failures.append("test result evidence mismatch")

    removed_path = root / "reports/education_selective_mega_update/removed_items.json"
    if not removed_path.is_file():
        failures.append("preservation removed-items evidence missing")
    else:
        removed = json.loads(removed_path.read_text(encoding="utf-8"))
        if any(value for value in removed.values()):
            failures.append("preservation evidence contains removals")

    windows_path = root / "reports/education_selective_mega_update/windows_validation.json"
    if not windows_path.is_file():
        failures.append("Windows validation evidence missing")
    else:
        windows = json.loads(windows_path.read_text(encoding="utf-8"))
        if windows.get("status") != "completed":
            failures.append("Windows validation is not complete")
        checks = windows.get("checks", {})
        required = ["offline_wheelhouse", "path_with_spaces", "install_windows", "repeat_install_repair", "run_both_api_ui"]
        for name in required:
            value = checks.get(name, {})
            if not isinstance(value, dict) or value.get("status") != "passed":
                failures.append("Windows check not passed: " + name)

    for relative in ROUTES:
        path = root / relative
        if not path.is_file():
            failures.append("route missing: " + relative)
            continue
        text = path.read_text(encoding="utf-8")
        if "apply_theme" not in text:
            failures.append("theme not applied: " + relative)

    required_sources = [
        "src/biointel/education/intelligence_ui.py",
        "src/biointel/education/phase4.py",
        "src/biointel/education/phase7.py",
        "src/biointel/education/phase16_runtime/service.py",
        "src/biointel/education/lecture_intelligence.py",
        "tests/test_education_pdf_mega_upgrade.py",
    ]
    for relative in required_sources:
        if not (root / relative).is_file():
            failures.append("required implementation source missing: " + relative)

    sources = [
        root / "src/biointel/education/lecture_intelligence.py",
        root / "pages/141_Shiro_AI_Studio.py",
        root / "pages/153_BioIntel_Academy_Lecture_Studio.py",
    ]
    banned = ["sample transcript", "dr. demo", "prof. demo", "mock citation"]
    for path in sources:
        if path.is_file():
            lowered = path.read_text(encoding="utf-8").casefold()
            for token in banned:
                if token in lowered:
                    failures.append("static fake token in " + str(path.relative_to(root)) + ": " + token)

    manifests = []
    for relative in ["release/SOURCE_MANIFEST_SHA256.json", "STEP220_SOURCE_MANIFEST_SHA256.json"]:
        path = root / relative
        if path.is_file():
            manifests.append({"path": relative, "sha256": sha256(path)})

    result = {
        "schema": "biointel.education.mega-r14.validation.v1",
        "root": str(root),
        "status": "passed" if not failures else "failed",
        "checks": {
            "required_reports": len(REQUIRED_REPORTS),
            "required_guides": len(REQUIRED_GUIDES),
            "acceptance_criteria": 30,
            "route_theme_checks": len(ROUTES),
            "preservation_zero_removals": not any("preservation" in value for value in failures),
            "windows_evidence": not any("Windows" in value for value in failures),
        },
        "manifests": manifests,
        "failures": failures,
    }
    print(json.dumps(result, indent=2))
    return 0 if not failures else 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    return validate(args.root.resolve())


if __name__ == "__main__":
    raise SystemExit(main())
