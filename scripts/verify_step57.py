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
from biointel.ui.style_catalog import FONTS, THEMES


def _luminance(hex_colour: str) -> float:
    channels = [int(hex_colour[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [
        value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
        for value in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(first: str, second: str) -> float:
    first_luminance = _luminance(first)
    second_luminance = _luminance(second)
    lighter = max(first_luminance, second_luminance)
    darker = min(first_luminance, second_luminance)
    return (lighter + 0.05) / (darker + 0.05)


def _database_health(root: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for database in sorted((root / "reports").glob("*.sqlite3")):
        with sqlite3.connect(database) as connection:
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


def _run(command: list[str], root: Path) -> None:
    subprocess.run(command, cwd=root, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify BioIntel AI Step 57 themes and fonts.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--json-output", default="reports/step57_local_verification.json")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    _run([sys.executable, "-m", "ruff", "check", "."], root)
    _run([sys.executable, "-m", "compileall", "-q", "app.py", "pages", "src", "scripts"], root)
    if not args.skip_tests:
        _run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "tests/test_step11_ui.py",
                "tests/test_step12_experience.py",
                "tests/test_step50_runtime_repair.py",
                "tests/test_step56_store_release.py",
            ],
            root,
        )

    contrast_failures = []
    for theme in THEMES.values():
        if _contrast(theme.text, theme.bg_start) < 7.0:
            contrast_failures.append(f"{theme.name}:text")
        if _contrast(theme.muted, theme.bg_start) < 4.5:
            contrast_failures.append(f"{theme.name}:muted")

    databases = _database_health(root)
    secrets = scan_repository_secrets(root)
    result = {
        "release": "BioIntel AI Step 57 Theme & Typography Expansion",
        "theme_count": len(THEMES),
        "new_theme_count": sum(theme.is_new for theme in THEMES.values()),
        "font_count": len(FONTS),
        "new_font_count": sum(font.is_new for font in FONTS.values()),
        "remote_font_dependencies": sum(
            "http" in font.css_stack.lower() for font in FONTS.values()
        ),
        "contrast_failures": contrast_failures,
        "ruff": "passed",
        "python_compilation": "passed",
        "focused_regression": "skipped" if args.skip_tests else "passed",
        "database_count": len(databases),
        "healthy_databases": sum(row["integrity"] == "ok" for row in databases),
        "foreign_key_violations": sum(
            int(row["foreign_key_violations"]) for row in databases
        ),
        "secret_scan": secrets,
        "databases": databases,
    }
    output = root / args.json_output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))

    passed = (
        result["theme_count"] == 17
        and result["new_theme_count"] == 10
        and result["font_count"] == 11
        and result["new_font_count"] == 10
        and result["remote_font_dependencies"] == 0
        and not contrast_failures
        and result["healthy_databases"] == result["database_count"]
        and result["foreign_key_violations"] == 0
        and bool(secrets["passed"])
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
