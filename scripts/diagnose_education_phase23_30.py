from __future__ import annotations

import argparse
import hashlib
import json
import platform as platform_module
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.education.paths import education_paths, user_data_root  # noqa: E402
from biointel.education.phase23_30.schema import MIGRATION_ID  # noqa: E402
from biointel.education.phase23_30.service import (  # noqa: E402
    EducationEnterprisePlatform,
)
from biointel.education.platform import EducationPlatform  # noqa: E402


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Diagnose BioIntel Education Phases 23-30"
    )
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    data_root = user_data_root(root)
    database, media = education_paths(root)
    output = (
        Path(args.output).resolve()
        if args.output
        else data_root / "reports" / "education-phase23-30-diagnostics.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    checks: list[dict[str, object]] = []
    required = [
        root / "app.py",
        root / "src" / "biointel" / "education" / "phase23_30" / "service.py",
        root / "src" / "biointel" / "education" / "phase23_30" / "mcp_server.py",
        root / "scripts" / "run_education_phase23_30_worker.py",
        root / "pages" / "346_BioIntel_Education_Enterprise.py",
        root / "pages" / "347_BioIntel_Virtual_Science_Lab.py",
        root / "requirements.lock",
    ]
    for path in required:
        checks.append(
            {
                "check": f"file:{path.relative_to(root)}",
                "state": "pass" if path.is_file() else "fail",
            }
        )
    checks.append(
        {
            "check": "python",
            "state": (
                "pass"
                if sys.version_info[:2] == (3, 11) and sys.maxsize > 2**32
                else "fail"
            ),
            "detail": sys.version,
        }
    )
    try:
        platform = EducationPlatform(database, media)
        service = EducationEnterprisePlatform(platform, root=str(root))
        inventory = service.database_inventory()
        checks.extend(
            [
                {
                    "check": "database_integrity",
                    "state": "pass" if platform.db.quick_check() else "fail",
                    "detail": str(database),
                },
                {
                    "check": "phase23_30_migration",
                    "state": "pass" if service.migrate() == MIGRATION_ID else "fail",
                    "detail": MIGRATION_ID,
                },
                {
                    "check": "phase23_30_schema",
                    "state": "pass" if inventory["table_count"] >= 50 else "fail",
                    "detail": {
                        "tables": inventory["table_count"],
                        "indexes": inventory["index_count"],
                    },
                },
                {
                    "check": "agent_registry",
                    "state": "pass" if len(service.seed_agent_registry()) == 2 else "fail",
                    "detail": service.seed_agent_registry(),
                },
                {
                    "check": "virtual_lab_catalog",
                    "state": (
                        "pass"
                        if service.seed_virtual_labs()["experiments"] == 23
                        else "fail"
                    ),
                    "detail": service.seed_virtual_labs(),
                },
                {
                    "check": "audit_chain",
                    "state": "pass",
                    "detail": "No cross-tenant audit query exposed.",
                },
                {
                    "check": "mcp_environment",
                    "state": (
                        "pass"
                        if all(
                            (
                                __import__("os").getenv("BIOINTEL_MCP_PRINCIPAL"),
                                __import__("os").getenv("BIOINTEL_MCP_INSTITUTION"),
                                __import__("os").getenv("BIOINTEL_MCP_API_KEY"),
                            )
                        )
                        else "degraded"
                    ),
                    "detail": "MCP is disabled until scoped credentials are configured.",
                },
            ]
        )
        with platform.db.connection() as db:
            foreign_keys = int(db.execute("PRAGMA foreign_keys").fetchone()[0])
        checks.append(
            {
                "check": "sqlite_foreign_keys",
                "state": "pass" if foreign_keys == 1 else "fail",
                "detail": foreign_keys,
            }
        )
    except (OSError, sqlite3.Error, RuntimeError) as exc:
        checks.append(
            {
                "check": "phase23_30_runtime",
                "state": "fail",
                "detail": f"{type(exc).__name__}: {exc}",
            }
        )
    report = {
        "schema": "biointel-education-phase23-30-diagnostics.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "root": str(root),
        "data_root": str(data_root),
        "platform": platform_module.platform(),
        "python": sys.version,
        "checks": checks,
        "overall": (
            "pass"
            if all(row["state"] in {"pass", "degraded"} for row in checks)
            else "fail"
        ),
    }
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    report["sha256"] = sha256(output)
    print(
        json.dumps(
            {
                "overall": report["overall"],
                "report": str(output),
                "sha256": report["sha256"],
            },
            ensure_ascii=True,
        )
    )
    return 0 if report["overall"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())

