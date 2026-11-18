#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python scripts/verify_step63_discovery.py --output reports/step63_discovery_qualification.json
python scripts/verify_store_release.py --output reports/step63_store_release_verification.json
