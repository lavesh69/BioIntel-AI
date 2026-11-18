from __future__ import annotations

import hashlib
import json
import py_compile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_VERSION = "13.2.0"
PREMIUM_THEMES = {
    "Genomic Aurora",
    "Midnight Laboratory",
    "Clinical White",
    "Molecular Glass",
    "Cyber Biotech",
    "Oceanic Research",
    "Cellular Green",
    "Protein Violet",
    "Minimal Scientific",
    "High-Contrast Research",
}
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


def check(name: str, passed: bool, detail: str) -> dict[str, object]:
    return {"name": name, "passed": bool(passed), "detail": detail}


def main() -> int:
    import sys

    sys.path.insert(0, str(ROOT / "src"))
    from biointel.ui.appearance_engine import CHART_PROFILES, LIGHT_THEMES, THEME_META
    from biointel.ui.experience_themes import EXPERIENCES
    from biointel.ui.premium_visuals import premium_theme_names
    from biointel.ui.style_catalog import FONTS, THEMES

    checks: list[dict[str, object]] = []
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    checks.append(check("version", version == EXPECTED_VERSION, version))

    theme_sets_equal = set(THEMES) == set(LIGHT_THEMES) == set(THEME_META) == set(CHART_PROFILES) == set(EXPERIENCES)
    checks.append(check("theme catalogue", theme_sets_equal and len(THEMES) == 42, f"themes={len(THEMES)} fonts={len(FONTS)}"))
    requested = set(premium_theme_names())
    checks.append(check("premium themes", requested == PREMIUM_THEMES and requested <= set(THEMES), f"{len(requested)}/10"))

    required_files = (
        "src/biointel/ui/premium_visuals.py",
        "src/biointel/ui/premium_visuals.css",
        "config/step124_premium_visual_system.json",
        "tests/test_step124_premium_visual_system.py",
        "VERIFY_STEP124_WINDOWS.bat",
    )
    missing = [rel for rel in required_files if not (ROOT / rel).is_file()]
    checks.append(check("premium files", not missing, "missing=" + ",".join(missing) if missing else "all present"))

    css = (ROOT / "src/biointel/ui/premium_visuals.css").read_text(encoding="utf-8")
    css_tokens = (
        "pv-background-drift",
        "bio-premium-hero",
        "bio-workflow-ribbon",
        "backdrop-filter",
        "prefers-reduced-motion",
        "forced-colors",
    )
    absent = [token for token in css_tokens if token not in css]
    checks.append(check("visual CSS", not absent, "missing=" + ",".join(absent) if absent else "animations, glass and accessibility present"))

    renderer = (ROOT / "src/biointel/ui/theme.py").read_text(encoding="utf-8")
    workspace = (ROOT / "src/biointel/ui/module_experience_2_9.py").read_text(encoding="utf-8")
    checks.append(check("global integration", all(token in renderer for token in ("premium_visuals.css", "premium_hero_inner_html", "svg_icon_html")), "hero/icon/CSS integration"))
    checks.append(check("before-after integration", "render_before_after_comparison(" in workspace, "interactive workspace comparison"))

    compile_targets = [
        ROOT / "src/biointel/ui/premium_visuals.py",
        ROOT / "src/biointel/ui/style_catalog.py",
        ROOT / "src/biointel/ui/appearance_engine.py",
        ROOT / "src/biointel/ui/experience_themes.py",
        ROOT / "src/biointel/ui/theme.py",
        ROOT / "src/biointel/ui/module_experience_2_9.py",
        ROOT / "pages/24_Appearance_Studio.py",
    ]
    compile_errors: list[str] = []
    for target in compile_targets:
        try:
            py_compile.compile(str(target), doraise=True)
        except py_compile.PyCompileError as exc:
            compile_errors.append(f"{target.name}: {exc}")
    checks.append(check("Python compilation", not compile_errors, "; ".join(compile_errors) if compile_errors else f"{len(compile_targets)}/{len(compile_targets)}"))

    locked_results = []
    for rel, expected in LOCKED.items():
        actual = sha256(ROOT / rel)
        locked_results.append({"path": rel, "expected": expected, "actual": actual, "byte_identical": actual == expected})
    checks.append(check("locked modules", all(item["byte_identical"] for item in locked_results), f"{sum(item['byte_identical'] for item in locked_results)}/{len(locked_results)} byte-identical"))

    report = {
        "schema": "biointel.step124-verification.v1",
        "version": version,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "checks": checks,
        "locked_modules": locked_results,
        "passed": all(item["passed"] for item in checks),
    }
    output = ROOT / "reports/step124_premium_visual_verification.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    for item in checks:
        print(("PASS" if item["passed"] else "FAIL") + f" | {item['name']} | {item['detail']}")
    print(f"REPORT | {output.relative_to(ROOT)}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
