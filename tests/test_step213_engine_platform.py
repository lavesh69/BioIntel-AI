from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from biointel.api.main import app
from biointel.engine_platform_v196 import (
    EngineManager,
    EngineStateStore,
    adapter_catalog,
    build_pack,
    engine_platform_catalog,
    inspect_pack,
    pack_catalog,
    production_service_catalog,
)
from biointel.engine_platform_v196.manager import PlanState
from biointel.engine_platform_v196.packs import EnginePackError, canonical_sha256, sha256_file

ROOT = Path(__file__).resolve().parents[1]


def test_complete_76_engine_catalog_is_unique_and_fail_closed() -> None:
    frame = engine_platform_catalog(root=ROOT)
    assert len(frame) == 76
    assert frame["engine"].nunique() == 76
    assert not frame["install_manifest_complete"].any()
    assert set(frame["qualification_status"]) == {"unqualified"}


def test_pack_groups_cover_all_engines_once() -> None:
    frame = pack_catalog()
    assert len(frame) == 5
    assert int(frame["engine_count"].sum()) == 76
    assert frame["pack_key"].is_unique


def test_twelve_advanced_format_adapters_are_registered() -> None:
    frame = adapter_catalog()
    assert len(frame) == 12
    assert set(frame["adapter"]) == {
        "h5ad", "zarr", "nifti", "dicom", "edf_bdf_fif", "bam_cram_bcf",
        "bigwig", "plink", "mzml", "fast5", "pod5", "ome_tiff",
    }


def test_six_optional_production_services_are_registered() -> None:
    frame = production_service_catalog()
    assert len(frame) == 6
    assert set(frame["service"]) == {"postgresql", "redis", "object_storage", "oidc", "observability", "crdt"}


def test_state_store_is_wal_safe_and_persistent(tmp_path: Path) -> None:
    store = EngineStateStore(tmp_path / "engine.sqlite3")
    store.upsert_engine("samtools", state="available-unqualified", version="1.0", qualified=False)
    assert store.get_engine("samtools")["version"] == "1.0"
    store.record_evidence("samtools", "version", "passed", sha256="a" * 64)
    assert len(store.evidence("samtools")) == 1
    assert store.integrity_check()["status"] == "passed"


def test_restricted_and_model_engines_remain_fail_closed(tmp_path: Path) -> None:
    manager = EngineManager(project=ROOT, user_data=tmp_path)
    assert manager.plan("netmhcpan").state is PlanState.REQUIRES_USER_AUTHORIZATION
    assert manager.plan("rfdiffusion").state is PlanState.REQUIRES_MODEL_PACK


def test_unqualified_catalog_does_not_emit_online_install_commands(tmp_path: Path) -> None:
    manager = EngineManager(project=ROOT, user_data=tmp_path)
    plan = manager.plan("samtools")
    assert plan.state not in {PlanState.READY_QUALIFIED_ONLINE, PlanState.READY_OFFLINE_PACK}
    assert plan.commands == ()
    assert any("Exact version" in blocker for blocker in plan.blockers)


def _build_dummy_pack(tmp_path: Path) -> tuple[Path, str]:
    source = tmp_path / "source"
    binary = source / "bin" / "samtools"
    binary.parent.mkdir(parents=True)
    binary.write_text("dummy executable\n", encoding="utf-8")
    digest = sha256_file(binary)
    destination = tmp_path / "test-pack.zip"
    build_pack(
        source,
        destination,
        pack_id="test-samtools-pack",
        pack_version="1.0",
        platform="test",
        engines=[{
            "engine": "samtools",
            "version": "test-1",
            "executable": "bin/samtools",
            "executable_sha256": digest,
            "qualified": True,
        }],
        licence_records=[{"engine": "samtools", "licence_sha256": "b" * 64}],
    )
    return destination, digest


def test_pack_build_inspection_and_install_are_integrity_checked(tmp_path: Path) -> None:
    pack, digest = _build_dummy_pack(tmp_path)
    inspection = inspect_pack(pack)
    assert inspection["status"] == "verified"
    manager = EngineManager(project=ROOT, user_data=tmp_path / "user")
    result = manager.install_pack(pack)
    assert result["status"] == "completed"
    state = manager.store.get_engine("samtools")
    assert state["state"] == "installed-unqualified"
    assert state["executable_sha256"] == digest
    assert state["qualified"] == 0
    evidence = manager.store.evidence("samtools").iloc[0]
    assert "target_machine_qualification_required" in evidence["details_json"]


def test_pack_uninstall_clears_registry_without_touching_project(tmp_path: Path) -> None:
    pack, _ = _build_dummy_pack(tmp_path)
    manager = EngineManager(project=ROOT, user_data=tmp_path / "user")
    manager.install_pack(pack)
    result = manager.uninstall("samtools", remove_pack_when_unused=True)
    assert result["status"] == "removed"
    assert manager.store.get_engine("samtools")["state"] == "not-installed"
    assert (ROOT / "app.py").is_file()


def test_unsafe_engine_pack_path_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "unsafe.zip"
    payload = {
        "schema": "biointel.engine-pack.v1",
        "pack_id": "unsafe",
        "pack_version": "1",
        "platform": "test",
        "engines": [],
        "licence_records": [],
        "files": [{"path": "../escape.txt", "size_bytes": 3, "sha256": hashlib.sha256(b"bad").hexdigest()}],
        "claim_boundary": "test",
    }
    payload["manifest_sha256"] = canonical_sha256(payload)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("../escape.txt", b"bad")
        archive.writestr("BIOINTEL_ENGINE_PACK.json", json.dumps(payload))
    with pytest.raises(EnginePackError, match="Unsafe archive path"):
        inspect_pack(path)


def test_tampered_engine_pack_payload_is_rejected(tmp_path: Path) -> None:
    pack, _ = _build_dummy_pack(tmp_path)
    tampered = tmp_path / "tampered.zip"
    with zipfile.ZipFile(pack) as source, zipfile.ZipFile(tampered, "w") as output:
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename == "bin/samtools":
                data = b"tampered"
            output.writestr(item, data)
    with pytest.raises(EnginePackError, match="SHA-256 mismatch|Size mismatch"):
        inspect_pack(tampered)


def test_manager_health_and_module_readiness_are_exportable(tmp_path: Path) -> None:
    manager = EngineManager(project=ROOT, user_data=tmp_path)
    health = manager.health_report()
    assert health["registered_engines"] == 76
    assert health["advanced_adapters"] == 12
    output = manager.export_report(tmp_path / "report.json")
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert len(payload["engines"]) == 76
    assert len(payload["adapters"]) == 12


def test_engine_platform_api_is_readable_and_plan_is_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BIOINTEL_USER_DATA_DIR", str(tmp_path))
    client = TestClient(app)
    response = client.get("/engine-platform/health")
    assert response.status_code == 200
    assert response.json()["registered_engines"] == 76
    response = client.post("/engine-platform/plan", json={"engine": "netmhcpan", "offline_pack": ""})
    assert response.status_code == 200
    assert response.json()["state"] == "requires-user-authorization"


def test_bootstrap_initializes_only_metadata_and_performs_no_download(tmp_path: Path) -> None:
    output = tmp_path / "bootstrap.json"
    environment = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "BIOINTEL_USER_DATA_DIR": str(tmp_path / "user")}
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "step213_engine_platform_bootstrap.py"), "--root", str(ROOT), "--user-data", str(tmp_path / "user"), "--output", str(output)],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["bootstrap"]["external_downloads_performed"] is False
    assert payload["bootstrap"]["external_engines_installed"] is False


def test_windows_installer_initializes_engine_platform_without_silent_download() -> None:
    installer = (ROOT / "scripts" / "install_windows_step206.py").read_text(encoding="utf-8")
    batch = (ROOT / "INSTALL_WINDOWS.bat").read_text(encoding="utf-8")
    assert "step213_engine_platform_bootstrap.py" in installer
    assert "no external downloads" in installer
    assert "step220_part%%P.ok" in batch
    assert "V19.6" not in batch


def test_protected_module_hashes_remain_unchanged() -> None:
    manifest = json.loads((ROOT / "PROTECTED_MODULE_HASHES_STEP205.json").read_text(encoding="utf-8"))
    for item in manifest["entries"]:
        assert hashlib.sha256((ROOT / item["path"]).read_bytes()).hexdigest() == item["sha256"]


def test_module_tool_readiness_reads_engine_control_center_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BIOINTEL_USER_DATA_DIR", str(tmp_path))
    binary = tmp_path / "managed-samtools"
    binary.write_text("managed", encoding="utf-8")
    store = EngineStateStore(user_data=tmp_path)
    store.upsert_engine("samtools", state="qualified-ready", executable=str(binary), qualified=True)
    from biointel.expansion.tool_adapters import tool_status
    frame = tool_status("epigenomics_chromatin")
    row = frame.loc[frame["engine_key"] == "samtools"].iloc[0]
    assert bool(row["installed"])
    assert bool(row["qualified"])
    assert row["source"] == "Engine Control Center"


def test_hardware_inventory_is_bounded_and_serialisable() -> None:
    from biointel.engine_platform_v196 import hardware_inventory
    payload = hardware_inventory(ROOT)
    assert payload["cpu_count"] >= 1
    assert payload["disk_free_bytes"] > 0
    json.dumps(payload)


def test_target_machine_qualification_requires_hash_version_positive_and_negative_evidence(tmp_path: Path) -> None:
    from biointel.engine_platform_v196 import qualify_engine
    executable = Path(sys.executable).resolve()
    expected_payload = b"qualified-output\n"
    expected_hash = hashlib.sha256(expected_payload).hexdigest()
    store = EngineStateStore(tmp_path / "qual.sqlite3")
    result = qualify_engine(
        "openmm",
        {
            "executable": str(executable),
            "executable_sha256": sha256_file(executable),
            "version_args": ["--version"],
            "version_regex": r"Python 3\.",
            "positive_command": [str(executable), "-c", "from pathlib import Path; Path('result.txt').write_bytes(b'qualified-output\\n')"],
            "positive_expected_codes": [0],
            "negative_command": [str(executable), "-c", "raise SystemExit(2)"],
            "negative_expected_codes": [2],
            "expected_outputs": [{"path": "result.txt", "sha256": expected_hash}],
            "timeout_seconds": 20,
        },
        store=store,
        workspace_root=tmp_path,
    )
    assert result.passed
    assert store.get_engine("openmm")["state"] == "qualified-ready"
    assert store.get_engine("openmm")["qualified"] == 1


def test_qualification_fails_closed_when_executable_hash_is_wrong(tmp_path: Path) -> None:
    from biointel.engine_platform_v196 import qualify_engine
    executable = Path(sys.executable).resolve()
    store = EngineStateStore(tmp_path / "qual.sqlite3")
    result = qualify_engine(
        "openmm",
        {
            "executable": str(executable),
            "executable_sha256": "0" * 64,
            "version_args": ["--version"],
            "version_regex": r"Python 3\.",
            "positive_command": [str(executable), "-c", "raise SystemExit(0)"],
            "negative_command": [str(executable), "-c", "raise SystemExit(2)"],
            "negative_expected_codes": [2],
            "expected_outputs": [],
        },
        store=store,
        workspace_root=tmp_path,
    )
    assert not result.passed
    assert store.get_engine("openmm")["state"] == "qualification-failed"


def test_restricted_engine_pack_requires_explicit_user_acceptance(tmp_path: Path) -> None:
    source = tmp_path / "source-restricted"
    binary = source / "bin" / "netMHCpan"
    binary.parent.mkdir(parents=True)
    binary.write_text("restricted", encoding="utf-8")
    pack = tmp_path / "restricted.zip"
    build_pack(
        source,
        pack,
        pack_id="restricted-test",
        pack_version="1",
        platform="test",
        engines=[{
            "engine": "netmhcpan",
            "version": "test",
            "executable": "bin/netMHCpan",
            "executable_sha256": sha256_file(binary),
            "qualified": False,
        }],
    )
    manager = EngineManager(project=ROOT, user_data=tmp_path / "user")
    with pytest.raises(EnginePackError, match="Explicit user licence acceptance"):
        manager.install_pack(pack)
    result = manager.install_pack(pack, accept_restricted_licences=True)
    assert result["status"] == "completed"
    assert manager.store.get_engine("netmhcpan")["state"] == "installed-unqualified"


def test_text_crdt_converges_for_concurrent_edits_and_is_idempotent() -> None:
    from biointel.engine_platform_v196 import TextCRDT

    seed = TextCRDT()
    seed.local_insert("seed", 1, 0, "A")
    left = TextCRDT(seed.operations())
    right = TextCRDT(seed.operations())
    left.local_insert("alice", 1, 1, "x")
    right.local_insert("bob", 1, 1, "y")

    merged_left_first = left.merge(right)
    merged_right_first = right.merge(left)
    assert merged_left_first.text() == merged_right_first.text()
    assert set(merged_left_first.text()) == {"A", "x", "y"}
    operation = merged_left_first.operations()[0]
    assert merged_left_first.apply(operation) is False


def test_text_crdt_delete_and_serialization_converge() -> None:
    from biointel.engine_platform_v196 import TextCRDT

    base = TextCRDT()
    base.local_insert("seed", 1, 0, "abc")
    deleting = TextCRDT(base.operations())
    inserting = TextCRDT(base.operations())
    deleting.local_delete("reviewer", 1, 1)
    inserting.local_insert("author", 1, 1, "X")

    first = deleting.merge(inserting)
    second = inserting.merge(deleting)
    assert first.text() == second.text()
    assert "b" not in first.text()
    restored = TextCRDT.from_dict(first.to_dict())
    assert restored.text() == first.text()
    assert restored.operations() == first.operations()


def test_production_configuration_validation_redacts_secrets_and_does_not_probe() -> None:
    from biointel.engine_platform_v196 import ProductionConfiguration, deployment_plan

    configuration = ProductionConfiguration(
        database_url="postgresql://biointel:top-secret@db.internal:5432/biointel",
        redis_url="rediss://cache.internal:6380/0",
        object_storage_endpoint="https://objects.internal",
        object_storage_bucket="biointel-data",
        oidc_issuer="https://identity.internal",
        otel_endpoint="grpc://telemetry.internal:4317",
        crdt_enabled=True,
    )
    plan = deployment_plan(configuration)
    assert plan["mode"] == "lab-distributed"
    assert plan["configured_services"] == 6
    assert plan["secrets_included"] is False
    assert "top-secret" not in json.dumps(plan)
    assert "does not start external servers" in plan["claim_boundary"]


def test_production_configuration_rejects_unsafe_or_incomplete_endpoints() -> None:
    from biointel.engine_platform_v196 import ProductionConfiguration, validate_production_configuration

    checks = validate_production_configuration(
        ProductionConfiguration(
            database_url="sqlite:///not-production.sqlite3",
            redis_url="http://not-redis.internal",
            object_storage_endpoint="https://objects.internal",
            object_storage_bucket="",
            oidc_issuer="http://identity.internal",
            otel_endpoint="ftp://telemetry.internal",
        )
    ).set_index("service")
    assert not bool(checks.loc["postgresql", "configured"])
    assert not bool(checks.loc["redis", "configured"])
    assert checks.loc["object_storage", "note"] == "bucket missing"
    assert not bool(checks.loc["oidc", "configured"])
    assert not bool(checks.loc["observability", "configured"])


def test_builtin_crdt_service_is_available_without_external_package() -> None:
    from biointel.engine_platform_v196 import production_service_status

    frame = production_service_status().set_index("service")
    assert bool(frame.loc["crdt", "package_available"])
    assert frame.loc["crdt", "package"] == "biointel.engine_platform_v196.crdt"


def test_restricted_pack_is_not_extracted_before_licence_acceptance(tmp_path: Path) -> None:
    source = tmp_path / "source-restricted-preflight"
    binary = source / "bin" / "netMHCpan"
    binary.parent.mkdir(parents=True)
    binary.write_text("restricted", encoding="utf-8")
    pack = tmp_path / "restricted-preflight.zip"
    build_pack(
        source,
        pack,
        pack_id="restricted-preflight",
        pack_version="1",
        platform="test",
        engines=[{
            "engine": "netmhcpan",
            "version": "test",
            "executable": "bin/netMHCpan",
            "executable_sha256": sha256_file(binary),
            "qualified": False,
        }],
    )
    manager = EngineManager(project=ROOT, user_data=tmp_path / "user")
    target = manager.tools / "EnginePacks" / "restricted-preflight"
    with pytest.raises(EnginePackError, match="before extracting"):
        manager.install_pack(pack)
    assert not target.exists()


def test_qualification_creates_missing_workspace_parent(tmp_path: Path) -> None:
    from biointel.engine_platform_v196 import qualify_engine

    executable = Path(sys.executable).resolve()
    expected_payload = b"workspace-created\n"
    missing_workspace = tmp_path / "not-yet-created" / "qualification"
    result = qualify_engine(
        "openmm",
        {
            "executable": str(executable),
            "executable_sha256": sha256_file(executable),
            "version_args": ["--version"],
            "version_regex": r"Python 3\.",
            "positive_command": [str(executable), "-c", "from pathlib import Path; Path('result.txt').write_bytes(b'workspace-created\\n')"],
            "positive_expected_codes": [0],
            "negative_command": [str(executable), "-c", "raise SystemExit(2)"],
            "negative_expected_codes": [2],
            "expected_outputs": [{"path": "result.txt", "sha256": hashlib.sha256(expected_payload).hexdigest()}],
        },
        store=EngineStateStore(tmp_path / "qualification.sqlite3"),
        workspace_root=missing_workspace,
    )
    assert result.passed
    assert missing_workspace.is_dir()
