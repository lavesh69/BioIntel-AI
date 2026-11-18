from __future__ import annotations

import compileall
import hashlib
import json
import sqlite3
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.step127 import ALL_MODULE_SPECS, assess_module, build_protected_plan
from biointel.step127.domain_checks import audit_fastq_pairs, normalize_variant

REPORT = ROOT / "reports" / "step127_scientific_depth_verification.json"
EXPECTED_LOCKED = {
    "pages/6_DTI_Predictor.py": "84b3ecec1356b7239a057459210af4cd130c57c08dd9449b7239d1fe5954e0cc",
    "pages/74_DTI_Validation_Evidence_Center.py": "a700a8a21649b49cf0e3a1521d2afad45039b83b767c2fe730b93fee7d4f7f11",
    "pages/109_Lab_Instrument_Import_Center.py": "22b5aba5bfea37bb1ef330ed7cca3773467463f883189602d96a0151311c8f70",
    "pages/126_LIMS_ELN_and_Sample_Chain_of_Custody_Hub.py": "eadaef1a283a5fa11ce6b243aa561508ba9ceba9f6fdcc207f4853ccf7d86905",
    "pages/157_Instrument_Integration_Hub_2.py": "cf3a5f94756def0007dbff31184ec276d90b03fc6d6e1ca792c87189e5ab7d6d",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(name: str, passed: bool, detail: str) -> dict[str, object]:
    return {"name": name, "passed": bool(passed), "detail": detail}


def database_health() -> tuple[int, int, int, list[str]]:
    healthy = 0
    total = 0
    rows = 0
    errors: list[str] = []
    candidates = sorted({*ROOT.rglob("*.sqlite3"), *ROOT.rglob("*.sqlite"), *ROOT.rglob("*.db")})
    for path in candidates:
        if any(part in {".venv", "wheelhouse", "node_modules"} for part in path.parts):
            continue
        total += 1
        try:
            connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
            result = connection.execute("PRAGMA integrity_check").fetchone()[0]
            if result != "ok":
                raise RuntimeError(result)
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

    counts = Counter(spec.domain for spec in ALL_MODULE_SPECS)
    checks.append(check("module catalogue", len(ALL_MODULE_SPECS) == 33 and counts == {"Bioinformatics": 17, "Discovery": 9, "Lab Analytics": 7}, f"33 modules · {dict(counts)}"))
    unique = len({spec.key for spec in ALL_MODULE_SPECS}) == 33 and len({spec.page_path for spec in ALL_MODULE_SPECS}) == 33
    checks.append(check("unique module mappings", unique, "unique keys and page paths"))

    missing_pages = [spec.page_path for spec in ALL_MODULE_SPECS if not (ROOT / spec.page_path).is_file()]
    checks.append(check("module pages", not missing_pages, f"missing={missing_pages}"))

    panel_ok = True
    panel_count = 0
    for spec in ALL_MODULE_SPECS:
        source = (ROOT / spec.page_path).read_text(encoding="utf-8")
        marker = f"STEP127_SCIENTIFIC_DEPTH_{spec.key.upper()}"
        if spec.locked_source:
            panel_ok &= marker not in source
        else:
            panel_count += marker in source
    checks.append(check("module integration", panel_ok and panel_count == 31, f"31 full panels + 2 protected-source sidebar integrations"))

    locked_rows = []
    for relative, expected in EXPECTED_LOCKED.items():
        actual = sha256(ROOT / relative)
        locked_rows.append({"path": relative, "expected": expected, "actual": actual, "byte_identical": actual == expected})
    checks.append(check("source-locked modules", all(item["byte_identical"] for item in locked_rows), f"{sum(item['byte_identical'] for item in locked_rows)}/5 byte-identical"))

    config = json.loads((ROOT / "config/step127_scientific_depth.json").read_text(encoding="utf-8"))
    checks.append(check("configuration", config.get("release") == "13.2.0" and config.get("module_count") == 33, "Step 127 module policy loaded"))

    manifest = json.loads((ROOT / "config/advanced_tools_manifest.json").read_text(encoding="utf-8"))
    tool_ids = {item.get("id") for item in manifest.get("tools", [])}
    required_tools = {"dorado", "interproscan", "signalp6", "deeptmhmm", "panaroo", "sourmash", "nextclade", "pangolin", "cutadapt", "mosdepth"}
    checks.append(check("advanced tool catalogue", len(manifest.get("tools", [])) >= 86 and required_tools.issubset(tool_ids), f"{len(manifest.get('tools', []))} registered tools"))

    assessments = [assess_module(spec.key) for spec in ALL_MODULE_SPECS]
    checks.append(check("capability assessments", len(assessments) == 33 and all(item.tier in {"A", "B", "C"} for item in assessments), "33/33 assessments generated"))

    try:
        with tempfile.TemporaryDirectory(prefix="biointel_step127_") as temp:
            root = Path(temp)
            fastp = build_protected_plan("fastq_qc", "fastp", [root / "R1.fastq.gz", root / "R2.fastq.gz"], root / "fastp", parameters={"threads": 4})
            flye = build_protected_plan("long_read", "flye", [root / "reads.fastq.gz"], root / "flye", parameters={"threads": 8, "platform": "nano-hq", "genome_size": "5m"})
            vep = build_protected_plan("variant_annotation", "vep", [root / "variants.vcf.gz"], root / "vep", parameters={"threads": 4, "assembly": "GRCh38"})
        plan_ok = fastp.argv[0] == "fastp" and flye.argv[0] == "flye" and vep.argv[0] == "vep"
        plan_detail = "fastp, Flye and VEP bounded plans generated"
    except Exception as exc:
        plan_ok, plan_detail = False, str(exc)
    checks.append(check("protected execution plans", plan_ok, plan_detail))

    pair_audit = audit_fastq_pairs(["A_R1.fastq.gz", "A_R2.fastq.gz", "B_R1.fastq.gz"])
    variant = normalize_variant("chr1", 100, "AT", "AC")
    checks.append(check("domain safeguards", pair_audit.paired == 1 and pair_audit.missing_mates == ("B",) and variant == ("chr1", 101, "T", "C"), "FASTQ pairing and variant normalization safeguards"))

    command_center = ROOT / "pages/172_Scientific_Depth_Command_Center.py"
    theme_source = (ROOT / "src/biointel/ui/theme.py").read_text(encoding="utf-8")
    checks.append(check("command center and global sidebar", command_center.is_file() and "render_step127_sidebar_for_page" in theme_source, "command center + protected-page sidebar"))

    compile_ok = compileall.compile_dir(ROOT / "src", quiet=1) and compileall.compile_dir(ROOT / "pages", quiet=1)
    checks.append(check("python compilation", compile_ok, "src and pages syntax compilation"))

    healthy, total, rows, db_errors = database_health()
    checks.append(check("database integrity", healthy == total and total > 0, f"{healthy}/{total} healthy · {rows} rows · errors={db_errors[:3]}"))

    passed = all(bool(item["passed"]) for item in checks)
    payload = {
        "schema": "biointel.step127.verification.v1",
        "version": version,
        "created_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "passed": passed,
        "checks": checks,
        "locked_modules": locked_rows,
        "module_counts": dict(counts),
        "registered_tools": len(manifest.get("tools", [])),
        "database_count": total,
        "database_rows": rows,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for item in checks:
        print(("PASS" if item["passed"] else "FAIL"), item["name"], "-", item["detail"])
    print("REPORT", REPORT)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
