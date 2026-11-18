from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.neuro_cns.demo_showcase import run_complete_demo_showcase
from biointel.neuro_cns.catalog import MODULES
from biointel.neuro_cns.production import verify_demo_pack
from biointel.neuro_cns.projects import project_json
from biointel.neuro_cns.reporting import bundle_html, bundle_json, bundle_markdown, bundle_pdf


EXPECTED_MODULE_KEYS = frozenset(module.key for module in MODULES)


def output_directory() -> Path:
    local = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    return local / "BioIntelAI" / "UserData" / "reports" / "step202-neuro-demo"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir")
    args = parser.parse_args()
    status = verify_demo_pack(ROOT)
    if not status["passed"]:
        raise RuntimeError(f"Step202 demo pack integrity failed: {status['errors']}")
    results = run_complete_demo_showcase()
    actual_module_keys = frozenset(results)
    if actual_module_keys != EXPECTED_MODULE_KEYS:
        missing = sorted(EXPECTED_MODULE_KEYS - actual_module_keys)
        unexpected = sorted(actual_module_keys - EXPECTED_MODULE_KEYS)
        raise RuntimeError(
            "Demo module coverage mismatch: "
            f"expected {len(EXPECTED_MODULE_KEYS)} canonical module results; "
            f"received {len(actual_module_keys)}. "
            f"missing={missing}; unexpected={unexpected}"
        )
    out = Path(args.output_dir).resolve() if args.output_dir else output_directory()
    out.mkdir(parents=True, exist_ok=True)
    project_name = "BioIntel-Neuro-Step202-Synthetic-Demo"
    metadata = {
        "project_name": project_name,
        "analyst": "BioIntel automated demo runner",
        "notes": "Synthetic demonstration only. No real patient data. Not controlled-release eligible.",
    }
    files = {
        "BioIntel-Neuro-Step202-Demo.json": bundle_json(results, **metadata).encode("utf-8"),
        "BioIntel-Neuro-Step202-Demo.html": bundle_html(results, **metadata).encode("utf-8"),
        "BioIntel-Neuro-Step202-Demo.md": bundle_markdown(results, **metadata).encode("utf-8"),
        "BioIntel-Neuro-Step202-Demo.pdf": bundle_pdf(results, **metadata),
        "BioIntel-Neuro-Step202-Project.json": project_json(project_name, results, metadata={"step": "202", "synthetic_demo": True}).encode("utf-8"),
    }
    manifest_rows = []
    import hashlib
    for name, data in files.items():
        path = out / name
        path.write_bytes(data)
        manifest_rows.append({"path": name, "size_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    manifest = {
        "schema": "biointel.neuro.step202.demo-run.v1",
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "module_results": len(results),
        "canonical_module_results": len(EXPECTED_MODULE_KEYS),
        "module_keys": sorted(actual_module_keys),
        "synthetic_demo_only": True,
        "controlled_release_eligible": False,
        "files": manifest_rows,
    }
    (out / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": True, "output_directory": str(out), "module_results": len(results), "files": len(files)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
