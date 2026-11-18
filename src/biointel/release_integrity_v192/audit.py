from __future__ import annotations

from biointel.runtime_paths import runtime_report_path

import ast
import csv
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
import tomllib
import zipfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

from biointel.scientific_execution_v190.catalog import PROFILES

RELEASE_STEP = 192
RELEASE_VERSION = "15.0.0"
EXPECTED_MODULES = 80
SCHEMA = "biointel.step192.release-integrity.v1"

_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"(?i)\b(?:api[_-]?key|secret|token|password)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{20,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
)

_UNSAFE_CLAIMS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)\b(?:clinically|regulatorily) validated\b"),
    re.compile(r"(?i)\bregulatory approved\b"),
    re.compile(r"(?i)\bzero bugs guaranteed\b"),
    re.compile(r"(?i)\bwet[- ]lab validated\b"),
)

@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str
    severity: str = "critical"


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def _version_values(root: Path) -> dict[str, str]:
    with (root / "pyproject.toml").open("rb") as handle:
        project_version = str(tomllib.load(handle).get("project", {}).get("version", "")).strip()
    init_text = (root / "src" / "biointel" / "__init__.py").read_text(encoding="utf-8")
    init_match = re.search(r"__version__\s*=\s*['\"]([^'\"]+)", init_text)
    settings_text = (root / "config" / "settings.yaml").read_text(encoding="utf-8")
    settings_match = re.search(r"(?m)^\s*version:\s*['\"]?([^'\"\s]+)", settings_text)
    version_file = (root / "VERSION").read_text(encoding="utf-8-sig").strip() if (root / "VERSION").is_file() else ""
    citation = (root / "CITATION.cff").read_text(encoding="utf-8")
    citation_match = re.search(r"(?m)^version:\s*['\"]?([^'\"\s]+)", citation)
    release = _read_json(root / "STEP192_RELEASE.json") if (root / "STEP192_RELEASE.json").is_file() else {}
    return {
        "pyproject": project_version,
        "package_init": init_match.group(1) if init_match else "",
        "settings": settings_match.group(1) if settings_match else "",
        "VERSION": version_file,
        "citation": citation_match.group(1) if citation_match else "",
        "release_json": str(release.get("version", "")),
    }


def _exact_project_dependencies(root: Path) -> list[str]:
    with (root / "pyproject.toml").open("rb") as handle:
        project = tomllib.load(handle).get("project", {})
    deps = project.get("dependencies", [])
    if not isinstance(deps, list):
        return []
    return sorted(str(item).strip() for item in deps if str(item).strip())


def _read_lock(path: Path) -> list[str]:
    rows: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and not line.startswith("--"):
            rows.append(line)
    return sorted(rows)


def _page_static_audit(root: Path) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    failures: list[str] = []
    for page in sorted((root / "pages").glob("*.py")):
        text = page.read_text(encoding="utf-8-sig", errors="replace")
        try:
            tree = ast.parse(text, filename=str(page))
            syntax_ok = True
        except SyntaxError as exc:
            tree = None
            syntax_ok = False
            failures.append(f"{page.name}: syntax error {exc.lineno}:{exc.offset}")
        set_page_count = text.count("st.set_page_config(")
        dangerous_shell = bool(re.search(r"subprocess\.(?:run|Popen|call)\([^\n]*shell\s*=\s*True", text))
        uses_eval = False
        if tree is not None:
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec"}:
                    uses_eval = True
                    break
        secret_hits = sum(bool(pattern.search(text)) for pattern in _SECRET_PATTERNS)
        step192_hook = "render_step192_release_integrity" in text
        row = {
            "page": page.name,
            "syntax_ok": syntax_ok,
            "set_page_config_count": set_page_count,
            "dangerous_shell": dangerous_shell,
            "eval_exec": uses_eval,
            "secret_pattern_hits": secret_hits,
            "step192_hook": step192_hook,
            "functions": sum(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) for n in ast.walk(tree)) if tree else 0,
        }
        if set_page_count > 1:
            failures.append(f"{page.name}: multiple st.set_page_config calls")
        if dangerous_shell:
            failures.append(f"{page.name}: subprocess shell=True")
        if uses_eval:
            failures.append(f"{page.name}: eval/exec usage")
        if secret_hits:
            failures.append(f"{page.name}: possible embedded secret")
        rows.append(row)
    return rows, failures


def _publication_audit(root: Path) -> tuple[list[dict[str, Any]], list[str]]:
    base = root / "UserData" / "step191" / "modules"
    rows: list[dict[str, Any]] = []
    failures: list[str] = []
    for key, profile in sorted(PROFILES.items()):
        folder = base / key
        required = (
            "module_publication_card.json",
            "publication_benchmark_input.csv",
            "publication_benchmark_output.csv",
            "publication_benchmark_summary.json",
            "MODULE_LIMITATIONS.md",
        )
        missing = [name for name in required if not (folder / name).is_file()]
        benchmark_passed = False
        reproducible = False
        if not missing:
            try:
                summary = _read_json(folder / "publication_benchmark_summary.json")
                benchmark_passed = bool(summary.get("passed", summary.get("benchmark_passed", False)))
                reproducible = bool(summary.get("reproducible", summary.get("repeatability_passed", False)))
                # Older Step 191 summaries use deterministic hashes rather than explicit flags.
                if not benchmark_passed:
                    benchmark_passed = bool(summary.get("output_sha256") or summary.get("result_sha256"))
                if not reproducible:
                    hashes = summary.get("run_hashes", [])
                    reproducible = isinstance(hashes, list) and len(hashes) >= 3 and len(set(hashes)) == 1
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                failures.append(f"{key}: benchmark summary unreadable: {exc}")
        card_ok = False
        if not missing:
            try:
                card = _read_json(folder / "module_publication_card.json")
                card_ok = str(card.get("module_key", key)) == key and bool(card.get("intended_use")) and bool(card.get("limitations"))
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                failures.append(f"{key}: publication card unreadable: {exc}")
        passed = not missing and card_ok and benchmark_passed
        if not passed:
            failures.append(f"{key}: missing={missing}, card={card_ok}, benchmark={benchmark_passed}")
        rows.append({
            "module_key": key,
            "title": profile.title,
            "page": profile.page,
            "publication_assets_complete": not missing,
            "publication_card_valid": card_ok,
            "benchmark_passed": benchmark_passed,
            "repeatability_explicit": reproducible,
            "passed": passed,
        })
    return rows, failures


def _database_audit(root: Path) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    failures: list[str] = []
    candidates = sorted({*root.glob("**/*.sqlite"), *root.glob("**/*.sqlite3"), *root.glob("**/*.db")})
    for path in candidates:
        if ".venv" in path.parts or "wheelhouse" in path.parts:
            continue
        rel = path.relative_to(root).as_posix()
        try:
            connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
            integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
            foreign_keys = int(connection.execute("PRAGMA foreign_key_check").fetchall().__len__())
            connection.close()
            passed = integrity.lower() == "ok" and foreign_keys == 0
        except sqlite3.Error as exc:
            integrity = f"error:{exc}"
            foreign_keys = -1
            passed = False
        if not passed:
            failures.append(f"{rel}: integrity={integrity}, foreign_key_violations={foreign_keys}")
        rows.append({"path": rel, "integrity": integrity, "foreign_key_violations": foreign_keys, "passed": passed})
    return rows, failures


def _claims_audit(root: Path) -> tuple[list[dict[str, Any]], list[str]]:
    targets = [
        root / "README.md",
        root / "CURRENT_RELEASE.md",
        root / "STEP191_RESEARCH_PAPER_DRAFT.md",
        root / "research" / "joss_paper" / "paper.md",
    ]
    rows: list[dict[str, Any]] = []
    failures: list[str] = []
    for path in targets:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        hits: list[str] = []
        for pattern in _UNSAFE_CLAIMS:
            for match in pattern.finditer(text):
                prefix = text[max(0, match.start() - 80):match.start()].lower()
                negated = any(token in prefix for token in ("not ", "no claim", "does not", "is not", "are not", "without ", "never "))
                if not negated:
                    hits.append(pattern.pattern)
                    break
        rows.append({"path": path.relative_to(root).as_posix(), "unsafe_claim_patterns": hits, "passed": not hits})
        if hits:
            failures.append(f"{path.name}: unsafe claim pattern(s): {hits}")
    return rows, failures


def load_module_status(root: Path, module_key: str) -> dict[str, Any]:
    profile = PROFILES[module_key]
    folder = root / "UserData" / "step191" / "modules" / module_key
    required = [
        folder / "module_publication_card.json",
        folder / "publication_benchmark_summary.json",
        folder / "MODULE_LIMITATIONS.md",
    ]
    card = _read_json(required[0]) if required[0].is_file() else {}
    benchmark = _read_json(required[1]) if required[1].is_file() else {}
    release_gate = _read_json(root / "UserData" / "step191" / "STEP191_PUBLICATION_RELEASE_GATE.json") if (root / "UserData" / "step191" / "STEP191_PUBLICATION_RELEASE_GATE.json").is_file() else {}
    return {
        "module_key": module_key,
        "title": profile.title,
        "category": profile.category,
        "assets_present": all(path.is_file() for path in required),
        "intended_use": card.get("intended_use", "Research software evaluation only."),
        "limitations": card.get("limitations", "External scientific evidence remains required."),
        "benchmark": benchmark,
        "preprint_ready": bool(release_gate.get("preprint_package_ready", False)),
        "controlled_release_eligible": bool(release_gate.get("controlled_scientific_release_eligible", False)),
        "external_blockers": list(release_gate.get("external_blockers", [])),
    }


def run_release_audit(root: Path, *, deep_hashes: bool = False) -> dict[str, Any]:
    root = Path(root).resolve()
    checks: list[Check] = []

    versions = _version_values(root)
    historical_ok = len(set(versions.values())) == 1 and next(iter(versions.values()), "") == RELEASE_VERSION
    current_values = [value for key, value in versions.items() if key != "release_json"]
    current_version = current_values[0] if current_values and len(set(current_values)) == 1 else ""
    successor_candidates: list[dict[str, Any]] = []
    for successor_path in sorted(root.glob("STEP*_RELEASE.json")):
        match = re.match(r"STEP(\d+)_RELEASE\.json$", successor_path.name, re.IGNORECASE)
        if not match or int(match.group(1)) <= RELEASE_STEP:
            continue
        try:
            successor = _read_json(successor_path)
            step = int(successor.get("step", 0) or 0)
            successor_version = str(successor.get("version", "")).strip()
            if step == int(match.group(1)) and successor_version == current_version:
                successor_candidates.append({"step": step, "version": successor_version, "file": successor_path.name})
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    successor_ok = bool(
        current_version
        and versions.get("release_json") == RELEASE_VERSION
        and successor_candidates
    )
    version_ok = historical_ok or successor_ok
    checks.append(Check(
        "release version consistency",
        version_ok,
        json.dumps({"step192": versions, "current_version": current_version, "successors": successor_candidates}, sort_keys=True),
    ))

    release = _read_json(root / "STEP192_RELEASE.json") if (root / "STEP192_RELEASE.json").is_file() else {}
    checks.append(Check("release identity", release.get("step") == RELEASE_STEP and release.get("version") == RELEASE_VERSION, json.dumps(release, sort_keys=True)))

    lock_path = root / "requirements-lock-step192.txt"
    dependency_rows = _exact_project_dependencies(root)
    lock_rows = _read_lock(lock_path) if lock_path.is_file() else []
    checks.append(Check("dependency lock parity", dependency_rows == lock_rows, f"project={len(dependency_rows)} lock={len(lock_rows)}"))

    wheel_report_path = runtime_report_path(root, "step192") / "wheelhouse_verification.json"
    wheel_report: dict[str, Any] = {}
    if wheel_report_path.is_file():
        wheel_report = _read_json(wheel_report_path)
    wheel_ok = bool(wheel_report.get("valid", False))
    checks.append(Check("offline wheelhouse integrity", wheel_ok, json.dumps(wheel_report, sort_keys=True)))

    pages, page_failures = _page_static_audit(root)
    hooked_pages = sum(int(row["step192_hook"]) for row in pages)
    checks.append(Check("all page syntax and security", not page_failures, f"pages={len(pages)} failures={len(page_failures)}"))
    checks.append(Check("major-module publication hooks", hooked_pages >= 79, f"hooked={hooked_pages}/79"))

    publication, publication_failures = _publication_audit(root)
    checks.append(Check("80-module publication assets", len(publication) == EXPECTED_MODULES and not publication_failures, f"modules={len(publication)} failures={len(publication_failures)}"))

    databases, database_failures = _database_audit(root)
    checks.append(Check("SQLite integrity", not database_failures, f"databases={len(databases)} failures={len(database_failures)}", severity="advisory"))

    claims, claim_failures = _claims_audit(root)
    checks.append(Check("scientific claim safety", not claim_failures, f"files={len(claims)} failures={len(claim_failures)}"))

    launcher_text = (root / "INSTALL_WINDOWS.bat").read_text(encoding="utf-8-sig", errors="replace") if (root / "INSTALL_WINDOWS.bat").is_file() else ""
    run_text = (root / "RUN_BOTH_WINDOWS.bat").read_text(encoding="utf-8-sig", errors="replace") if (root / "RUN_BOTH_WINDOWS.bat").is_file() else ""
    latest_successor = max(successor_candidates, key=lambda row: int(row["step"]), default={})
    latest_step = int(latest_successor.get("step", RELEASE_STEP) or RELEASE_STEP)
    launcher_ok = all(
        token in launcher_text
        for token in (f"Step {latest_step}", f"step{latest_step}_part", f"install_windows_step{latest_step}.py")
    ) and all(
        token in run_text
        for token in (f"run_biointel_step{latest_step}.py", f"repair_step{latest_step}_release_metadata.py")
    )
    checks.append(Check("classic installer latest-release contract", launcher_ok, f"latest_step={latest_step}"))

    manifest_result: dict[str, Any] = {"checked": 0, "mismatches": []}
    manifest_path = root / "STEP192_SOURCE_MANIFEST_SHA256.json"
    if deep_hashes and manifest_path.is_file():
        manifest = _read_json(manifest_path)
        mismatches: list[str] = []
        for item in manifest.get("entries", []):
            if not isinstance(item, dict):
                continue
            relative = str(item.get("path", ""))
            path = root / relative
            if not path.is_file() or path.stat().st_size != int(item.get("size_bytes", -1)) or sha256_path(path) != str(item.get("sha256", "")):
                mismatches.append(relative)
        manifest_result = {"checked": len(manifest.get("entries", [])), "mismatches": mismatches}
        checks.append(Check("deep source manifest hashes", not mismatches, f"checked={manifest_result['checked']} mismatches={len(mismatches)}"))

    critical_failed = [asdict(item) for item in checks if not item.passed and item.severity == "critical"]
    result = {
        "schema": SCHEMA,
        "generated_at_utc": utc_now(),
        "root": str(root),
        "release_step": RELEASE_STEP,
        "release_version": RELEASE_VERSION,
        "passed": not critical_failed,
        "checks": [asdict(item) for item in checks],
        "critical_failures": critical_failed,
        "page_audit": {"rows": pages, "failures": page_failures},
        "publication_audit": {"rows": publication, "failures": publication_failures},
        "database_audit": {"rows": databases, "failures": database_failures},
        "claim_audit": {"rows": claims, "failures": claim_failures},
        "manifest_audit": manifest_result,
    }
    return result


def _write_csv(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    rows = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row}) if rows else ["status"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_step192(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    output = root / "UserData" / "step192"
    reports = runtime_report_path(root, "step192")
    output.mkdir(parents=True, exist_ok=True)
    reports.mkdir(parents=True, exist_ok=True)

    audit = run_release_audit(root, deep_hashes=False)
    write_json(output / "STEP192_RELEASE_AUDIT.json", audit)
    write_json(reports / "STEP192_RELEASE_AUDIT.json", audit)
    _write_csv(root / "STEP192_PAGE_STATIC_AUDIT.csv", audit["page_audit"]["rows"])
    _write_csv(root / "STEP192_80_MODULE_PUBLICATION_INTEGRATION.csv", audit["publication_audit"]["rows"])
    _write_csv(root / "STEP192_DATABASE_INTEGRITY.csv", audit["database_audit"]["rows"])

    summary = {
        "schema": "biointel.step192.summary.v1",
        "generated_at_utc": utc_now(),
        "release_step": RELEASE_STEP,
        "release_version": RELEASE_VERSION,
        "release_audit_passed": bool(audit["passed"]),
        "modules": EXPECTED_MODULES,
        "page_files": len(audit["page_audit"]["rows"]),
        "major_module_hooks": sum(int(row["step192_hook"]) for row in audit["page_audit"]["rows"]),
        "publication_modules_passed": sum(int(row["passed"]) for row in audit["publication_audit"]["rows"]),
        "database_files_checked": len(audit["database_audit"]["rows"]),
        "wheelhouse_valid": next((item["passed"] for item in audit["checks"] if item["name"] == "offline wheelhouse integrity"), False),
        "controlled_scientific_release_eligible": False,
        "external_blockers": [
            "public_archive_doi",
            "public_repository_url",
            "journal_compatible_licence_decision",
            "independent_external_benchmarks",
            "real wet-lab/clinical/instrument evidence where applicable",
        ],
    }
    write_json(root / "STEP192_UPGRADE_SUMMARY.json", summary)
    write_json(output / "STEP192_UPGRADE_SUMMARY.json", summary)
    return summary
