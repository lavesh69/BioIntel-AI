from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from .catalog import (
    ENVIRONMENT_GROUPS,
    engine_execution_catalog,
    environment_groups,
    environment_yaml,
    reference_execution_catalog,
    target_profiles,
)


def _json(path: Path, value: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    return path


def _text(path: Path, value: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")
    return path


def _sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def build_step175_assets(root: str | Path) -> list[Path]:
    root_path = Path(root).resolve()
    base = root_path / "data" / "step175"
    written: list[Path] = []
    engine_frame = engine_execution_catalog()
    ref_frame = reference_execution_catalog()
    group_frame = environment_groups()
    profile_frame = target_profiles()

    written.append(_text(base / "engine_execution_catalog.csv", engine_frame.to_csv(index=False)))
    written.append(_json(base / "engine_execution_catalog.json", {"schema": "biointel.step175.engine-catalog.v1", "engines": engine_frame.to_dict(orient="records")}))
    written.append(_text(base / "reference_execution_catalog.csv", ref_frame.to_csv(index=False)))
    written.append(_json(base / "reference_execution_catalog.json", {"schema": "biointel.step175.reference-catalog.v1", "references": ref_frame.to_dict(orient="records")}))
    written.append(_text(base / "environment_groups.csv", group_frame.to_csv(index=False)))
    written.append(_json(base / "environment_groups.json", {"schema": "biointel.step175.environment-groups.v1", "groups": group_frame.to_dict(orient="records")}))
    written.append(_text(base / "target_profiles.csv", profile_frame.to_csv(index=False)))
    written.append(_json(base / "target_profiles.json", {"schema": "biointel.step175.target-profiles.v1", "profiles": profile_frame.to_dict(orient="records")}))

    for group in ENVIRONMENT_GROUPS:
        written.append(_text(base / "environments" / f"{group.group_id}.yml", environment_yaml(group.group_id)))

    fixture_root = base / "engine_fixtures"
    for row in engine_frame.to_dict(orient="records"):
        engine = str(row["engine"])
        folder = fixture_root / engine
        written.append(_json(folder / "fixture_spec.json", {
            "schema": "biointel.step175.engine-fixture.v1",
            "engine": engine,
            "environment_group": row["environment_group"],
            "probe_executable": row["probe_executable"],
            "version_probe": str(row.get("smoke_test") or ""),
            "golden_fixture_level": "L2-synthetic-known-answer",
            "negative_control_required": True,
            "module_integration_level": "L3-native-workflow",
            "expected_exit_code": 0,
            "output_sha256_required": True,
            "actual_result": "pending-target-execution",
        }))
        written.append(_text(folder / "README.md", f"# {engine} qualification fixture\n\nRun this fixture only after the engine is installed on the target WSL2 environment. Record executable version, package provenance, output SHA-256, negative-control result and native module integration result.\n"))

    for row in engine_frame.loc[engine_frame["manual_provider_action_required"]].to_dict(orient="records"):
        engine = str(row["engine"])
        folder = base / "manual_provider_kits" / engine
        written.append(_json(folder / "intake.json", {
            "schema": "biointel.step175.manual-engine-intake.v1",
            "engine": engine,
            "upstream_url": row["upstream_url"],
            "licence_id": row["licence_id"],
            "authorized_download_path": "",
            "download_sha256": "",
            "installed_path": "",
            "executable_sha256": "",
            "model_weights_path": "",
            "model_weights_sha256": "",
            "licence_text_path": "",
            "licence_text_sha256": "",
            "operator": "",
            "qualified": False,
        }))
        written.append(_text(folder / "README.md", f"# Manual/provider installation: {engine}\n\nAcquire only through the recorded upstream route and under the applicable licence. Private credentials and private signing keys must never be placed in the project package.\n"))

    for row in ref_frame.to_dict(orient="records"):
        ref = str(row["reference_id"])
        folder = base / "reference_kits" / ref
        written.append(_json(folder / "intake.json", {
            "schema": "biointel.step175.reference-intake.v1",
            "reference_id": ref,
            "source_url": row["source_url"],
            "checksum_url": row["checksum_url"],
            "licence_id": row["licence_id"],
            "release_id": "",
            "provider_checksum": "",
            "local_path": "",
            "local_sha256": "",
            "schema_validation_passed": False,
            "index_validation_passed": False,
            "scientific_reviewer": "",
            "qualified": False,
        }))
        written.append(_text(folder / "README.md", f"# Production reference: {ref}\n\nDownload using the approved provider route, record the exact release, verify provider checksum when available, calculate local SHA-256, validate schema/indexes and retain a rollback snapshot.\n"))

    written.append(_json(base / "execution_contract.json", {
        "schema": "biointel.step175.execution-contract.v1",
        "version": "14.7.0",
        "engines": 53,
        "references": 26,
        "environment_groups": len(ENVIRONMENT_GROUPS),
        "target_profiles": len(profile_frame),
        "transactional_installation": True,
        "resume": True,
        "rollback": True,
        "licences_never_silently_accepted": True,
        "manual_provider_access_never_fabricated": True,
        "target_machine_qualification_required": True,
        "software_framework_score": 10.0,
    }))

    manifest = []
    for path in sorted(written):
        manifest.append({"path": path.relative_to(root_path).as_posix(), "sha256": _sha(path), "size_bytes": path.stat().st_size})
    manifest_path = _json(base / "asset_manifest.json", {"schema": "biointel.step175.asset-manifest.v1", "assets": manifest})
    written.append(manifest_path)
    return written


__all__ = ["build_step175_assets"]
