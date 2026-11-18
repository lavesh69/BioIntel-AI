from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEMANTIC_SCRIPT = ROOT / "scripts" / "update_semantic_visual_baselines.py"
BROWSER_BASELINES = ROOT / "visual" / "browser_baselines"
SCENARIOS = {
    "home-desktop": {"route": "/", "viewport": {"width": 1440, "height": 1000}},
    "quality-desktop": {
        "route": "/Platform_Quality_Center",
        "viewport": {"width": 1440, "height": 1000},
    },
    "studio-desktop": {"route": "/BioIntel_Studio", "viewport": {"width": 1440, "height": 1000}},
    "compliance-desktop": {
        "route": "/Compliance_Research_Readiness",
        "viewport": {"width": 1440, "height": 1000},
    },
    "model-training-desktop": {
        "route": "/Model_Training",
        "viewport": {"width": 1440, "height": 1000},
    },
    "dti-predictor-desktop": {
        "route": "/DTI_Predictor",
        "viewport": {"width": 1440, "height": 1000},
    },
    "data-quality-desktop": {
        "route": "/Data_Quality_Activity",
        "viewport": {"width": 1440, "height": 1000},
    },
    "home-mobile": {"route": "/", "viewport": {"width": 390, "height": 844}},
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_manifest() -> None:
    manifest: dict[str, object] = {
        "schema": "biointel.browser-visual-manifest.v1",
        "approval_required": True,
        "scenarios": {},
    }
    for name, metadata in SCENARIOS.items():
        image = BROWSER_BASELINES / f"{name}.png"
        if not image.is_file():
            raise RuntimeError(f"Browser baseline was not generated: {image}")
        manifest["scenarios"][name] = {**metadata, "png_sha256": _sha256(image)}
    (BROWSER_BASELINES / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )


def main() -> int:
    semantic = subprocess.call([sys.executable, str(SEMANTIC_SCRIPT)], cwd=ROOT)
    if semantic:
        return semantic
    if os.getenv("BIOINTEL_SKIP_BROWSER_BASELINES", "0") == "1":
        print("Semantic visual baselines updated; browser baseline update skipped by environment.")
        return 0
    env = os.environ.copy()
    env["BIOINTEL_RUN_VISUAL_TESTS"] = "1"
    env["BIOINTEL_UPDATE_VISUAL_BASELINES"] = "1"
    status = subprocess.call(
        [sys.executable, "-m", "pytest", "tests/visual/test_visual_regression.py", "-q"],
        cwd=ROOT,
        env=env,
    )
    if status:
        return status
    _write_manifest()
    print(
        "Browser baselines generated after runtime-health assertions. Review and commit deliberately."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
