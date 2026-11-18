"""Validate BioIntel Education local production readiness without masking external gaps."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.education.local_transcription import local_transcription_readiness  # noqa: E402
from biointel.education.paths import education_paths  # noqa: E402
from verify_windows_wheelhouse import verify as verify_wheelhouse  # noqa: E402


def configured(*names: str) -> bool:
    return all(bool(os.environ.get(name, "").strip()) for name in names)


def gate(name: str, passed: bool, evidence: object, *, required: bool = True) -> dict[str, object]:
    return {
        "name": name,
        "required_for_local_core": required,
        "state": "passed" if passed else ("configuration_required" if not required else "failed"),
        "evidence": evidence,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate BioIntel Education deployment readiness")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--output", required=True)
    parser.add_argument("--require-production-profile", action="store_true")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    database, media = education_paths(root)
    transcription = local_transcription_readiness(root)
    wheelhouse = verify_wheelhouse(root)
    profile = os.environ.get("BIOINTEL_DEPLOYMENT_PROFILE", "local_desktop").strip()
    core = [
        gate("project source", (root / "src" / "biointel").is_dir(), str(root / "src" / "biointel")),
        gate("offline Windows wheelhouse", bool(wheelhouse.get("valid")), {"wheel_count": wheelhouse.get("wheel_count"), "errors": wheelhouse.get("runtime_compatibility", {}).get("errors", [])}),
        gate("bundled FFmpeg and local transcription", bool(transcription["ready"]), transcription),
        gate("Education data location", bool(database.parent), {"database": str(database), "media": str(media)}),
    ]
    if args.require_production_profile:
        core.append(gate("production deployment profile", profile == "production", profile))
    external = [
        gate("TURN relay", configured("BIOINTEL_CALL_TURN_URL", "BIOINTEL_CALL_TURN_USERNAME", "BIOINTEL_CALL_TURN_CREDENTIAL"), "real relay URL and credentials must pass deployment diagnostics", required=False),
        gate("OIDC identity", configured("BIOINTEL_OIDC_ISSUER", "BIOINTEL_OAUTH_CLIENT_ID"), "issuer and registered client required", required=False),
        gate("SMTP delivery", configured("BIOINTEL_SMTP_HOST", "BIOINTEL_SMTP_SENDER"), "host and sender required", required=False),
        gate("cluster persistence", configured("BIOINTEL_POSTGRES_DSN", "BIOINTEL_REDIS_URL", "BIOINTEL_S3_BUCKET"), "Postgres, Redis and object storage required for multi-node deployment", required=False),
    ]
    passed = all(item["state"] == "passed" for item in core)
    payload = {
        "schema": "biointel.education.deployment-readiness.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "local_core_ready": passed,
        "deployment_profile": profile,
        "core_gates": core,
        "external_integration_gates": external,
        "truth_contract": "External gates never become passed without explicit deployment configuration.",
    }
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())