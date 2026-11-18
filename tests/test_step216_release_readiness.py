from __future__ import annotations

from pathlib import Path

from biointel.release_readiness_v216 import (
    PHYSICAL_RELEASE_STEP,
    PRODUCT_VERSION,
    RELEASE_STEP,
    readiness_table_rows,
    scan_release_readiness,
)

ROOT = Path(__file__).resolve().parents[1]


def test_step216_readiness_passes_quick_scan() -> None:
    report = scan_release_readiness(ROOT, deep_hashes=False)
    assert report["release_step"] == RELEASE_STEP == 216
    assert report["physical_release_step"] == PHYSICAL_RELEASE_STEP == 220
    assert report["version"] == PRODUCT_VERSION == "15.6.0"
    assert report["passed"], report


def test_step216_table_rows_are_project_status_ready() -> None:
    rows = readiness_table_rows(scan_release_readiness(ROOT, deep_hashes=False))
    assert rows
    assert {"Check", "Status", "Severity", "Detail"} <= set(rows[0])
    assert any(row["Check"] == "Project Status readiness panel" for row in rows)


def test_step216_keeps_scientific_boundary_explicit() -> None:
    changelog = (ROOT / "CHANGELOG_STEP216_RELEASE_READINESS.md").read_text(encoding="utf-8")
    normalized = " ".join(changelog.split()).casefold()
    assert "not clinical" in normalized
    assert "external engines remain unqualified" in normalized
    assert "target-machine evidence" in normalized