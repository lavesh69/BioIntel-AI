#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
python scripts/verify_step64_final.py --workers 4
