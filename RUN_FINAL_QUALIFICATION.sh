#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
PYTHON_BIN="${PYTHON_BIN:-python}"
if [[ -x .venv/bin/python ]]; then PYTHON_BIN=.venv/bin/python; fi
PYTHONPATH=src "$PYTHON_BIN" scripts/qualify_step43_final.py
