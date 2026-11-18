from __future__ import annotations

import ast
import hashlib
import json
import re
import tomllib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PRODUCT_NAME = "BioIntel AI"
PRODUCT_VERSION = "15.6.0"
RELEASE_STEP = 216
PACKAGE_GENERATION = "V19.6.1"
PHYSICAL_RELEASE_STEP = 220
PHYSICAL_PACKAGE_GENERATION = "V20.5"
SOURCE_MANIFEST_NAME = "STEP220_SOURCE_MANIFEST_SHA256.json"
REQUIRED_PART_COUNT = 4
REQUIRED_PYTHON_TEXT = "CPython 3.11.x x64"
MIN_TRACKED_SOURCE_FILES = 10_000
SCHEMA = "biointel.step216.release-readiness.v1"
CLAIM_BOUNDARY = (
    "Step216 is a software release-readiness upgrade. It does not claim clinical, "
    "regulatory, wet-lab, external-engine, model-weight or public-internet qualification."
)


@dataclass(frozen=True)
class ReadinessCheck:
    name: str
    passed: bool
    severity: str
    detail: Any

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "severity": self.severity,
            "detail": self.detail,
        }


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return ""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _pyproject_version(root: Path) -> str:
    try:
        with (root / "pyproject.toml").open("rb") as handle:
            return str(tomllib.load(handle).get("project", {}).get("version", "")).strip()
    except (OSError, tomllib.TOMLDecodeError):
        return ""


def _python_package_version(root: Path) -> str:
    text = _read_text(root / "src" / "biointel" / "__init__.py")
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return ""
    for node in tree.body:
        if isinstance(node, ast.Assign):
            names = [target.id for target in node.targets if isinstance(target, ast.Name)]
            if "__version__" in names and isinstance(node.value, ast.Constant):
                return str(node.value.value).strip()
    return ""


def _citation_version(root: Path) -> str:
    for line in _read_text(root / "CITATION.cff").splitlines():
        if line.strip().startswith("version:"):
            return line.split(":", 1)[1].strip().strip("\"'")
    return ""


def _regex_constant(text: str, name: str) -> str:
    match = re.search(rf"^{re.escape(name)}\s*=\s*(.+?)\s*$", text, flags=re.MULTILINE)
    if not match:
        return ""
    raw = match.group(1).strip()
    if raw.startswith(("'", '"')) and raw.endswith(("'", '"')):
        return raw[1:-1]
    return raw


def _wheelhouse_status(root: Path, *, deep_hashes: bool) -> dict[str, Any]:
    wheelhouse = root / "wheelhouse" / "windows-cp311-x64"
    wheels = sorted(wheelhouse.glob("*.whl")) if wheelhouse.is_dir() else []
    names = [path.name.lower() for path in wheels]
    required_prefixes = (
        "streamlit-",
        "fastapi-",
        "pandas-",
        "numpy-",
        "scipy-",
        "scikit_learn-",
        "rdkit-",
        "biopython-",
        "pydantic-",
        "uvicorn-",
    )
    missing = [prefix for prefix in required_prefixes if not any(name.startswith(prefix) for name in names)]
    manifest_path = wheelhouse / "MANIFEST_SHA256.txt"
    bad_hashes: list[str] = []
    checked_hashes = 0
    if deep_hashes and manifest_path.is_file():
        for raw in manifest_path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            expected, name = parts[0], parts[-1].lstrip("*")
            target = wheelhouse / name
            if not target.is_file() or _sha256_file(target) != expected:
                bad_hashes.append(name)
            checked_hashes += 1
    return {
        "path": str(wheelhouse),
        "wheel_count": len(wheels),
        "missing_required_prefixes": missing,
        "manifest_present": manifest_path.is_file(),
        "deep_hashes": deep_hashes,
        "checked_hashes": checked_hashes,
        "bad_hashes": bad_hashes[:25],
    }


def _source_manifest_status(
    root: Path,
    manifest_name: str,
    *,
    deep_hashes: bool,
) -> dict[str, Any]:
    manifest = _read_json(root / manifest_name)
    rows = manifest.get("entries", [])
    bad: list[str] = []
    checked_hashes = 0
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                bad.append("<invalid-row>")
                continue
            rel = str(row.get("path", ""))
            target = root / rel
            expected_size = int(row.get("size_bytes", -1))
            if not target.is_file() or target.stat().st_size != expected_size:
                bad.append(rel)
                continue
            if deep_hashes:
                checked_hashes += 1
                if _sha256_file(target) != str(row.get("sha256", "")):
                    bad.append(rel)
    else:
        bad.append("<entries-not-list>")
    return {
        "manifest": manifest_name,
        "schema": manifest.get("schema", ""),
        "release_step": manifest.get("release_step"),
        "package_generation": manifest.get("package_generation"),
        "part_count": manifest.get("part_count"),
        "tracked_files": len(rows) if isinstance(rows, list) else 0,
        "deep_hashes": deep_hashes,
        "checked_hashes": checked_hashes,
        "bad_count": len(bad),
        "bad_files": bad[:25],
    }


def _version_surface(root: Path) -> dict[str, str]:
    return {
        "VERSION": _read_text(root / "VERSION").strip(),
        "pyproject.toml": _pyproject_version(root),
        "src/biointel/__init__.py": _python_package_version(root),
        "platform/desktop/package.json": str(
            _read_json(root / "platform" / "desktop" / "package.json").get("version", "")
        ).strip(),
        "codemeta.json": str(_read_json(root / "codemeta.json").get("version", "")).strip(),
        "CITATION.cff": _citation_version(root),
    }


def scan_release_readiness(root: str | Path, *, deep_hashes: bool = False) -> dict[str, Any]:
    project = Path(root).resolve()
    checks: list[ReadinessCheck] = []

    def add(name: str, passed: bool, detail: Any, *, severity: str = "blocker") -> None:
        checks.append(ReadinessCheck(name=name, passed=bool(passed), severity=severity, detail=detail))

    versions = _version_surface(project)
    add(
        "product version surface",
        all(value == PRODUCT_VERSION for value in versions.values()),
        versions,
    )

    contract = _read_text(project / "scripts" / "step206_contract.py")
    contract_detail = {
        "PRODUCT_VERSION": _regex_constant(contract, "PRODUCT_VERSION"),
        "RELEASE_STEP": _regex_constant(contract, "RELEASE_STEP"),
        "PACKAGE_GENERATION": _regex_constant(contract, "PACKAGE_GENERATION"),
        "PART_COUNT": _regex_constant(contract, "PART_COUNT"),
        "REQUIRED_PYTHON_TEXT": _regex_constant(contract, "REQUIRED_PYTHON_TEXT"),
        "MANIFEST_NAME": _regex_constant(contract, "MANIFEST_NAME"),
    }
    add(
        "physical installer contract preserved",
        contract_detail == {
            "PRODUCT_VERSION": PRODUCT_VERSION,
            "RELEASE_STEP": str(PHYSICAL_RELEASE_STEP),
            "PACKAGE_GENERATION": PHYSICAL_PACKAGE_GENERATION,
            "PART_COUNT": str(REQUIRED_PART_COUNT),
            "REQUIRED_PYTHON_TEXT": REQUIRED_PYTHON_TEXT,
            "MANIFEST_NAME": SOURCE_MANIFEST_NAME,
        },
        contract_detail,
    )

    markers = [
        f".release_parts/step{PHYSICAL_RELEASE_STEP}_part{part}.ok"
        for part in range(1, REQUIRED_PART_COUNT + 1)
    ]
    missing_markers = [item for item in markers if not (project / item).is_file()]
    add("four-part extraction markers", not missing_markers, missing_markers or markers)

    source_manifest = _source_manifest_status(
        project,
        SOURCE_MANIFEST_NAME,
        deep_hashes=deep_hashes,
    )
    add(
        "current source manifest compatible",
        source_manifest["release_step"] == PHYSICAL_RELEASE_STEP
        and source_manifest["package_generation"] == PHYSICAL_PACKAGE_GENERATION
        and source_manifest["part_count"] == REQUIRED_PART_COUNT
        and source_manifest["tracked_files"] >= MIN_TRACKED_SOURCE_FILES
        and source_manifest["bad_count"] == 0,
        source_manifest,
    )

    wheelhouse = _wheelhouse_status(project, deep_hashes=deep_hashes)
    add(
        "offline Windows cp311 wheelhouse",
        wheelhouse["wheel_count"] >= 100
        and not wheelhouse["missing_required_prefixes"]
        and wheelhouse["manifest_present"]
        and not wheelhouse["bad_hashes"],
        wheelhouse,
    )

    readme = _read_text(project / "README.md")
    current_release = _read_text(project / "CURRENT_RELEASE.md")
    step216 = _read_text(project / "CHANGELOG_STEP216_RELEASE_READINESS.md")
    docs_detail = {
        "readme_step216": "Step216" in readme,
        "current_release_step216": "Step216" in current_release,
        "engine_platform_retained": any(marker in readme + current_release for marker in ("Engine Control Center", "Engine Platform")),
        "four_part_workflow_retained": ("all four" in readme.lower() or "4 parts" in readme.lower()),
        "step216_changelog": bool(step216.strip()),
    }
    add("Step216 documentation", all(docs_detail.values()), docs_detail)

    status_page = _read_text(project / "pages" / "9_Project_Status.py")
    add(
        "Project Status readiness panel",
        "scan_release_readiness" in status_page and "readiness_table_rows" in status_page,
        {"page": "pages/9_Project_Status.py"},
    )

    controls = [
        "VERIFY_STEP216_RELEASE_READINESS_WINDOWS.bat",
        "scripts/step216_release_readiness.py",
        "REPAIR_WINDOWS.bat",
        "DIAGNOSE_WINDOWS.bat",
        "SAFE_MODE_WINDOWS.bat",
        "UNINSTALL_BIOINTEL_WINDOWS.bat",
        "RUN_ULTIMATE_ACCEPTANCE_WINDOWS.bat",
    ]
    missing_controls = [item for item in controls if not (project / item).is_file()]
    add("upgrade and recovery controls", not missing_controls, missing_controls or controls)

    provenance = _read_json(project / "BUILD_PROVENANCE.json")
    add(
        "build provenance upgraded",
        provenance.get("schema") in {
            "biointel.build-provenance.v216",
            "biointel.build-provenance.v217",
        }
        and int(provenance.get("release_step", 0) or 0) >= RELEASE_STEP
        and provenance.get("version") == PRODUCT_VERSION,
        {
            "schema": provenance.get("schema"),
            "release_step": provenance.get("release_step"),
            "version": provenance.get("version"),
            "release": provenance.get("release"),
        },
    )

    boundary_text = "\n".join([readme, current_release, step216, CLAIM_BOUNDARY]).casefold()
    boundary_ok = (
        "not clinical" in boundary_text
        and "external engines remain unqualified" in boundary_text
        and "target-machine evidence" in boundary_text
    )
    add(
        "qualification boundary explicit",
        boundary_ok,
        {
            "not_clinical": "not clinical" in boundary_text,
            "external_engines_unqualified": "external engines remain unqualified" in boundary_text,
            "target_machine_evidence": "target-machine evidence" in boundary_text,
        },
    )

    total = len(checks)
    passed_count = sum(1 for check in checks if check.passed)
    blockers = [check.name for check in checks if not check.passed and check.severity == "blocker"]
    warnings = [check.name for check in checks if not check.passed and check.severity != "blocker"]
    return {
        "schema": SCHEMA,
        "product": PRODUCT_NAME,
        "version": PRODUCT_VERSION,
        "release_step": RELEASE_STEP,
        "package_generation": PACKAGE_GENERATION,
        "physical_release_step": PHYSICAL_RELEASE_STEP,
        "physical_package_generation": PHYSICAL_PACKAGE_GENERATION,
        "generated_at_utc": utc_now(),
        "root": str(project),
        "passed": not blockers,
        "score_percent": round((passed_count / total) * 100, 1) if total else 0.0,
        "checks_passed": passed_count,
        "checks_total": total,
        "blockers": blockers,
        "warnings": warnings,
        "claim_boundary": CLAIM_BOUNDARY,
        "checks": [check.as_dict() for check in checks],
    }


def readiness_table_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for check in report.get("checks", []):
        detail = check.get("detail")
        if isinstance(detail, (dict, list)):
            detail_text = json.dumps(detail, sort_keys=True, default=str)
        else:
            detail_text = str(detail)
        rows.append(
            {
                "Check": str(check.get("name", "")),
                "Status": "Pass" if check.get("passed") else "Review",
                "Severity": str(check.get("severity", "")),
                "Detail": detail_text[:700],
            }
        )
    return rows


def write_readiness_report(
    root: str | Path,
    *,
    output: str | Path | None = None,
    deep_hashes: bool = False,
) -> Path:
    project = Path(root).resolve()
    report = scan_release_readiness(project, deep_hashes=deep_hashes)
    target = Path(output) if output is not None else project / "reports" / "step216_release_readiness.json"
    if not target.is_absolute():
        target = project / target
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(target)
    return target