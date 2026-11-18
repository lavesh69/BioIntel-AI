from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from biointel.environment_v175 import (
    Step175Registry,
    automatic_host_probe,
    build_step175_assets,
    engine_execution_catalog,
    environment_groups,
    environment_summary,
    execution_matrix,
    reference_execution_catalog,
    target_profiles,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_plan(root: Path, profile: str, max_reference_gb: float) -> dict:
    profiles = target_profiles().set_index("profile_id")
    if profile not in profiles.index:
        raise SystemExit(f"Unknown profile: {profile}")
    engines = engine_execution_catalog()
    refs = reference_execution_catalog()
    groups = environment_groups()
    automatic_refs = refs.loc[refs["automatic_download_eligible"] & (refs["approximate_size_gb"] <= max_reference_gb)]
    plan = {
        "schema": "biointel.step175.execution-plan.v1",
        "created_at_utc": _now(),
        "version": "14.7.0",
        "profile": profiles.loc[profile].to_dict(),
        "environment_groups": groups.to_dict(orient="records"),
        "engines_total": len(engines),
        "automatic_engines": int(engines["automatic_install_eligible"].sum()),
        "manual_engines": int(engines["manual_provider_action_required"].sum()),
        "references_total": len(refs),
        "automatic_references_under_size_policy": len(automatic_refs),
        "reference_storage_estimate_gb": round(float(refs["approximate_size_gb"].sum()), 2),
        "open_reference_storage_selected_gb": round(float(automatic_refs["approximate_size_gb"].sum()), 2),
        "max_reference_gb": max_reference_gb,
        "commands": {
            "plan": "RUN_STEP175_TARGET_ENVIRONMENT_WINDOWS.bat",
            "execute_open": "RUN_STEP175_TARGET_ENVIRONMENT_WINDOWS.bat --execute-open",
            "resume": "RUN_STEP175_TARGET_ENVIRONMENT_WINDOWS.bat --resume",
            "verify": "VERIFY_STEP175_WINDOWS.bat",
        },
        "licences_never_silently_accepted": True,
        "provider_credentials_never_stored": True,
        "automatic_installation_does_not_equal_qualification": True,
    }
    user_data = root / "UserData" / "step175"
    user_data.mkdir(parents=True, exist_ok=True)
    path = user_data / "execution_plan.json"
    path.write_text(json.dumps(plan, indent=2, default=str) + "\n", encoding="utf-8")
    plan["plan_path"] = str(path)
    plan["plan_sha256"] = _sha(path)
    return plan


def main() -> int:
    parser = argparse.ArgumentParser(description="BioIntel AI Step 175 target environment manager")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    p = sub.add_parser("plan"); p.add_argument("--profile", default="gpu-scientific"); p.add_argument("--max-reference-gb", type=float, default=2.0)
    sub.add_parser("probe-build-host")
    p = sub.add_parser("import-host-probe"); p.add_argument("path")
    p = sub.add_parser("import-engine-result"); p.add_argument("path")
    p = sub.add_parser("import-reference-result"); p.add_argument("path")
    sub.add_parser("matrix")
    args = parser.parse_args()

    build_step175_assets(ROOT)
    registry = Step175Registry(ROOT)
    if args.command == "status":
        print(json.dumps({"summary": environment_summary(ROOT), "registry": registry.status()}, indent=2, default=str)); return 0
    if args.command == "plan":
        print(json.dumps(build_plan(ROOT, args.profile, args.max_reference_gb), indent=2, default=str)); return 0
    if args.command == "probe-build-host":
        payload = automatic_host_probe(ROOT)
        path = ROOT / "reports" / "step175_build_host_probe.json"
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(payload, indent=2)); return 0 if payload["automatic_build_host_checks_passed"] else 1
    if args.command == "import-host-probe":
        print(json.dumps(registry.import_host_probe(args.path), indent=2)); return 0
    if args.command == "import-engine-result":
        result = registry.import_engine_result(args.path); print(json.dumps(result, indent=2)); return 0 if result["qualified"] else 2
    if args.command == "import-reference-result":
        result = registry.import_reference_result(args.path); print(json.dumps(result, indent=2)); return 0 if result["qualified"] else 2
    print(execution_matrix(ROOT).to_json(orient="records", indent=2)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
