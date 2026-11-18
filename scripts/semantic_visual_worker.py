from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from PIL import Image, ImageChops
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.ui.visual_snapshot import (
    build_semantic_snapshot,
    render_semantic_snapshot,
    write_snapshot,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--width", required=True, type=int)
    parser.add_argument("--height", required=True, type=int)
    parser.add_argument("--mode", choices=("update", "check"), required=True)
    parser.add_argument("--artifacts", default="visual/artifacts/semantic")
    args = parser.parse_args()

    app = AppTest.from_file(str(ROOT / args.source), default_timeout=120).run()
    if app.exception:
        raise RuntimeError(f"Streamlit exception in {args.name}: {app.exception}")
    snapshot = build_semantic_snapshot(
        app,
        scenario=args.name,
        source=args.source,
        viewport={"width": args.width, "height": args.height},
    )
    baseline_root = ROOT / "visual" / "semantic_baselines"
    json_path = baseline_root / f"{args.name}.json"
    png_path = baseline_root / f"{args.name}.png"
    if args.mode == "update":
        write_snapshot(snapshot, json_path, png_path)
        print(json.dumps({"updated": args.name, "content_sha256": snapshot["content_sha256"]}))
        return 0

    expected = json.loads(json_path.read_text(encoding="utf-8"))
    if snapshot != expected:
        raise AssertionError(f"Semantic UI contract changed for {args.name}")
    artifacts = ROOT / args.artifacts
    artifacts.mkdir(parents=True, exist_ok=True)
    actual_png = artifacts / f"{args.name}.png"
    render_semantic_snapshot(snapshot, actual_png)
    expected_image = Image.open(png_path).convert("RGB")
    actual_image = Image.open(actual_png).convert("RGB")
    if actual_image.size != expected_image.size:
        raise AssertionError(f"Image size changed for {args.name}")
    if ImageChops.difference(expected_image, actual_image).getbbox() is not None:
        raise AssertionError(f"Rendered semantic visual changed for {args.name}")
    print(json.dumps({"passed": args.name, "content_sha256": snapshot["content_sha256"]}))
    return 0


if __name__ == "__main__":
    code = 1
    try:
        code = main()
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
    os._exit(code)
