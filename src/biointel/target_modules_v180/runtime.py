from __future__ import annotations

from dataclasses import asdict, dataclass
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
from typing import Any

import pandas as pd

from .catalog import TARGET_MODULES, TARGET_PROFILES


@dataclass(frozen=True)
class ComponentProbe:
    component: str
    label: str
    source: str
    discovered: bool
    location: str
    version: str
    probe_status: str
    install_route: str


REFERENCE_FLAGS = (
    "present",
    "release_pinned",
    "checksum_verified",
    "licence_accepted",
    "schema_validated",
    "provenance_complete",
    "owner_approved",
)
MODEL_FLAGS = (
    "present",
    "provider_recorded",
    "release_pinned",
    "weight_checksum_verified",
    "licence_accepted",
    "architecture_locked",
    "preprocessing_locked",
    "model_card_complete",
    "calibration_available",
    "intended_use_approved",
)
COHORT_FLAGS = (
    "present",
    "cohort_id_recorded",
    "permission_verified",
    "deidentification_reviewed",
    "site_independent",
    "sample_ids_unique",
    "labels_locked",
    "subgroup_metadata_present",
    "checksum_verified",
    "leakage_audit_complete",
)
FIXTURE_FLAGS = (
    "present",
    "checksum_verified",
    "expected_outputs_locked",
    "negative_cases_present",
    "corruption_cases_present",
    "leakage_cases_present",
    "sensitivity_cases_present",
    "reproducibility_cases_present",
    "last_run_passed",
)
GOVERNANCE_FLAGS = (
    "present",
    "owner_assigned",
    "risk_assessment_approved",
    "biosafety_or_security_reviewed",
    "privacy_reviewed",
    "acceptance_plan_approved",
    "monitoring_slo_approved",
    "rollback_tested",
    "expert_reviewer_assigned",
)
EXTERNAL_FLAGS = (
    "independent_site_validation_complete",
    "orthogonal_or_wet_lab_confirmation_complete",
    "prospective_or_temporal_validation_complete",
    "physical_target_environment_qualification_complete",
    "domain_expert_signoff_complete",
    "operating_history_complete",
    "formal_release_review_complete",
)


def required_components(module_key: str) -> pd.DataFrame:
    if module_key not in TARGET_MODULES:
        raise KeyError(module_key)
    return pd.DataFrame(
        [
            {
                "component": component,
                "label": label,
                "install_route": route,
                "platform_target": "Windows/Python/WSL as qualified",
                "smoke_test": "import/version/help probe only",
            }
            for component, label, route in TARGET_PROFILES[module_key].supplemental_components
        ]
    )


def _asset_plan(module_key: str, kind: str, ids: tuple[str, ...]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "asset_id": asset_id,
                "label": asset_id.replace("-", " ").title(),
                "kind": kind,
                "release_mode": "operator-pinned-and-reviewed",
                "expected_format": "manifest + checksummed assets",
                "qualification_strategy": "manual evidence intake plus automated manifest verification",
            }
            for asset_id in ids
        ]
    )


def required_references(module_key: str) -> pd.DataFrame:
    return _asset_plan(module_key, "reference", TARGET_PROFILES[module_key].supplemental_references)


def required_models(module_key: str) -> pd.DataFrame:
    return _asset_plan(module_key, "model", TARGET_PROFILES[module_key].model_assets)


def required_cohorts(module_key: str) -> pd.DataFrame:
    return _asset_plan(module_key, "cohort", TARGET_PROFILES[module_key].cohort_assets)


def _python_version(module_name: str) -> str:
    candidates = [module_name, module_name.replace("_", "-"), module_name.split(".", 1)[0]]
    for candidate in candidates:
        try:
            return importlib.metadata.version(candidate)
        except importlib.metadata.PackageNotFoundError:
            continue
    return "importable"


def _probe_executable(executable: str, execute: bool) -> tuple[str, str]:
    if not execute:
        return "not executed", "discovered"
    commands = ([executable, "--version"], [executable, "-h"], [executable, "--help"])
    last = ""
    for command in commands:
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=20, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            last = str(exc)
            continue
        output = " ".join((result.stdout or result.stderr or "").strip().split())[:500]
        if result.returncode == 0:
            return output or "exit=0", "pass"
        last = output or f"exit={result.returncode}"
    return last or "probe failed", "probe-failed"


def probe_components(module_key: str, execute_smoke_tests: bool = False) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for item in required_components(module_key).to_dict("records"):
        component = str(item["component"])
        label = str(item["label"])
        route = str(item["install_route"])
        if component.startswith("python:"):
            module_name = component.split(":", 1)[1]
            found = importlib.util.find_spec(module_name) is not None
            status = "pass" if found and execute_smoke_tests else ("discovered" if found else "missing")
            rows.append(
                asdict(
                    ComponentProbe(
                        component,
                        label,
                        "python-package",
                        found,
                        module_name,
                        _python_version(module_name) if found else "not found",
                        status,
                        route,
                    )
                )
            )
            continue
        executable = shutil.which(component) or shutil.which(f"{component}.exe") or ""
        version, status = _probe_executable(executable, execute_smoke_tests) if executable else ("not found", "missing")
        rows.append(
            asdict(
                ComponentProbe(
                    component,
                    label,
                    "executable",
                    bool(executable),
                    executable,
                    version,
                    status,
                    route,
                )
            )
        )
    return pd.DataFrame(rows)


def _load_manifest(folder: Path) -> dict[str, Any]:
    for name in ("qualification_manifest.json", "manifest.json", "evidence_manifest.json"):
        path = folder / name
        if path.is_file():
            try:
                value = json.loads(path.read_text(encoding="utf-8-sig"))
                return value if isinstance(value, dict) else {}
            except (OSError, ValueError):
                return {}
    return {}


def _flag(payload: dict[str, Any], name: str) -> bool:
    aliases = {
        "licence_accepted": ("licence_accepted", "license_accepted", "terms_accepted"),
        "checksum_verified": ("checksum_verified", "sha256_verified"),
        "weight_checksum_verified": ("weight_checksum_verified", "weights_sha256_verified", "checksum_verified"),
        "release_pinned": ("release_pinned", "version_locked", "model_release_locked"),
        "permission_verified": ("permission_verified", "consent_or_permission_verified"),
        "biosafety_or_security_reviewed": ("biosafety_or_security_reviewed", "biosafety_reviewed", "security_reviewed"),
    }
    return any(bool(payload.get(alias)) for alias in aliases.get(name, (name,)))


def _roots(root: Path, kind: str) -> list[Path]:
    env = os.environ.get(f"BIOINTEL_{kind.upper()}_ROOT", "").strip()
    values = [
        Path(env).expanduser() if env else None,
        root / "UserData" / "step180" / kind,
        root / "UserData" / kind,
        root / "data" / kind,
    ]
    return [value.resolve() for value in values if value is not None]


def _probe_assets(root: str | Path, kind: str, ids: tuple[str, ...], flags: tuple[str, ...]) -> pd.DataFrame:
    project = Path(root).resolve()
    bases = _roots(project, kind)
    rows: list[dict[str, Any]] = []
    for asset_id in ids:
        folder = next((base / asset_id for base in bases if (base / asset_id).exists()), bases[0] / asset_id)
        payload = _load_manifest(folder) if folder.exists() else {}
        row: dict[str, Any] = {"asset_id": asset_id, "path": str(folder)}
        for flag in flags:
            row[flag] = folder.exists() if flag == "present" else _flag(payload, flag)
        row["qualification_status"] = "qualified" if all(bool(row[flag]) for flag in flags) else "review"
        rows.append(row)
    return pd.DataFrame(rows)


def probe_references(root: str | Path, module_key: str) -> pd.DataFrame:
    return _probe_assets(root, "references", TARGET_PROFILES[module_key].supplemental_references, REFERENCE_FLAGS)


def probe_models(root: str | Path, module_key: str) -> pd.DataFrame:
    return _probe_assets(root, "models", TARGET_PROFILES[module_key].model_assets, MODEL_FLAGS)


def probe_cohorts(root: str | Path, module_key: str) -> pd.DataFrame:
    return _probe_assets(root, "cohorts", TARGET_PROFILES[module_key].cohort_assets, COHORT_FLAGS)


def probe_fixtures(root: str | Path, module_key: str) -> pd.DataFrame:
    return _probe_assets(root, "fixtures", TARGET_PROFILES[module_key].validation_fixtures, FIXTURE_FLAGS)


def probe_governance(root: str | Path, module_key: str) -> pd.DataFrame:
    return _probe_assets(root, "governance", TARGET_PROFILES[module_key].governance_assets, GOVERNANCE_FLAGS)


def probe_external_evidence(root: str | Path, module_key: str) -> dict[str, bool]:
    folder = Path(root).resolve() / "UserData" / "step180" / "evidence" / module_key
    payload = _load_manifest(folder)
    return {flag: _flag(payload, flag) for flag in EXTERNAL_FLAGS}


def host_summary() -> dict[str, Any]:
    return {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "architecture": platform.machine(),
        "cpu_threads": os.cpu_count() or 0,
        "windows": platform.system().lower() == "windows",
        "wsl_available": bool(shutil.which("wsl") or shutil.which("wsl.exe")),
        "gpu_environment_declared": bool(os.environ.get("CUDA_VISIBLE_DEVICES", "").strip()),
    }


__all__ = [
    "REFERENCE_FLAGS",
    "MODEL_FLAGS",
    "COHORT_FLAGS",
    "FIXTURE_FLAGS",
    "GOVERNANCE_FLAGS",
    "EXTERNAL_FLAGS",
    "required_components",
    "required_references",
    "required_models",
    "required_cohorts",
    "probe_components",
    "probe_references",
    "probe_models",
    "probe_cohorts",
    "probe_fixtures",
    "probe_governance",
    "probe_external_evidence",
    "host_summary",
]
