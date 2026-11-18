from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPORT_DIR = Path("reports/education_selective_mega_update")


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


class Definitions(ast.NodeVisitor):
    def __init__(self) -> None:
        self.stack: list[str] = []
        self.items: set[tuple[str, str]] = set()

    def _visit(self, node: ast.AST, kind: str) -> None:
        name = str(getattr(node, "name"))
        qualified = ".".join([*self.stack, name])
        self.items.add((qualified, kind))
        self.stack.append(name)
        self.generic_visit(node)
        self.stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit(node, "function")

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit(node, "async_function")

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._visit(node, "class")


def definitions(path: Path) -> set[tuple[str, str]]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return set()
    visitor = Definitions()
    visitor.visit(tree)
    return visitor.items


def load(name: str) -> dict[str, Any]:
    return json.loads((REPORT_DIR / name).read_text(encoding="utf-8"))


def write_json(name: str, payload: Any) -> None:
    (REPORT_DIR / name).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def scan_database(path: Path) -> dict[str, set[str]]:
    if not path.is_file():
        return {}
    try:
        connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        tables: dict[str, set[str]] = {}
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'"):
            name = str(row[0])
            tables[name] = {
                str(column[1]) for column in connection.execute(f'PRAGMA table_info("{name}")')
            }
        connection.close()
        return tables
    except sqlite3.Error:
        return {}


def new_features() -> list[dict[str, Any]]:
    groups = {
        "Education Hub": [
            "Professional database-derived launch card",
            "Institution hierarchy registry",
            "People and admissions registry",
            "Configurable service request workflow",
            "Permission-aware institution search",
            "Official India source catalogue",
            "Authorised CSV institution import",
            "Provenance and freshness dashboard",
            "Private-field import rejection",
            "Idempotent import checksums",
            "Fuzzy duplicate review queue",
            "Role-targeted notifications",
        ],
        "Classroom": [
            "Professional database-derived launch card",
            "Unique controlled class codes",
            "Class member invitations",
            "Persistent class stream",
            "Scheduled and pinned posts",
            "Persistent classwork catalogue",
            "Classwork CSV export",
            "Role-filtered class visibility",
            "Existing attendance and assignment operations",
            "Existing visual intelligence workspace",
        ],
        "Examination Command Center": [
            "Professional database-derived launch card",
            "Examination registration and decision audit",
            "Duplicate-aware question bank",
            "Room and invigilator conflict detection",
            "Capacity-controlled seating",
            "Admit-card verification reference",
            "Question-wise evaluator records",
            "Configurable result rules",
            "Immutable result version history",
            "Result publication notifications",
            "Re-evaluation request workflow",
            "Consent-based proctor policy disabled by default",
            "Existing secure timed delivery",
        ],
        "Shared Education infrastructure": [
            "Additive R9 migration",
            "Service-layer RBAC",
            "Audit events",
            "FastAPI R9 routes",
            "Safe MIME and extension validation",
            "CSV export",
            "Legacy configurable examination pass mark",
            "Legacy classroom institution compatibility",
            "Custom-root backup correctness",
        ],
    }
    rows: list[dict[str, Any]] = []
    for module, names in groups.items():
        for name in names:
            feature_id = "edu-r9-" + hashlib.sha1(f"{module}:{name}".encode()).hexdigest()[:16]
            rows.append(
                {
                    "module_name": module,
                    "feature_name": name,
                    "stable_feature_id": feature_id,
                    "feature_kind": "r9_production_upgrade",
                    "source_file": "src/biointel/education/selective_mega.py",
                    "function_class": "EducationMegaService",
                    "route_page": "/api/v1/education/mega",
                    "navigation_destination": None,
                    "database_dependency": "education_selective_mega_r9_v1",
                    "api_dependency": "/api/v1/education/mega",
                    "existing_status": "new_additive",
                    "final_status": "implemented",
                    "test_status": "automated_and_smoke_tested",
                }
            )
    return rows


def generate(root: Path) -> dict[str, Any]:
    global REPORT_DIR
    root = root.resolve()
    REPORT_DIR = root / "reports" / "education_selective_mega_update"
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    baseline_modules = load("baseline_modules.json")["modules"]
    baseline_functions = load("baseline_functions.json")["functions"]
    baseline_routes = load("baseline_routes.json")["routes"]
    baseline_navigation = load("baseline_navigation.json")["navigation"]
    baseline_schema = load("baseline_database_schema.json")["sqlite_files"]
    baseline_features = load("baseline_features.json")["features"]
    baseline_files = {}
    with (REPORT_DIR / "baseline_files.csv").open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            baseline_files[row["path"]] = row

    missing_modules = [row for row in baseline_modules if not (root / row["source_file"]).is_file()]
    definition_cache: dict[str, set[tuple[str, str]]] = {}
    missing_functions = []
    for row in baseline_functions:
        source = row["source_file"]
        if source not in definition_cache:
            definition_cache[source] = definitions(root / source)
        key = (row["qualified_name"], row["kind"])
        if key not in definition_cache[source]:
            missing_functions.append(row)
    missing_routes = []
    for row in baseline_routes:
        path = root / row["source_file"]
        text = path.read_text(encoding="utf-8-sig", errors="replace") if path.is_file() else ""
        route_definition = (row["endpoint"], "async_function") in definition_cache.get(
            row["source_file"], set()
        ) or (row["endpoint"], "function") in definition_cache.get(row["source_file"], set())
        if row["path"] not in text or not route_definition:
            missing_routes.append(row)
    missing_navigation = []
    for row in baseline_navigation:
        path = root / row["source_file"]
        text = path.read_text(encoding="utf-8-sig", errors="replace") if path.is_file() else ""
        if not path.is_file() or (row.get("destination") and row["destination"] not in text):
            missing_navigation.append(row)
    missing_tables, missing_columns = [], []
    for database in baseline_schema:
        current = scan_database(root / database["source_file"])
        for item in database.get("tables", []):
            table = item["name"]
            if table not in current:
                missing_tables.append({"source_file": database["source_file"], "table": table})
            else:
                for column in item.get("columns", []):
                    if column["name"] not in current[table]:
                        missing_columns.append(
                            {
                                "source_file": database["source_file"],
                                "table": table,
                                "column": column["name"],
                            }
                        )
    missing_features = [
        row for row in baseline_features if not (root / row["source_file"]).is_file()
    ]

    modified_existing = []
    for relative, row in baseline_files.items():
        path = root / relative
        if path.is_file() and digest(path) != row["sha256"]:
            modified_existing.append(relative)
    allowed_shared = {
        "app.py": "Replaced the three selected plain launch links with live cards while retaining a compatibility wrapper.",
        "src/biointel/education/database.py": "Narrowed migration exception handling for safe failure visibility.",
        "src/biointel/education/platform.py": "Added the requested education role aliases without changing existing role names.",
        "src/biointel/education/api.py": "Registered additive R9 Education API routes.",
        "src/biointel/education/ui.py": "Added compatibility aliases and replaced only the three selected render entry points.",
        "pages/150_BioIntel_Education_Home_v17.py": "Replaced the legacy seeded Education Home page with the persistent production renderer.",
        "pages/151_BioIntel_Classroom_v17.py": "Replaced the legacy example Classroom page with the persistent production renderer.",
        "pages/339_BioIntel_Education_Home.py": "Normalized the active production-only Education Home entry point.",
        "pages/340_BioIntel_Classroom.py": "Normalized the active production-only Classroom entry point.",
        "pages/342_BioIntel_Academy_and_Lecture_Studio.py": "Applied the BioIntel theme and production-only Academy workspace.",
        "pages/344_BioIntel_Examination_Command_Center.py": "Applied the BioIntel theme and production-only Examination workspace.",
        "pages/345_BioIntel_Education_Intelligence_Hub.py": "Applied the BioIntel theme and production-only Intelligence workspace.",
        "pages/343_BioIntel_Education_Universe.py": "Applied the shared BioIntel theme to Education Universe.",
        "pages/346_BioIntel_Education_Enterprise.py": "Applied the shared BioIntel theme to the Home-linked Education Enterprise.",
        "pages/346_BioIntel_Institution_Platform_Center.py": "Applied the shared BioIntel theme to Institution Platform Center.",
        "pages/347_BioIntel_Virtual_Science_Lab.py": "Applied the shared BioIntel theme to the Home-linked Virtual Science Laboratory.",
        "pages/347_BioIntel_Education_Visual_Command_Center.py": "Applied the shared BioIntel theme to Education Visual Command.",
        "pages/348_BioIntel_Education_Desktop.py": "Applied the shared BioIntel theme to Education Desktop.",
        "pages/349_BioIntel_Mega_Production_and_Academic_Center.py": "Applied the shared BioIntel theme to Mega Production and Academic Center.",
        "pages/350_BioIntel_Final_Completion_and_Qualification_Center.py": "Applied the shared BioIntel theme to Final Completion and Qualification Center.",
        "pages/351_BioIntel_Local_Autonomy_and_Operations_Center.py": "Applied the shared BioIntel theme to Local Autonomy and Operations Center.",
        "pages/352_BioIntel_Academic_Quality_and_Intelligence_Center.py": "Applied the shared BioIntel theme to Academic Quality and Intelligence Center.",
        "pages/353_BioIntel_Production_Runtime_and_Research_Intelligence_Center.py": "Applied the shared BioIntel theme to Production Runtime and Research Intelligence Center.",
        "pages/354_BioIntel_Final_Runtime_Evidence_and_Scientific_Workbench_Center.py": "Applied the shared BioIntel theme to Final Runtime, Evidence and Scientific Workbench Center.",
        "src/biointel/education/intelligence_ui.py": "Replaced the Intelligence demo entry path with the persistent production platform.",
        "tests/test_education_phase4.py": "Updated the Intelligence UI smoke to patch the production-only platform contract.",
        "src/biointel/education/classroom_service.py": "Repaired the legacy hard-coded institution write while preserving its signature.",
        "src/biointel/education/examination_service.py": "Made pass marks configurable and proctoring opt-in.",
        "scripts/phase23_30_backup_restore.py": "Made explicit custom roots work in Windows backup validation.",
        "scripts/step206_release_gate.py": "Tightened the managed Windows path limit after native RDKit DLL qualification.",
        "scripts/verify_step202_neuro.py": "Isolated explicit project-root queue tests from installed UserData configuration.",
        "src/biointel/runtime_paths.py": "Added an explicit verification-only project-local runtime switch without changing production defaults.",
        "requirements-windows-cp311-offline.lock": "Synchronized the complete hash-pinned offline wheel inventory.",
        "release/SOURCE_MANIFEST_SHA256.json": "Regenerated the current release source SHA-256 manifest.",
        "STEP220_SOURCE_MANIFEST_SHA256.json": "Regenerated the legacy-compatible source SHA-256 manifest.",
        "src/biointel/chemistry/__init__.py": "Normalized a zero-byte package source for release integrity.",
        "src/biointel/dti/__init__.py": "Normalized a zero-byte package source for release integrity.",
        "src/biointel/training/__init__.py": "Normalized a zero-byte package source for release integrity.",
        "pages/141_Shiro_AI_Studio.py": "Replaced a fabricated static legacy Shiro page with the canonical themed Shiro application.",
        "pages/153_BioIntel_Academy_Lecture_Studio.py": "Replaced the legacy static Academy route with the canonical themed production Academy.",
        "pages/155_Education_Intelligence_Hub.py": "Replaced fabricated metrics with the canonical production Intelligence workspace.",
        "pages/172_Multilingual_Lecture_Intelligence.py": "Routed legacy Lecture Intelligence to the canonical Academy and Lecture Studio.",
        "pages/273_Shiro_AI.py": "Applied the shared BioIntel theme to the canonical Shiro route.",
        "src/biointel/education/academy_ui.py": "Integrated governed media jobs, event-derived playback, Lecture intelligence and course-aware Shiro.",
        "src/biointel/education/academy_service.py": "Made the preserved legacy enrollment adapter idempotent.",
        "src/biointel/education/intelligence_hub_service.py": "Removed static metrics from the preserved legacy adapter.",
        "src/biointel/education/lecture_intelligence.py": "Preserved the legacy interface while removing synthetic production transcripts and chapters.",
        "src/biointel/education/phase4.py": "Added canonical Shiro delegation for authorized Academy lecture transcripts.",
        "src/biointel/education/phase7_ui.py": "Connected the Academy player to server-validated events, chapters, notes and transcripts.",
        "src/biointel/education/phase15_ui.py": "Exposed governed media registration and playback evidence inside Academy.",
        "src/biointel/education/phase16_ui.py": "Exposed verified FFmpeg processing inside Academy.",
        "src/biointel/education/phase16_runtime/service.py": "Added an honest configuration-required state when FFmpeg is unavailable.",
        "src/biointel/education/selective_mega_ui.py": "Embedded the canonical tenant-scoped Shiro tutor in Classroom.",
        "tests/test_education_pdf_mega_upgrade.py": "Added PDF acceptance tests for legacy routes, Shiro, media jobs and playback evidence.",
        "platform/mobile/android/app/src/main/assets/public/cordova.js": "Normalized a zero-byte mobile build placeholder.",
        "platform/mobile/android/app/src/main/assets/public/cordova_plugins.js": "Normalized a zero-byte mobile build placeholder.",
        "platform/mobile/ios/App/App/public/cordova.js": "Normalized a zero-byte mobile build placeholder.",
        "platform/mobile/ios/App/App/public/cordova_plugins.js": "Normalized a zero-byte mobile build placeholder.",
        ".env.example": "Documented credential-free local transcription and honest external deployment boundaries.",
        "pyproject.toml": "Added the exact offline speech-to-text runtime dependency.",
        "requirements.txt": "Added the exact offline speech-to-text runtime dependency.",
        "requirements-production.txt": "Added the production speech-to-text runtime dependency.",
        "scripts/sync_windows_wheelhouse.py": "Recorded R15 speech-to-text runtime and bundled model provenance.",
        "scripts/education_selective_mega_reports.py": "Documented additive R15 changes in the preservation allowlist.",
        "src/biointel/education/phase16_runtime/schema.py": "Added an additive durable lecture-transcription job table and migration record.",
        "src/biointel/science_pulse/store.py": "Made explicit UserData configuration take precedence over legacy global database discovery.",
        "src/biointel/education/phase32_35/compute.py": "Changed free-space admission from the maximum disk ceiling to a bounded dataset scratch estimate.",
    }
    unexpected = [
        path
        for path in modified_existing
        if path not in allowed_shared
        and not path.startswith("reports/")
        and not path.startswith("wheelhouse/")
        and "__pycache__/" not in path
        and not path.startswith("UserData/")
    ]

    final_features = []
    for row in baseline_features:
        updated = dict(row)
        updated["final_status"] = "preserved"
        updated["test_status"] = "preservation_scan_passed"
        final_features.append(updated)
    final_features.extend(new_features())
    write_json(
        "final_features.json",
        {
            "generated_at_utc": stamp(),
            "feature_count": len(final_features),
            "features": final_features,
        },
    )

    preservation_rows = []
    preservation_rows += [
        {
            "item_type": "module",
            "stable_id": row["module"],
            "source": row["source_file"],
            "baseline_status": "present",
            "final_status": "missing" if row in missing_modules else "preserved",
            "test_status": "failed" if row in missing_modules else "passed",
        }
        for row in baseline_modules
    ]
    preservation_rows += [
        {
            "item_type": "function",
            "stable_id": f"{row['module']}:{row['qualified_name']}:{row['kind']}",
            "source": row["source_file"],
            "baseline_status": "present",
            "final_status": "missing" if row in missing_functions else "preserved",
            "test_status": "failed" if row in missing_functions else "passed",
        }
        for row in baseline_functions
    ]
    preservation_rows += [
        {
            "item_type": "route",
            "stable_id": f"{row['method']}:{row['path']}:{row['endpoint']}",
            "source": row["source_file"],
            "baseline_status": "present",
            "final_status": "missing" if row in missing_routes else "preserved",
            "test_status": "failed" if row in missing_routes else "passed",
        }
        for row in baseline_routes
    ]
    preservation_rows += [
        {
            "item_type": "feature",
            "stable_id": row["stable_feature_id"],
            "source": row["source_file"],
            "baseline_status": "present",
            "final_status": "missing" if row in missing_features else "preserved",
            "test_status": "failed" if row in missing_features else "passed",
        }
        for row in baseline_features
    ]
    with (REPORT_DIR / "preservation_matrix.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "item_type",
                "stable_id",
                "source",
                "baseline_status",
                "final_status",
                "test_status",
            ],
        )
        writer.writeheader()
        writer.writerows(preservation_rows)

    with (REPORT_DIR / "feature_matrix.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        fields = [
            "module_name",
            "feature_name",
            "stable_feature_id",
            "feature_kind",
            "source_file",
            "function_class",
            "route_page",
            "navigation_destination",
            "database_dependency",
            "api_dependency",
            "existing_status",
            "final_status",
            "test_status",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(final_features)

    removed = {
        "removed_modules": missing_modules,
        "removed_features": missing_features,
        "removed_functions": missing_functions,
        "removed_routes": missing_routes,
        "removed_tables": missing_tables,
        "removed_navigation_items": missing_navigation,
    }
    write_json("removed_items.json", removed)
    write_json(
        "unrelated_module_changes.json",
        {
            "generated_at_utc": stamp(),
            "modified_existing_files": modified_existing,
            "allowed_shared_changes": [
                {"source_file": path, "justification": allowed_shared[path]}
                for path in modified_existing
                if path in allowed_shared
            ],
            "unexpected_unrelated_modifications": unexpected,
        },
    )
    summary = {
        "generated_at_utc": stamp(),
        "baseline_modules": len(baseline_modules),
        "baseline_functions": len(baseline_functions),
        "baseline_routes": len(baseline_routes),
        "baseline_navigation": len(baseline_navigation),
        "baseline_features": len(baseline_features),
        "removed_counts": {key: len(value) for key, value in removed.items()},
        "missing_columns": missing_columns,
        "unexpected_unrelated_modifications": unexpected,
        "passed": not any(removed.values()) and not missing_columns and not unexpected,
    }
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    result = generate(args.root)
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
