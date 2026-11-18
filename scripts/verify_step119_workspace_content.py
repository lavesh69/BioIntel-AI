from __future__ import annotations

import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.ui.module_experience_2_9 import (  # noqa: E402
    MODULE_EXPERIENCE_CATALOG,
    validate_workspace_summary,
    workspace_summary_cards,
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    checks: list[dict[str, object]] = []

    def add(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "status": "PASS" if passed else "FAIL", "detail": detail})

    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    add("Version", version == "13.2.0", f"VERSION={version}")

    renderer_path = ROOT / "src/biointel/ui/module_experience_2_9.py"
    renderer = renderer_path.read_text(encoding="utf-8")
    add(
        "Summary schema",
        'data-biointel-summary-schema="v2"' in renderer,
        "Collapsed summaries expose the Step 119 schema marker",
    )
    add(
        "Stable card diagnostics",
        "data-biointel-card-id" in renderer and "data-biointel-card-surface" in renderer,
        "Per-card IDs and surfaces are emitted",
    )
    add(
        "Card overflow safeguards",
        "min-width:0;height:100%;overflow:hidden" in renderer and "white-space:normal" in renderer,
        "Narrow-card wrapping and sizing rules are present",
    )

    module_results: list[dict[str, object]] = []
    total_cards = 0
    fingerprints: set[tuple[str, ...]] = set()
    for key, spec in sorted(MODULE_EXPERIENCE_CATALOG.items()):
        cards = workspace_summary_cards(spec)
        issues = validate_workspace_summary(spec)
        total_cards += len(cards)
        fingerprints.add(tuple(value for _, value in cards))
        module_results.append(
            {
                "module_key": key,
                "title": spec.title,
                "card_count": len(cards),
                "status": "PASS" if not issues else "FAIL",
                "issues": list(issues),
                "cards": [{"title": title, "value": value} for title, value in cards],
            }
        )

    failed_modules = [item for item in module_results if item["status"] != "PASS"]
    add(
        "Workspace summary completeness",
        len(MODULE_EXPERIENCE_CATALOG) == 78 and not failed_modules,
        f"{len(MODULE_EXPERIENCE_CATALOG) - len(failed_modules)}/78 workspaces complete",
    )
    add("Validated card count", total_cards == 468, f"{total_cards}/468 summary cards")
    add(
        "Module-specific fingerprints",
        len(fingerprints) == 78,
        f"{len(fingerprints)}/78 unique workspace summary fingerprints",
    )

    integrated = []
    for path in sorted((ROOT / "pages").glob("*.py")):
        source = path.read_text(encoding="utf-8", errors="ignore")
        if "_render_step116_module_experience(" in source:
            integrated.append(path)
    add("Shared renderer coverage", len(integrated) == 77, f"{len(integrated)}/77 integrated pages")

    excluded = {
        "pages/6_DTI_Predictor.py": "84b3ecec1356b7239a057459210af4cd130c57c08dd9449b7239d1fe5954e0cc",
        "pages/74_DTI_Validation_Evidence_Center.py": "a700a8a21649b49cf0e3a1521d2afad45039b83b767c2fe730b93fee7d4f7f11",
        "pages/126_LIMS_ELN_and_Sample_Chain_of_Custody_Hub.py": "eadaef1a283a5fa11ce6b243aa561508ba9ceba9f6fdcc207f4853ccf7d86905",
        "pages/109_Lab_Instrument_Import_Center.py": "22b5aba5bfea37bb1ef330ed7cca3773467463f883189602d96a0151311c8f70",
        "pages/157_Instrument_Integration_Hub_2.py": "cf3a5f94756def0007dbff31184ec276d90b03fc6d6e1ca792c87189e5ab7d6d",
    }
    preserved = sum(sha256(ROOT / rel) == digest for rel, digest in excluded.items())
    add("Excluded page preservation", preserved == len(excluded), f"{preserved}/{len(excluded)} locked pages byte-identical")

    failed = [item for item in checks if item["status"] != "PASS"]
    payload = {
        "schema": "biointel.step119.workspace-content-verification.v1",
        "version": version,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "status": "PASS" if not failed else "FAIL",
        "passed": len(checks) - len(failed),
        "failed": len(failed),
        "checks": checks,
    }
    reports = ROOT / "reports"
    reports.mkdir(exist_ok=True)
    (reports / "step119_workspace_content_verification.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    audit = {
        "schema": "biointel.step119.workspace-content-audit.v1",
        "version": version,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "status": payload["status"],
        "workspaces": len(module_results),
        "summary_cards": total_cards,
        "unique_fingerprints": len(fingerprints),
        "failed_workspaces": len(failed_modules),
        "modules": module_results,
    }
    (ROOT / "STEP119_WORKSPACE_CONTENT_AUDIT.json").write_text(
        json.dumps(audit, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
