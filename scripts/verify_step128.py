from __future__ import annotations

import compileall
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.nextgen.biomedical_expansion import NEW_BIOMEDICAL_KEYS
from biointel.nextgen.catalog import MODULE_BY_KEY
from biointel.nextgen.scientific import analyse, demo_frame, normalise
from biointel.scientific_depth import profile_for
from biointel.ui.navigation import PAGE_BY_KEY

REPORT = ROOT / "reports" / "step128_next_generation_verification.json"


def check(name: str, passed: bool, detail: str) -> dict[str, object]:
    return {"name": name, "passed": bool(passed), "detail": detail}


def database_health() -> tuple[int, int, int, list[str]]:
    healthy = total = rows = 0
    errors: list[str] = []
    candidates = sorted({*ROOT.rglob("*.sqlite3"), *ROOT.rglob("*.sqlite"), *ROOT.rglob("*.db")})
    for path in candidates:
        if any(part in {".venv", "wheelhouse", "node_modules"} for part in path.parts):
            continue
        total += 1
        try:
            connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
            if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("integrity_check failed")
            for (table,) in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
                try:
                    rows += int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
                except sqlite3.DatabaseError:
                    pass
            connection.close()
            healthy += 1
        except Exception as exc:
            errors.append(f"{path.relative_to(ROOT)}: {exc}")
    return healthy, total, rows, errors


def main() -> int:
    checks: list[dict[str, object]] = []
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    checks.append(check("version", version == "13.2.0", f"VERSION={version}"))

    checks.append(check("module catalogue", len(NEW_BIOMEDICAL_KEYS) == 15 and NEW_BIOMEDICAL_KEYS.issubset(MODULE_BY_KEY), f"{len(NEW_BIOMEDICAL_KEYS)} modules"))

    missing_pages: list[str] = []
    missing_navigation: list[str] = []
    missing_profiles: list[str] = []
    analysis_failures: list[str] = []
    for key in sorted(NEW_BIOMEDICAL_KEYS):
        module = MODULE_BY_KEY[key]
        page = PAGE_BY_KEY.get(key)
        if page is None:
            missing_navigation.append(key)
        elif not (ROOT / page.path).is_file():
            missing_pages.append(page.path)
        if profile_for(key) is None:
            missing_profiles.append(key)
        try:
            data = normalise(demo_frame(module, 120), module)
            result, summary, _, _ = analyse(data, module, 0.7)
            if data.empty or result.empty or summary.get("module") != key:
                analysis_failures.append(key)
        except Exception as exc:
            analysis_failures.append(f"{key}: {exc}")
    checks.append(check("pages and navigation", not missing_pages and not missing_navigation, f"missing_pages={missing_pages}; missing_navigation={missing_navigation}"))
    checks.append(check("scientific depth profiles", not missing_profiles, f"missing={missing_profiles}"))
    checks.append(check("deterministic analysis", not analysis_failures, f"failures={analysis_failures}"))

    hub_ok = (ROOT / "pages/188_Next_Generation_Biomedical_Modules_Hub.py").is_file() and "next_generation_biomedical_hub" in PAGE_BY_KEY
    checks.append(check("module hub", hub_ok, "Step 128 hub registered"))

    starter_manifest = ROOT / "data/module_starter_kits/step128_next_generation/manifest.json"
    starter_ok = False
    starter_detail = "missing"
    if starter_manifest.is_file():
        payload = json.loads(starter_manifest.read_text(encoding="utf-8"))
        items = payload.get("modules", [])
        missing = [item.get("starter_file") for item in items if not (ROOT / str(item.get("starter_file", ""))).is_file()]
        starter_ok = len(items) == 15 and not missing
        starter_detail = f"{len(items)} kits; missing={missing}"
    checks.append(check("starter kits", starter_ok, starter_detail))

    release = json.loads((ROOT / "STEP128_RELEASE.json").read_text(encoding="utf-8"))
    config = json.loads((ROOT / "config/step128_next_generation_modules.json").read_text(encoding="utf-8"))
    checks.append(check("release configuration", release.get("version") == "13.2.0" and release.get("new_modules") == 15 and config.get("module_count") == 15, "release and config aligned"))

    compile_ok = compileall.compile_dir(ROOT / "src", quiet=1) and compileall.compile_dir(ROOT / "pages", quiet=1)
    checks.append(check("python compilation", compile_ok, "src and pages syntax compilation"))

    healthy, total, rows, errors = database_health()
    checks.append(check("database integrity", total > 0 and healthy == total, f"{healthy}/{total} healthy · {rows} rows · errors={errors[:3]}"))

    passed = all(bool(item["passed"]) for item in checks)
    report = {
        "schema": "biointel.step128.verification.v1",
        "version": version,
        "created_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "passed": passed,
        "new_module_count": len(NEW_BIOMEDICAL_KEYS),
        "checks": checks,
        "database_count": total,
        "database_rows": rows,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for item in checks:
        print(("PASS" if item["passed"] else "FAIL"), item["name"], "-", item["detail"])
    print("REPORT", REPORT)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
