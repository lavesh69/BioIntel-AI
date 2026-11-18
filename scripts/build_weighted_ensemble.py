from __future__ import annotations

# ruff: noqa: E402, I001

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.training.ensemble import build_weighted_ensemble_artifact
from biointel.training.model_artifact import load_model_artifact, save_model_artifact


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a schema-compatible weighted ensemble.")
    parser.add_argument("output", type=Path)
    parser.add_argument("members", nargs="+", type=Path)
    parser.add_argument("--weights", nargs="+", type=float)
    parser.add_argument("--version", default="1.0.0")
    args = parser.parse_args()
    artifacts = [load_model_artifact(path, trusted_root=ROOT / "models") for path in args.members]
    ensemble = build_weighted_ensemble_artifact(
        artifacts,
        weights=args.weights,
        model_version=args.version,
    )
    output = save_model_artifact(ensemble, args.output)
    print(output)
    print("External revalidation is mandatory before scientific release.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
