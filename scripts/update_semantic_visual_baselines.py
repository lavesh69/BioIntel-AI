from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.ui.visual_scenarios import SEMANTIC_VISUAL_SCENARIOS


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    baseline_root = ROOT / "visual" / "semantic_baselines"
    baseline_root.mkdir(parents=True, exist_ok=True)
    for name, source, viewport in SEMANTIC_VISUAL_SCENARIOS:
        command = [
            sys.executable,
            "scripts/semantic_visual_worker.py",
            "--mode",
            "update",
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
        if completed.returncode:
            print(completed.stdout)
            print(completed.stderr, file=sys.stderr)
            return completed.returncode
        print(f"updated {name}")

    manifest: dict[str, object] = {
        "schema": "biointel.semantic-visual-manifest.v1",
        "scenarios": {},
    }
    for name, source, viewport in SEMANTIC_VISUAL_SCENARIOS:
        json_path = baseline_root / f"{name}.json"
        image_path = baseline_root / f"{name}.png"
        snapshot = json.loads(json_path.read_text(encoding="utf-8"))
        manifest["scenarios"][name] = {
            "source": source,
            "viewport": viewport,
            "content_sha256": snapshot["content_sha256"],
            "json_sha256": sha256(json_path),
            "png_sha256": sha256(image_path),
        }
    manifest_path = baseline_root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    print(f"wrote {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
