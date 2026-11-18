from __future__ import annotations

import hashlib
import json
from pathlib import Path

from biointel.release_integrity_v192.audit import (
    EXPECTED_MODULES,
    RELEASE_VERSION,
    _exact_project_dependencies,
    _read_lock,
    run_release_audit,
)
from biointel.scientific_execution_v190.catalog import PROFILES

ROOT = Path(__file__).resolve().parents[1]


def test_step192_profiles_cover_80_modules() -> None:
    assert EXPECTED_MODULES == 80
    assert len(PROFILES) == 80


def test_step192_release_audit_passes() -> None:
    result = run_release_audit(ROOT, deep_hashes=False)
    assert result["passed"], result["critical_failures"]


def test_step192_publication_assets_cover_all_modules() -> None:
    result = run_release_audit(ROOT, deep_hashes=False)
    rows = result["publication_audit"]["rows"]
    assert len(rows) == 80
    assert all(row["passed"] for row in rows)


def test_step192_major_module_pages_are_hooked() -> None:
    pages = list((ROOT / "pages").glob("*.py"))
    hooked = [page for page in pages if "render_step192_release_integrity" in page.read_text(encoding="utf-8-sig", errors="replace")]
    assert len(hooked) == 79


def test_step192_dependency_lock_matches_pyproject() -> None:
    assert _exact_project_dependencies(ROOT) == _read_lock(ROOT / "requirements-lock-step192.txt")


def test_step192_version_is_consistent() -> None:
    result = run_release_audit(ROOT, deep_hashes=False)
    check = next(item for item in result["checks"] if item["name"] == "release version consistency")
    assert check["passed"]
    assert RELEASE_VERSION == "15.0.0"


def test_step192_wheelhouse_repaired() -> None:
    wheel = ROOT / "wheelhouse" / "windows-cp311-x64" / "scipy-1.17.0-cp311-cp311-win_amd64.whl"
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    assert digest == "255c0da161bd7b32a6c898e7891509e8a9289f0b1c6c7d96142ee0d2b114c2ea"
    report = json.loads((ROOT / "reports" / "step192" / "wheelhouse_verification.json").read_text(encoding="utf-8"))
    assert report["valid"] is True


def test_step192_release_stays_fail_closed() -> None:
    release = json.loads((ROOT / "STEP192_RELEASE.json").read_text(encoding="utf-8"))
    assert release["controlled_scientific_release_eligible"] is False
    assert release["external_blockers"]
