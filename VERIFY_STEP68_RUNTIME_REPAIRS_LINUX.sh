#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ -x .venv/bin/python ]]; then
  exec .venv/bin/python scripts/verify_step68_runtime_repairs.py
fi
exec python scripts/verify_step68_runtime_repairs.py
