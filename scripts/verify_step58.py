from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.engineering.repository_audit import scan_repository_secrets
from biointel.ui.aesthetic import AESTHETIC_LAYER_ID, premium_aesthetic_css
from biointel.ui.style_catalog import FONTS, THEMES

REQUIRED_UI_MARKERS = (
    AESTHETIC_LAYER_ID,
    "Step 58 · premium adaptive visual system",
    ".bio-hero",
    ".bio-shell-bar",
    '[data-testid="stSidebar"]',
    '[data-testid="stMetric"]',
    '[data-testid="stFileUploaderDropzone"]',
    '[data-testid="stPlotlyChart"]',
    '[data-testid="stDataFrame"]',
    '[data-testid="stDialog"]',
    "@media (prefers-reduced-motion: reduce)",
    "@media (prefers-contrast: more)",
    "@media (forced-colors: active)",
    "@media (max-width: 760px)",
)


def _run(command: list[str], root: Path) -> None:
    subprocess.run(command, cwd=root, check=True)


def _database_health(root: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for database in sorted((root / "reports").glob("*.sqlite3")):
        with sqlite3.connect(f"file:{database.as_posix()}?mode=ro&immutable=1", uri=True) as connection:
            integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
            foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
        rows.append(
            {
                "path": database.relative_to(root).as_posix(),
                "integrity": integrity,
                "foreign_key_violations": len(foreign_keys),
            }
        )
    return rows



def _remove_sqlite_residue(root: Path) -> list[str]:
    removed: list[str] = []
    for pattern in ("*.sqlite3-wal", "*.sqlite3-shm", "*.db-wal", "*.db-shm"):
        for path in root.rglob(pattern):
            removed.append(path.relative_to(root).as_posix())
            path.unlink(missing_ok=True)
    return sorted(removed)

def _screen_health(root: Path) -> dict[str, object]:
    screens = [root / "app.py", *sorted((root / "pages").glob("*.py"))]
    missing_theme: list[str] = []
    missing_hero: list[str] = []
    for screen in screens:
        source = screen.read_text(encoding="utf-8")
        relative = screen.relative_to(root).as_posix()
        if "apply_theme()" not in source:
            missing_theme.append(relative)
        if "hero(" not in source:
            missing_hero.append(relative)
    return {
        "screen_count": len(screens),
        "missing_theme": missing_theme,
        "missing_hero": missing_hero,
    }


def _css_health() -> dict[str, object]:
    samples = 0
    missing_markers: dict[str, list[str]] = {}
    unbalanced: list[str] = []
    external_dependencies: list[str] = []
    for theme in THEMES.values():
        for font in FONTS.values():
            css = premium_aesthetic_css(theme, font)
            key = f"{theme.name}/{font.name}"
            samples += 1
            missing = [marker for marker in REQUIRED_UI_MARKERS if marker not in css]
            if missing:
                missing_markers[key] = missing
            if css.count("{") != css.count("}"):
                unbalanced.append(key)
            lowered = css.lower()
            if "https://" in lowered or "http://" in lowered or "@import" in lowered:
                external_dependencies.append(key)
    return {
        "samples": samples,
        "missing_markers": missing_markers,
        "unbalanced": unbalanced,
        "external_dependencies": external_dependencies,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify BioIntel AI Step 58 aesthetic UI release.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--json-output", default="reports/step58_local_verification.json")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    _run([sys.executable, "-m", "ruff", "check", "."], root)
    _run(
        [
            sys.executable,
            "-m",
            "compileall",
            "-q",
            "app.py",
            "pages",
            "src",
            "scripts",
            "platform",
        ],
        root,
    )
    if not args.skip_tests:
        _run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "tests/test_step58_aesthetic_ui.py",
                "tests/test_step46_ui_excellence.py",
                "tests/test_step45_distributed_ui.py",
                "tests/test_step56_store_release.py",
                "tests/test_step43_final_assurance.py",
            ],
            root,
        )

    removed_residue = _remove_sqlite_residue(root)
    css = _css_health()
    screens = _screen_health(root)
    databases = _database_health(root)
    residue = sorted(
        path.relative_to(root).as_posix()
        for pattern in ("*.sqlite3-wal", "*.sqlite3-shm", "*.db-wal", "*.db-shm")
        for path in root.rglob(pattern)
    )
    secrets = scan_repository_secrets(root)

    result = {
        "release": "BioIntel AI Step 58 Premium Aesthetic UI & Error Hardening",
        "theme_count": len(THEMES),
        "font_count": len(FONTS),
        "css_combinations_verified": css["samples"],
        "css_missing_markers": css["missing_markers"],
        "css_unbalanced": css["unbalanced"],
        "css_external_dependencies": css["external_dependencies"],
        "screen_count": screens["screen_count"],
        "screens_missing_theme": screens["missing_theme"],
        "screens_missing_hero": screens["missing_hero"],
        "ruff": "passed",
        "python_compilation": "passed",
        "focused_regression": "skipped" if args.skip_tests else "passed",
        "database_count": len(databases),
        "healthy_databases": sum(row["integrity"] == "ok" for row in databases),
        "foreign_key_violations": sum(
            int(row["foreign_key_violations"]) for row in databases
        ),
        "sqlite_runtime_residue_removed": removed_residue,
        "sqlite_runtime_residue": residue,
        "secret_scan": secrets,
        "databases": databases,
    }

    output = root / args.json_output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))

    passed = (
        result["theme_count"] == 17
        and result["font_count"] == 11
        and result["css_combinations_verified"] == 187
        and not result["css_missing_markers"]
        and not result["css_unbalanced"]
        and not result["css_external_dependencies"]
        and result["screen_count"] >= 89
        and not result["screens_missing_theme"]
        and not result["screens_missing_hero"]
        and result["healthy_databases"] == result["database_count"]
        and result["foreign_key_violations"] == 0
        and not residue
        and bool(secrets["passed"])
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
