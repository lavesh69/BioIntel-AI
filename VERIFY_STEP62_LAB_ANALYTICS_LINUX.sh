#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
python scripts/verify_step62_lab_analytics.py --output reports/step62_lab_analytics_qualification.json
echo "Qualification passed: reports/step62_lab_analytics_qualification.json"
