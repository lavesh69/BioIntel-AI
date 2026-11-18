from __future__ import annotations

# ruff: noqa: E402
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.ui.visual_scenarios import SEMANTIC_VISUAL_SCENARIOS

BASELINES = ROOT / "visual" / "semantic_baselines"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_semantic_manifest_integrity() -> None:
    manifest_path = BASELINES / "manifest.json"
    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema"] == "biointel.semantic-visual-manifest.v1"
    assert set(manifest["scenarios"]) == {item[0] for item in SEMANTIC_VISUAL_SCENARIOS}
    for name, source, viewport in SEMANTIC_VISUAL_SCENARIOS:
        baseline_json = BASELINES / f"{name}.json"
        baseline_png = BASELINES / f"{name}.png"
        approved = manifest["scenarios"][name]
        snapshot = json.loads(baseline_json.read_text(encoding="utf-8"))
        assert approved["source"] == source
        assert approved["viewport"] == viewport
        assert snapshot["source"] == source
        assert snapshot["viewport"] == viewport
        assert snapshot["content_sha256"] == approved["content_sha256"]
        assert _sha256(baseline_json) == approved["json_sha256"]
        assert _sha256(baseline_png) == approved["png_sha256"]
        serialized = json.dumps(snapshot).lower()
        assert "traceback" not in serialized
        assert "uncaught app exception" not in serialized


@pytest.mark.skipif(
    os.getenv("BIOINTEL_RUN_LIVE_SEMANTIC", "0").strip().lower() not in {"1", "true", "yes"},
    reason="Live Streamlit semantic rendering is isolated to the visual-regression CI job.",
)
@pytest.mark.parametrize("name,source,viewport", SEMANTIC_VISUAL_SCENARIOS)
def test_live_semantic_visual_scenario(name: str, source: str, viewport: dict[str, int]) -> None:
    command = [
        sys.executable,
        "scripts/semantic_visual_worker.py",
        "--mode",
        "check",
        "--name",
        name,
        "--source",
        source,
        "--width",
        str(viewport["width"]),
        "--height",
        str(viewport["height"]),
    ]
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=180)
    assert completed.returncode == 0, completed.stdout + "\n" + completed.stderr
