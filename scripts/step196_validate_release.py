from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tomllib
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PART_COUNT = 5


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return payload


def write_validation_output(root: Path, requested: str | None, payload: dict[str, Any]) -> Path | None:
    """Write a report where possible without turning validation into a traceback.

    The normal Windows destination is the separated local UserData folder. A
    source-only audit on another operating system may not have a writable
    ``LOCALAPPDATA`` path, so a local ``reports`` fallback is used instead.
    """
    if requested:
        candidates = [Path(requested) if Path(requested).is_absolute() else root / requested]
    else:
        local = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
        candidates = [
            local / "BioIntelAI" / "UserData" / "reports" / "step196-validation.json",
            root / "reports" / "step196-validation.json",
        ]
    for output_path in candidates:
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            payload["report_path"] = str(output_path)
            output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            return output_path
        except OSError:
            continue
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--output")
    parser.add_argument("--allow-uninstalled", action="store_true")
    parser.add_argument("--deep-hashes", action="store_true")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, detail: Any) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": str(detail)})

    required = [
        "app.py",
        "INSTALL_WINDOWS.bat",
        "RUN_BOTH_WINDOWS.bat",
        "REPAIR_INSTALL_WINDOWS.bat",
        "scripts/install_windows_step196.py",
        "scripts/run_biointel_step196.py",
        "scripts/run_biointel_step196_runtime.py",
        "scripts/step196_runtime_preflight.py",
        "scripts/setup_free_web_ai_windows.py",
        "scripts/setup_scientific_runtime_windows.py",
        "scripts/step196_preinstall_contract.py",
        "scripts/repair_step196_release_metadata.py",
        "scripts/step196_self_test.py",
        "src/biointel/connected/free_web_ai.py",
        "src/biointel/contextual_research_v196/catalog.py",
        "src/biointel/contextual_research_v196/service.py",
        "src/biointel/contextual_research_v196/ui.py",
        "src/biointel/proof_gates_v10/catalog.py",
        "src/biointel/proof_gates_v10/registry.py",
        "src/biointel/proof_gates_v10/functional.py",
        "src/biointel/proof_gates_v10/ui.py",
        "pages/83_BioIntel_Copilot.py",
        "pages/85_Provider_Integration_Center.py",
        "requirements.lock",
        "requirements-windows-cp311-offline.lock",
        "STEP196_RELEASE.json",
        "STEP196_SOURCE_MANIFEST_SHA256.json",
    ]
    missing = [item for item in required if not (root / item).is_file()]
    add("required files", not missing, missing or "complete")

    missing_markers = [
        part
        for part in range(1, PART_COUNT + 1)
        if not (root / ".release_parts" / f"step196_part{part}.ok").is_file()
    ]
    add("five part markers", not missing_markers, missing_markers or "complete")

    try:
        version = (root / "VERSION").read_text(encoding="utf-8-sig").strip()
        with (root / "pyproject.toml").open("rb") as handle:
            project_version = str(tomllib.load(handle).get("project", {}).get("version", "")).strip()
        release = load_json(root / "STEP196_RELEASE.json")
        release_version = str(release.get("version", "")).strip()
        release_step = int(release.get("step", 0) or 0)
        release_part_count = int(release.get("part_count", 0) or 0)
        add(
            "version consistency",
            version == project_version == release_version == "15.5.0"
            and release_step == 196
            and release_part_count == PART_COUNT,
            {
                "VERSION": version,
                "pyproject": project_version,
                "release": release_version,
                "step": release_step,
                "part_count": release_part_count,
            },
        )
    except Exception as exc:
        add("version consistency", False, f"{type(exc).__name__}: {exc}")

    try:
        manifest = load_json(root / "STEP196_SOURCE_MANIFEST_SHA256.json")
        entries = manifest.get("entries", [])
        if not isinstance(entries, list):
            raise ValueError("manifest entries must be a list")
        bad: list[str] = []
        hash_jobs: list[tuple[str, Path, str]] = []
        for row in entries:
            if not isinstance(row, dict):
                bad.append("<invalid-row>")
                continue
            relative = str(row.get("path", ""))
            target = root / relative
            expected_size = int(row.get("size_bytes", -1))
            expected_hash = str(row.get("sha256", ""))
            if not target.is_file() or target.stat().st_size != expected_size:
                bad.append(relative)
                continue
            if args.deep_hashes:
                hash_jobs.append((relative, target, expected_hash))
        if hash_jobs:
            workers = min(16, max(4, (os.cpu_count() or 4)))
            with ThreadPoolExecutor(max_workers=workers) as executor:
                actual_hashes = executor.map(lambda job: sha256_file(job[1]), hash_jobs)
                for job, actual_hash in zip(hash_jobs, actual_hashes, strict=True):
                    if actual_hash != job[2]:
                        bad.append(job[0])
        detail = f"checked={len(entries)} bad={len(bad)}"
        if bad:
            detail += " files=" + ", ".join(bad[:20])
        add("source manifest", not bad, detail)
    except Exception as exc:
        add("source manifest", False, f"{type(exc).__name__}: {exc}")

    try:
        hook_pattern = re.compile(r"_render_step196_contextual_online_research\((['\"])([^'\"]+)\1")
        hooked: list[str] = []
        page_count = 0
        top_failures: list[str] = []
        for page in sorted((root / "pages").glob("*.py")):
            page_text = page.read_text(encoding="utf-8-sig")
            matches = list(hook_pattern.finditer(page_text))
            keys = [match.group(2) for match in matches]
            if keys:
                page_count += 1
                hooked.extend(keys)
                lines = page_text.splitlines()
                try:
                    apply_line = next(index for index, line in enumerate(lines) if line.strip() == "apply_theme()")
                    hook_lines = [page_text[:match.start()].count("\n") for match in matches]
                    if min(hook_lines) <= apply_line or max(hook_lines) > apply_line + 8:
                        top_failures.append(page.name)
                except StopIteration:
                    top_failures.append(page.name)
        catalog_text = (root / "src/biointel/contextual_research_v196/catalog.py").read_text(encoding="utf-8-sig")
        coverage_ok = (
            page_count == 79
            and len(hooked) == 80
            and len(set(hooked)) == 80
            and not top_failures
            and "ALL_MAJOR_MODULE_KEYS" in catalog_text
            and "MODULE_RESEARCH_PROFILES" in catalog_text
            and "TOP_WEBSITE_ELIGIBLE_MODULE_KEYS" in catalog_text
            and "has_relevant_top_websites" in catalog_text
        )
        add(
            "80 module hooks with relevant website access at top",
            coverage_ok,
            {
                "page_files": page_count,
                "hooks": len(hooked),
                "unique_modules": len(set(hooked)),
                "top_failures": top_failures,
                "relevant_modules": 61,
            },
        )
    except Exception as exc:
        add("80 module contextual online research hooks", False, f"{type(exc).__name__}: {exc}")

    try:
        priority_catalog = (root / "src/biointel/proof_gates_v10/catalog.py").read_text(encoding="utf-8-sig")
        priority_registry = (root / "src/biointel/proof_gates_v10/registry.py").read_text(encoding="utf-8-sig")
        priority_functional = (root / "src/biointel/proof_gates_v10/functional.py").read_text(encoding="utf-8-sig")
        priority_ui = (root / "src/biointel/proof_gates_v10/ui.py").read_text(encoding="utf-8-sig")
        priority_pattern = re.compile(
            r"_render_step196_p0_p1_priority_workbench\(ROOT, ['\"](?P<key>[a-z0-9_]+)['\"], expanded=False\)"
        )
        priority_hooks: list[str] = []
        for page in sorted((root / "pages").glob("*.py")):
            priority_hooks.extend(match.group("key") for match in priority_pattern.finditer(page.read_text(encoding="utf-8-sig")))
        centres_ok = all(
            "render_priority_upgrade_center" in (root / "pages" / name).read_text(encoding="utf-8-sig")
            for name in (
                "242_Final_All_Module_10of10_Command_Center.py",
                "243_Phase_1_to_9_Real_World_Qualification_Execution.py",
            )
        )
        p0p1_ok = (
            len(priority_hooks) == 62
            and len(set(priority_hooks)) == 62
            and all(token in priority_catalog for token in ("P0_MODULE_KEYS", "P1_MODULE_KEYS", "25", "37"))
            and all(token in priority_catalog for token in ("EXECUTION_KEY_ALIASES", "canonical_execution_key"))
            and all(token in priority_registry for token in ("sha256", "audit_chain_valid", "not-automated", "DISALLOWED_EVIDENCE_CLASSES", "stage_execution_input", "write_execution_record"))
            and all(token in priority_functional for token in ("module_execution_contract", "prepare_functional_workspaces", "run_execution_preflight", "NATIVE_PIPELINE_KEYS"))
            and all(token in priority_ui for token in ("render_module_priority_workbench", "render_priority_upgrade_center", "Functional local execution", "execution_portfolio_rows"))
            and centres_ok
        )
        add(
            "P0/P1 priority evidence upgrade contract",
            p0p1_ok,
            {
                "module_workbenches": len(priority_hooks),
                "unique_modules": len(set(priority_hooks)),
                "portfolio_centres": centres_ok,
                "canonical_execution_aliases": 7,
                "native_execution_routes": 15,
                "automatic_controlled_release": False,
            },
        )
    except Exception as exc:
        add("P0/P1 priority evidence upgrade contract", False, f"{type(exc).__name__}: {exc}")

    try:
        runtime_launcher = (root / "scripts/run_biointel_step97.py").read_text(encoding="utf-8-sig")
        runtime_page = (root / "pages/107_Installation_Data_Recovery_Center.py").read_text(encoding="utf-8-sig")
        release = load_json(root / "STEP196_RELEASE.json")
        handover = release.get("runtime_handover_fix", {})
        handover_ok = (
            isinstance(handover, dict)
            and handover.get("automatic_handover_only_for_verified_biointel_processes") is True
            and handover.get("unverified_pid_termination") is False
            and all(
                token in runtime_launcher
                for token in (
                    "_reconcile_existing_runtime_state",
                    "_matches_recorded_biointel_process",
                    "handed-off-verified-release",
                    "discarded-stale-or-unverified-runtime-record",
                    "biointel.runtime-state.v4",
                )
            )
            and "verified automatic handover" in runtime_page
            and "A different extracted BioIntel release is already running" not in runtime_launcher
        )
        add(
            "cross-release runtime handover contract",
            handover_ok,
            {
                "verified_process_handover": bool(handover.get("automatic_handover_only_for_verified_biointel_processes")),
                "unverified_pid_termination": handover.get("unverified_pid_termination"),
                "project_data_changed": False,
            },
        )
    except Exception as exc:
        add("cross-release runtime handover contract", False, f"{type(exc).__name__}: {exc}")

    try:
        install_text = (root / "INSTALL_WINDOWS.bat").read_text(encoding="utf-8-sig")
        run_text = (root / "RUN_BOTH_WINDOWS.bat").read_text(encoding="utf-8-sig")
        installer_text = (root / "scripts/install_windows_step196.py").read_text(encoding="utf-8-sig")
        free_text = (root / "src/biointel/connected/free_web_ai.py").read_text(encoding="utf-8-sig")
        contract_ok = all(
            token in install_text
            for token in ("step196_part%%P.ok", "install_windows_step196.py", "(1 2 3 4 5)")
        ) and "run_biointel_step196.py" in run_text
        contract_ok = contract_ok and "run_biointel_step196_runtime.py" in (
            root / "scripts" / "run_biointel_step196.py"
        ).read_text(encoding="utf-8-sig")
        contract_ok = contract_ok and all(
            token in installer_text
            for token in (
                "setup_free_web_ai_windows.py",
                "verify_windows_wheelhouse.py",
                "class InterprocessFileLock",
                "biointel.step196.install-lock.v3",
                "step196_preinstall_contract.py",
                "launch_optional_free_web_ai_setup",
                "launch_scientific_runtime_setup",
            )
        )
        context_ui_text = (root / "src/biointel/contextual_research_v196/ui.py").read_text(encoding="utf-8-sig")
        contract_ok = contract_ok and all(
            token in free_text
            for token in ("class OllamaClient", "class SearxNGClient", "class FreeWebCopilot", "provider_entity_types")
        )
        contract_ok = contract_ok and all(
            token in context_ui_text
            for token in ("Free Web AI Answer", "Official Database Results", "Open Websites", "contextual_provider_search")
        )
        add("free web AI integration contract", contract_ok, "complete" if contract_ok else "missing hook")
    except Exception as exc:
        add("free web AI integration contract", False, f"{type(exc).__name__}: {exc}")

    if not args.allow_uninstalled:
        add(
            "installed environment",
            (root / ".venv" / "Scripts" / "python.exe").is_file(),
            ".venv/Scripts/python.exe",
        )

    passed = all(item["passed"] for item in checks)
    output = {
        "schema": "biointel.step196.validation.v1",
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "passed": passed,
        "checks": checks,
    }
    output_path = write_validation_output(root, args.output, output)
    if output_path is None:
        print("WARNING: validation report could not be written; console output remains available.", file=sys.stderr)
    print(json.dumps(output, indent=2))
    if not passed:
        failed = [f"{item['name']}: {item['detail']}" for item in checks if not item['passed']]
        print("VALIDATION FAILED CHECKS:", file=sys.stderr)
        for item in failed:
            print(f" - {item}", file=sys.stderr)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
