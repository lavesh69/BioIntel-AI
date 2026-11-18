"""Non-blocking Windows acquisition for the weakest-module scientific runtime.

This helper is intentionally standard-library-only so the main installer can
launch it safely after the offline application environment has been created.
It installs/downloads only routes that are public and technically automatable;
provider-authorised software, restricted licences, large references and real
external evidence remain explicitly pending rather than being fabricated.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
LOCAL = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
USER_DATA = Path(os.environ.get("BIOINTEL_USER_DATA_DIR", LOCAL / "BioIntelAI" / "UserData"))
DEFAULT_REPORT = USER_DATA / "reports" / "step196-scientific-runtime-setup.json"
DEFAULT_PLAN = USER_DATA / "reports" / "step196-weak-module-install-plan.json"
WEAK_RATING_CEILING = 5.32
MAX_AUTOMATIC_REFERENCE_GB = 2.0
MIN_FREE_GB_FOR_FULL_ENGINE_SETUP = 250.0
DEFAULT_DISTRO = "Ubuntu"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _split(value: object) -> list[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def _truthy(value: object) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return payload


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def build_priority_plan(root: str | Path, *, maximum_reference_gb: float = MAX_AUTOMATIC_REFERENCE_GB) -> dict[str, Any]:
    """Build a deterministic, evidence-honest plan for the 25 weakest modules."""
    root_path = Path(root).resolve()
    ratings_path = root_path / "STEP173_FINAL_ALL_MODULE_RATINGS.csv"
    with ratings_path.open(encoding="utf-8-sig", newline="") as handle:
        ratings = list(csv.DictReader(handle))
    weak = [
        row
        for row in ratings
        if float(row.get("actual_practical_readiness_rating") or 999.0) <= WEAK_RATING_CEILING
    ]
    weak.sort(key=lambda row: (float(row["actual_practical_readiness_rating"]), row.get("module_title", "")))
    modules = {str(row["module_key"]) for row in weak}

    engine_rows: list[dict[str, Any]] = []
    all_engine_rows: list[dict[str, Any]] = []
    for path in sorted((root_path / "data" / "step170" / "engine_manifests").glob("*.json")):
        item = _load_json(path)
        covered = sorted(modules.intersection(_split(item.get("modules"))))
        automatic = not _truthy(item.get("manual_distribution"))
        all_engine_rows.append({"engine": item["engine"], "automatic_install_eligible": automatic})
        if covered:
            engine_rows.append(
                {
                    "engine": item["engine"],
                    "label": item.get("label", item["engine"]),
                    "modules": covered,
                    "automatic_install_eligible": automatic,
                    "install_route": item.get("install_route", ""),
                    "licence_id": item.get("licence_id", ""),
                    "upstream_url": item.get("upstream_url", ""),
                    "model_weights_required": _truthy(item.get("model_weights_required")),
                    "reference_data_required": _truthy(item.get("reference_data_required")),
                }
            )

    reference_rows: list[dict[str, Any]] = []
    for path in sorted((root_path / "data" / "step170" / "reference_catalog").glob("*.json")):
        item = _load_json(path)
        covered = sorted(modules.intersection(_split(item.get("modules"))))
        if not covered:
            continue
        size_gb = float(item.get("approximate_size_gb") or 0.0)
        strategy = str(item.get("download_strategy") or "")
        automatic = strategy == "direct" and size_gb <= maximum_reference_gb
        reference_rows.append(
            {
                "reference_id": item["reference_id"],
                "label": item.get("label", item["reference_id"]),
                "modules": covered,
                "automatic_download_eligible": automatic,
                "download_strategy": strategy,
                "approximate_size_gb": size_gb,
                "licence_id": item.get("licence_id", ""),
                "licence_acceptance_mode": item.get("licence_acceptance_mode", ""),
                "source_url": item.get("source_url", ""),
            }
        )

    engine_rows.sort(key=lambda row: str(row["engine"]))
    reference_rows.sort(key=lambda row: str(row["reference_id"]))
    automatic_references = [row for row in reference_rows if row["automatic_download_eligible"]]
    return {
        "schema": "biointel.step196.weak-module-install-plan.v1",
        "created_at_utc": _now(),
        "source": "STEP173_FINAL_ALL_MODULE_RATINGS.csv + Step 170 manifests",
        "rating_ceiling": WEAK_RATING_CEILING,
        "weak_modules": [
            {
                "module_key": row["module_key"],
                "module_title": row.get("module_title", ""),
                "actual_practical_readiness_rating": float(row["actual_practical_readiness_rating"]),
                "remaining_blockers": row.get("remaining_blockers", ""),
            }
            for row in weak
        ],
        "targeted_engines": engine_rows,
        "targeted_references": reference_rows,
        "automatic_engine_count_catalog_wide": sum(
            bool(row["automatic_install_eligible"]) for row in all_engine_rows
        ),
        "automatic_engine_count_targeted": sum(
            bool(row["automatic_install_eligible"]) for row in engine_rows
        ),
        "manual_or_provider_engine_count_targeted": sum(
            not bool(row["automatic_install_eligible"]) for row in engine_rows
        ),
        "automatic_reference_count_targeted": len(automatic_references),
        "automatic_reference_storage_gb_targeted": round(
            sum(float(row["approximate_size_gb"]) for row in automatic_references), 2
        ),
        "total_reference_storage_gb_targeted": round(
            sum(float(row["approximate_size_gb"]) for row in reference_rows), 2
        ),
        "large_or_authorised_references_remain_operator_controlled": True,
        "external_evidence_is_not_installable_or_fabricated": True,
    }


def _command_result(command: list[str], *, timeout: int = 30) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return {
            "return_code": completed.returncode,
            "stdout_tail": completed.stdout[-2000:],
            "stderr_tail": completed.stderr[-2000:],
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"return_code": 127, "stdout_tail": "", "stderr_tail": f"{type(exc).__name__}: {exc}"}


def _wsl_inventory(distro: str) -> dict[str, Any]:
    executable = shutil.which("wsl.exe") or shutil.which("wsl")
    if not executable:
        return {"available": False, "distro_installed": False, "reason": "WSL2 command is unavailable"}
    result = _command_result([executable, "-l", "-q"])
    distros = [line.replace("\x00", "").strip() for line in str(result["stdout_tail"]).splitlines() if line.strip()]
    return {
        "available": result["return_code"] == 0,
        "distro_installed": distro in distros,
        "distro": distro,
        "executable": executable,
        "distros": distros,
        "detail": result,
    }


def _run_logged(command: list[str], *, cwd: Path, env: dict[str, str]) -> dict[str, Any]:
    """Inherit the background-worker log without buffering large installer output."""
    try:
        completed = subprocess.run(command, cwd=cwd, env=env, check=False)
        return {"return_code": completed.returncode}
    except OSError as exc:
        return {"return_code": 127, "error": f"{type(exc).__name__}: {exc}"}


def execute_setup(
    root: Path,
    plan: dict[str, Any],
    *,
    distro: str,
    attempt_wsl_bootstrap: bool,
    maximum_reference_gb: float,
) -> dict[str, Any]:
    """Attempt only public, recoverable acquisition routes after core install."""
    outcome: dict[str, Any] = {
        "schema": "biointel.step196.scientific-runtime-setup.v1",
        "started_at_utc": _now(),
        "platform": sys.platform,
        "core_application_is_independent": True,
        "licences_not_auto_accepted": True,
        "external_evidence_is_not_created": True,
        "targeted_weak_module_count": len(plan["weak_modules"]),
        "targeted_automatic_engines": plan["automatic_engine_count_targeted"],
        "targeted_manual_or_provider_engines": plan["manual_or_provider_engine_count_targeted"],
        "targeted_automatic_references": plan["automatic_reference_count_targeted"],
    }
    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")

    direct_references = [
        str(row["reference_id"])
        for row in plan["targeted_references"]
        if bool(row["automatic_download_eligible"])
    ]
    manager = root / "scripts" / "step170_reference_manager.py"
    if direct_references and manager.is_file():
        command = [
            sys.executable,
            str(manager),
            "--root",
            str(root),
            "--execute",
            "--max-size-gb",
            f"{maximum_reference_gb:g}",
        ]
        for reference_id in direct_references:
            command.extend(["--reference", reference_id])
        outcome["small_public_reference_acquisition"] = _run_logged(command, cwd=root, env=env)
    else:
        outcome["small_public_reference_acquisition"] = {"state": "not-required"}

    if os.name != "nt":
        outcome.update(
            {
                "runtime_state": "deferred-non-windows",
                "message": "Scientific engine installation is prepared for Windows/WSL2; this build host is not Windows.",
            }
        )
        outcome["finished_at_utc"] = _now()
        return outcome

    inventory = _wsl_inventory(distro)
    outcome["wsl"] = inventory
    if not inventory.get("available") or not inventory.get("distro_installed"):
        if attempt_wsl_bootstrap and inventory.get("executable"):
            bootstrap = _command_result(
                [str(inventory["executable"]), "--install", "-d", distro, "--no-launch"],
                timeout=600,
            )
            outcome["wsl_bootstrap"] = bootstrap
            outcome.update(
                {
                    "runtime_state": "wsl-installation-requested-restart-may-be-required",
                    "message": "Windows WSL2/Ubuntu setup was requested. If Windows asks for approval or a restart, complete that Windows step, then rerun INSTALL_WINDOWS.bat; the BioIntel core app remains usable now.",
                }
            )
        else:
            outcome.update(
                {
                    "runtime_state": "wsl2-unavailable",
                    "message": "Core BioIntel is installed. Free specialist engines require Windows WSL2 + Ubuntu; this was not available, so no engine is falsely marked installed.",
                }
            )
        outcome["finished_at_utc"] = _now()
        return outcome

    free_gb = round(shutil.disk_usage(root).free / 1024**3, 2)
    outcome["free_space_gb_at_project_drive"] = free_gb
    if free_gb < MIN_FREE_GB_FOR_FULL_ENGINE_SETUP:
        outcome.update(
            {
                "runtime_state": "deferred-insufficient-storage",
                "message": (
                    f"Core BioIntel is installed. The complete free specialist-engine setup requires at least "
                    f"{MIN_FREE_GB_FOR_FULL_ENGINE_SETUP:g} GB free on the project drive; detected {free_gb:g} GB."
                ),
            }
        )
        outcome["finished_at_utc"] = _now()
        return outcome

    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    workflow = root / "scripts" / "windows" / "step175_target_environment.ps1"
    if not powershell or not workflow.is_file():
        outcome.update(
            {
                "runtime_state": "scientific-workflow-unavailable",
                "message": "The Windows scientific-runtime workflow files are unavailable; core installation remains usable.",
            }
        )
        outcome["finished_at_utc"] = _now()
        return outcome

    # Step 175 uses grouped, resumable micromamba environments and imports
    # installed-but-unqualified records into the same local readiness registry.
    # It covers all 48 public automatic engines, including the 34 required by
    # the current weakest 25 modules.
    command = [
        powershell,
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(workflow),
        "-Mode",
        "ExecuteOpen",
        "-Distro",
        distro,
        "-Profile",
        "cpu-standard",
        "-MaxReferenceGB",
        f"{maximum_reference_gb:g}",
    ]
    outcome["full_free_engine_setup"] = _run_logged(command, cwd=root, env=env)
    outcome.update(
        {
            "runtime_state": "free-engine-setup-finished-review-reports",
            "message": (
                "Public specialist-engine setup finished or reported its recoverable state. "
                "Installed records remain unqualified until licence capture, reproducible fixtures, "
                "module integration and scientific review are complete."
            ),
        }
    )
    outcome["finished_at_utc"] = _now()
    return outcome


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare public BioIntel scientific runtimes for weak modules.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--mode", choices=("plan", "execute"), default="execute")
    parser.add_argument("--distro", default=DEFAULT_DISTRO)
    parser.add_argument("--max-reference-gb", type=float, default=MAX_AUTOMATIC_REFERENCE_GB)
    parser.add_argument("--attempt-wsl-bootstrap", action="store_true")
    parser.add_argument("--background-worker", action="store_true")
    parser.add_argument("--output")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    output = Path(args.output).resolve() if args.output else DEFAULT_REPORT
    try:
        plan = build_priority_plan(root, maximum_reference_gb=args.max_reference_gb)
        plan_path = output.with_name(DEFAULT_PLAN.name)
        _atomic_write(plan_path, plan)
        if args.mode == "plan":
            payload = {
                "schema": "biointel.step196.scientific-runtime-setup.v1",
                "started_at_utc": _now(),
                "finished_at_utc": _now(),
                "mode": "plan",
                "background_worker": bool(args.background_worker),
                "plan_path": str(plan_path),
                "runtime_state": "planned-no-system-changes",
                "message": "Readiness plan created; no runtime, reference or Windows setting was changed.",
                "targeted_weak_module_count": len(plan["weak_modules"]),
                "targeted_automatic_engines": plan["automatic_engine_count_targeted"],
                "targeted_manual_or_provider_engines": plan["manual_or_provider_engine_count_targeted"],
                "targeted_automatic_references": plan["automatic_reference_count_targeted"],
            }
        else:
            payload = execute_setup(
                root,
                plan,
                distro=args.distro,
                attempt_wsl_bootstrap=bool(args.attempt_wsl_bootstrap),
                maximum_reference_gb=args.max_reference_gb,
            )
            payload["mode"] = "execute"
            payload["background_worker"] = bool(args.background_worker)
            payload["plan_path"] = str(plan_path)
        _atomic_write(output, payload)
        print(json.dumps(payload, indent=2, sort_keys=True, default=str), flush=True)
        if args.strict and payload.get("runtime_state") not in {"free-engine-setup-finished-review-reports"}:
            return 1
        return 0
    except Exception as exc:
        payload = {
            "schema": "biointel.step196.scientific-runtime-setup.v1",
            "started_at_utc": _now(),
            "finished_at_utc": _now(),
            "mode": args.mode,
            "background_worker": bool(args.background_worker),
            "runtime_state": "setup-error",
            "message": f"{type(exc).__name__}: {str(exc)[:800]}",
            "core_application_is_independent": True,
        }
        try:
            _atomic_write(output, payload)
        except OSError:
            pass
        print(json.dumps(payload, indent=2, sort_keys=True), flush=True)
        return 1 if args.strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
