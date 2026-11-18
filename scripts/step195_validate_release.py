from __future__ import annotations

import argparse
import hashlib
import json
import os
import tomllib
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


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
        "scripts/install_windows_step195.py",
        "scripts/run_biointel_step195.py",
        "scripts/setup_free_web_ai_windows.py",
        "scripts/repair_step195_release_metadata.py",
        "src/biointel/connected/free_web_ai.py",
        "pages/83_BioIntel_Copilot.py",
        "pages/85_Provider_Integration_Center.py",
        "requirements.lock",
        "requirements-windows-cp311-offline.lock",
        "STEP195_RELEASE.json",
        "STEP195_SOURCE_MANIFEST_SHA256.json",
    ]
    missing = [item for item in required if not (root / item).is_file()]
    add("required files", not missing, missing or "complete")

    missing_markers = [
        part
        for part in range(1, 5)
        if not (root / ".release_parts" / f"step195_part{part}.ok").is_file()
    ]
    add("four part markers", not missing_markers, missing_markers or "complete")

    try:
        version = (root / "VERSION").read_text(encoding="utf-8-sig").strip()
        with (root / "pyproject.toml").open("rb") as handle:
            project_version = str(tomllib.load(handle).get("project", {}).get("version", "")).strip()
        release = load_json(root / "STEP195_RELEASE.json")
        release_version = str(release.get("version", "")).strip()
        release_step = int(release.get("step", 0) or 0)
        add(
            "version consistency",
            version == project_version == release_version == "15.2.0" and release_step == 195,
            {
                "VERSION": version,
                "pyproject": project_version,
                "release": release_version,
                "step": release_step,
            },
        )
    except Exception as exc:
        add("version consistency", False, f"{type(exc).__name__}: {exc}")

    try:
        manifest = load_json(root / "STEP195_SOURCE_MANIFEST_SHA256.json")
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
        install_text = (root / "INSTALL_WINDOWS.bat").read_text(encoding="utf-8-sig")
        run_text = (root / "RUN_BOTH_WINDOWS.bat").read_text(encoding="utf-8-sig")
        installer_text = (root / "scripts/install_windows_step195.py").read_text(encoding="utf-8-sig")
        free_text = (root / "src/biointel/connected/free_web_ai.py").read_text(encoding="utf-8-sig")
        contract_ok = all(
            token in install_text
            for token in ("step195_part%%P.ok", "install_windows_step195.py")
        ) and "run_biointel_step195.py" in run_text
        contract_ok = contract_ok and all(
            token in installer_text
            for token in ("setup_free_web_ai_windows.py", "verify_windows_wheelhouse.py")
        )
        contract_ok = contract_ok and all(
            token in free_text
            for token in ("class OllamaClient", "class SearxNGClient", "class FreeWebCopilot")
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
        "schema": "biointel.step195.validation.v1",
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "passed": passed,
        "checks": checks,
    }
    if args.output:
        output_path = Path(args.output)
        if not output_path.is_absolute():
            output_path = root / output_path
    else:
        local = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
        output_path = local / "BioIntelAI" / "UserData" / "reports" / "step195-validation.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(json.dumps(output, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
