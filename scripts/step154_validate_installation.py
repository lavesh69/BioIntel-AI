from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a merged BioIntel AI Step 154 folder.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--allow-uninstalled", action="store_true")
    args = parser.parse_args()
    root = Path(args.root).expanduser().resolve()
    sys.dont_write_bytecode = True
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    src = root / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))

    checks: list[dict[str, object]] = []
    failures: list[dict[str, str]] = []

    def check(key: str, passed: bool, message: str = "") -> None:
        checks.append({"key": key, "passed": bool(passed), "message": message})
        if not passed:
            failures.append({"key": key, "message": message})

    base_validator = root / "scripts" / "step150_validate_installation.py"
    check("step150_validator_present", base_validator.is_file(), str(base_validator))
    if base_validator.is_file():
        command = [sys.executable, str(base_validator), "--root", str(root)]
        if args.allow_uninstalled:
            command.append("--allow-uninstalled")
        completed = subprocess.run(command, cwd=root, text=True, capture_output=True, check=False, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        check("step150_base_validation", completed.returncode == 0, completed.stdout[-1800:] + completed.stderr[-900:])

    for part in range(1, 5):
        marker = root / ".release_parts" / f"step154_part{part}.ok"
        check(f"step154_part_{part}", marker.is_file(), marker.as_posix())

    critical_manifest = root / "release" / "step154_critical_hashes.json"
    check("critical_manifest_present", critical_manifest.is_file(), critical_manifest.as_posix())
    if critical_manifest.is_file():
        payload = json.loads(critical_manifest.read_text(encoding="utf-8"))
        for relative, expected in payload.get("files", {}).items():
            path = root / relative
            if not path.is_file():
                check(f"critical_file:{relative}", False, "missing")
                continue
            actual = sha256(path)
            check(f"critical_file:{relative}", actual == expected, f"expected={expected} actual={actual}")

    release_file = root / "STEP154_RELEASE.json"
    check("release_metadata", release_file.is_file(), release_file.as_posix())
    if release_file.is_file():
        release = json.loads(release_file.read_text(encoding="utf-8"))
        check("release_step", release.get("step") == 154, str(release.get("step")))
        check("regression_failures_zero", release.get("tests", {}).get("failed") == 0, str(release.get("tests")))
        check("regression_passes", release.get("tests", {}).get("passed") == 1275, str(release.get("tests")))
        check("native_workflows_complete", release.get("native_workflows") == 80, str(release.get("native_workflows")))
        check("domain_families_expanded", release.get("native_workflow_families", 0) >= 49, str(release.get("native_workflow_families")))
        check("full_hashing_enabled", release.get("full_input_provenance_hashing") is True, str(release.get("full_input_provenance_hashing")))
        check("complete_bundle_enabled", release.get("complete_result_bundle") is True, str(release.get("complete_result_bundle")))

    try:
        import pandas as pd
        from biointel.engineering.module_reliability import source_connection_audit
        from biointel.native.engines import ENGINE_REGISTRY, plan_catalog
        from biointel.release_hygiene import audit_runtime_residue
        from biointel.scientific_depth import MODULE_PROFILES, native_input_template, native_workflow_catalog, run_native_workflow
        from biointel.scientific_depth.native_integrity import full_frame_sha256, parse_scientific_bool
        from biointel.scientific_depth.toolchain_readiness import reference_readiness

        catalog = native_workflow_catalog()
        check("scientific_profiles_80", len(MODULE_PROFILES) == 80, str(len(MODULE_PROFILES)))
        check("native_workflows_80", len(catalog) == 80, str(len(catalog)))
        check("native_families_49", int(catalog.family.nunique()) >= 49, str(catalog.family.nunique()))
        check("engine_registry_61", len(ENGINE_REGISTRY) >= 61, str(len(ENGINE_REGISTRY)))
        check("execution_plans_41", len(plan_catalog()) >= 41, str(len(plan_catalog())))
        check("false_string_safe", parse_scientific_bool("False") is False and parse_scientific_bool("No") is False, "fail-closed boolean parser")

        frame_a = pd.DataFrame({"value": list(range(10020))})
        frame_b = frame_a.copy()
        frame_b.loc[10019, "value"] = -999
        check("full_frame_hash_scope", full_frame_sha256(frame_a) != full_frame_sha256(frame_b), "row 10020 affects digest")

        demo_failures: dict[str, str] = {}
        for module_key in MODULE_PROFILES:
            result = run_native_workflow(module_key, native_input_template(module_key, demonstration=True))
            if result.status == "fail":
                demo_failures[module_key] = "; ".join(result.checks.loc[result.checks.status == "fail", "detail"].astype(str).tolist())
        check("all_80_demo_workflows_execute", not demo_failures, json.dumps(demo_failures, sort_keys=True))

        connection_audit = source_connection_audit(root)
        check("managed_sqlite_connections", bool(connection_audit.get("passed")), json.dumps(connection_audit.get("violations", [])))

        residue = [str(path.relative_to(root)) for path in audit_runtime_residue(root)]
        check("release_runtime_residue_absent", not residue, json.dumps(residue[:50]))

        with tempfile.TemporaryDirectory(prefix="biointel-step154-reference-") as temp:
            temp_root = Path(temp)
            folder = temp_root / "data" / "reference_packs"
            folder.mkdir(parents=True)
            (folder / "genome_annotation_model_reference.csv").write_text("fake,asset\n1,2\n", encoding="utf-8")
            readiness = reference_readiness(temp_root, ["population_gwas"])
            no_false_positive = bool(not readiness.empty and not readiness.local_candidate_detected.any())
            check("reference_filename_false_positive_blocked", no_false_positive, readiness.to_json(orient="records"))
    except Exception as exc:
        check("step154_runtime_contracts", False, f"{type(exc).__name__}: {exc}")

    source_checks = {
        "native_integrity": "src/biointel/scientific_depth/native_integrity.py",
        "native_orchestrator": "src/biointel/scientific_depth/native_workflows.py",
        "native_specialist": "src/biointel/scientific_depth/native_specialist_workflows.py",
        "native_omics": "src/biointel/scientific_depth/native_omics_workflows.py",
        "native_platform": "src/biointel/scientific_depth/native_platform_workflows.py",
        "toolchain_readiness": "src/biointel/scientific_depth/toolchain_readiness.py",
        "engine_adapters": "src/biointel/native/engines.py",
        "release_hygiene": "src/biointel/release_hygiene.py",
        "native_tests": "tests/test_step154_maximum_internal_readiness.py",
    }
    for key, relative in source_checks.items():
        path = root / relative
        check(key, path.is_file() and path.stat().st_size > 500, relative)

    report = {
        "schema": "biointel.step154.validation-report.v1",
        "root": str(root),
        "checks": checks,
        "failures": failures,
        "passed": not failures,
    }
    report_dir = root / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "step154_installation_validation.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    print(f"REPORT_PATH={report_path}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
