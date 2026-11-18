#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3.11 scripts/bootstrap.py
.venv/bin/python scripts/verify_dependency_lock.py --root .
.venv/bin/python scripts/dev_doctor.py
