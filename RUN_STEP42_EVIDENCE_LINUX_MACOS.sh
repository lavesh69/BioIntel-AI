#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONPATH="$PWD/src"
python scripts/run_step42_verifiable_evidence.py --load-requests 400 --tenant-iterations 1000
python scripts/qualify_step42_maximum_evidence.py
python -m pytest -q tests/operations/test_step42_maximum_verifiable_evidence.py
