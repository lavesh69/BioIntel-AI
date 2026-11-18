from __future__ import annotations

import argparse
import json

from biointel.engineering.release import build_reproducible_release, verify_release_bundle

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--root", default=".")
    p.add_argument("--output", required=True)
    a = p.parse_args()
    target = build_reproducible_release(a.root, a.output)
    print(json.dumps(verify_release_bundle(target), indent=2))
