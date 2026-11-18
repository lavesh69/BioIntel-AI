from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


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
    add("Per-page stylesheet", '_step116_module_experience_css' not in renderer and 'id="biointel-module-experience-v2"' in renderer, "Session-scoped CSS guard removed; v2 stylesheet present")
    add("Card layout rules", '.mx-grid{display:grid!important' in renderer and '.mx-card{display:block!important' in renderer, "Grid and card display rules are resilient")
    add("Summary marker", 'data-biointel-module-workspace="summary"' in renderer, "Collapsed summary has a stable diagnostic marker")
    add("Responsive rules", '@media(max-width:760px)' in renderer and '@media(max-width:480px)' in renderer, "Tablet and narrow-window fallbacks present")
    add("Forced colours", '@media(forced-colors:active)' in renderer, "Windows forced-colour support present")

    integrated = []
    for path in sorted((ROOT / "pages").glob("*.py")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if '_render_step116_module_experience(' in text:
            integrated.append(path)
    add("Affected page coverage", len(integrated) == 77, f"{len(integrated)}/77 module pages use the shared renderer")

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
        "schema": "biointel.step118.workspace-card-verification.v1",
        "version": version,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "status": "PASS" if not failed else "FAIL",
        "passed": len(checks) - len(failed),
        "failed": len(failed),
        "checks": checks,
    }
    output = ROOT / "reports/step118_workspace_card_verification.json"
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
