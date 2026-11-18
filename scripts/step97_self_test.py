from __future__ import annotations

import argparse
import gzip
import importlib
import io
import json
import os
import py_compile
import struct
import sys
import time
import tomllib
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable


CRITICAL = "critical"
ADVISORY = "advisory"


def _expected_parts(step: int) -> set[int]:
    # Current Step 196 V16 uses five complementary extraction parts.
    return set(range(1, 6))


def _validated_release_version(root: Path) -> str:
    """Validate current product metadata while preserving historical release records.

    STEP175_RELEASE.json is a historical milestone and must not be forced to match
    the current product version. The active release is the highest STEP*_RELEASE.json
    whose declared version matches VERSION.
    """

    version_path = root / "VERSION"
    if not version_path.is_file():
        raise RuntimeError("VERSION is missing from the extracted BioIntel AI folder.")
    version = version_path.read_text(encoding="utf-8-sig").strip()
    if not version:
        raise RuntimeError("VERSION is empty in the extracted BioIntel AI folder.")

    pyproject_path = root / "pyproject.toml"
    try:
        with pyproject_path.open("rb") as handle:
            project_version = str(tomllib.load(handle).get("project", {}).get("version", "")).strip()
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise RuntimeError(f"pyproject.toml is unreadable: {exc}") from exc
    if project_version != version:
        raise RuntimeError(
            "Mixed product metadata were detected: "
            f"VERSION={version!r}, pyproject.toml version={project_version!r}. "
            "Extract all required matching current ZIP parts into one new empty folder."
        )

    candidates: list[tuple[int, Path, dict[str, object]]] = []
    malformed: list[str] = []
    for release_path in root.glob("STEP*_RELEASE.json"):
        stem = release_path.name
        prefix = stem.split("_", 1)[0]
        try:
            filename_step = int(prefix.removeprefix("STEP"))
        except ValueError:
            continue
        try:
            payload = json.loads(release_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            malformed.append(f"{release_path.name}: {exc}")
            continue
        release_version = str(payload.get("version", "")).strip()
        if release_version != version:
            continue
        declared_step = payload.get("step", filename_step)
        try:
            declared_step = int(declared_step)
        except (TypeError, ValueError):
            malformed.append(f"{release_path.name}: invalid step {declared_step!r}")
            continue
        if declared_step != filename_step:
            malformed.append(
                f"{release_path.name}: filename step {filename_step} != declared step {declared_step}"
            )
            continue
        candidates.append((filename_step, release_path, payload))

    if not candidates:
        details = f" Malformed release files: {' | '.join(malformed[:3])}." if malformed else ""
        raise RuntimeError(
            "No current release manifest matches the installed product version: "
            f"VERSION={version!r}.{details} "
            "Do not mix files from different BioIntel releases; extract all required matching current ZIP parts "
            "into one new empty folder."
        )

    active_step, active_path, _active_payload = max(candidates, key=lambda item: item[0])
    marker_dir = root / ".release_parts"
    if marker_dir.is_dir():
        present = list(marker_dir.glob(f"step{active_step}_part*.ok"))
        if present:
            missing = [
                part for part in sorted(_expected_parts(active_step))
                if not (marker_dir / f"step{active_step}_part{part}.ok").is_file()
            ]
            if missing:
                raise RuntimeError(
                    f"Current Step {active_step} release is incomplete; missing part marker(s): {missing}. "
                    "Extract all required matching ZIP parts into one new empty folder."
                )

    return version

def _normalize_root(value: str | Path) -> Path:
    raw = str(value).strip().strip('"').strip("'")
    if not raw or raw == ".":
        return Path.cwd().resolve()
    return Path(raw).expanduser().resolve()


def _check(name: str, operation: Callable[[], str], *, severity: str = CRITICAL) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        detail = operation()
        return {
            "name": name,
            "severity": severity,
            "status": "PASS",
            "detail": detail,
            "seconds": round(time.perf_counter() - started, 3),
        }
    except Exception as exc:
        return {
            "name": name,
            "severity": severity,
            "status": "FAIL",
            "detail": f"{type(exc).__name__}: {exc}",
            "seconds": round(time.perf_counter() - started, 3),
        }


def run(root: Path, *, deep_models: bool = True, strict_python311: bool = True) -> dict[str, object]:
    root = root.resolve()
    src = root / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))

    checks: list[dict[str, Any]] = []

    def version_check() -> str:
        version = _validated_release_version(root)
        is_64_bit = struct.calcsize("P") * 8 == 64
        if strict_python311:
            valid_version = sys.version_info[:2] == (3, 11)
        else:
            valid_version = (3, 11) <= sys.version_info[:2] < (3, 14)
        if not valid_version or not is_64_bit:
            requirement = "CPython 3.11.x x64" if strict_python311 else "supported Python 3.11–3.13 x64"
            raise RuntimeError(
                f"{requirement} required; found {sys.version.split()[0]} "
                f"{struct.calcsize('P') * 8}-bit"
            )
        return f"BioIntel AI {version}; Python {sys.version.split()[0]} x64"

    checks.append(_check("Version and runtime", version_check))

    def dependency_check() -> str:
        modules = {
            "Bio": "Biopython",
            "fastapi": "FastAPI",
            "joblib": "Joblib",
            "numpy": "NumPy",
            "pandas": "Pandas",
            "plotly": "Plotly",
            "rdkit": "RDKit",
            "sklearn": "scikit-learn",
            "streamlit": "Streamlit",
        }
        failures: list[str] = []
        versions: list[str] = []
        for module_name, label in modules.items():
            try:
                module = importlib.import_module(module_name)
                version = str(getattr(module, "__version__", "installed"))
                versions.append(f"{label} {version}")
            except BaseException as exc:
                failures.append(f"{label}: {type(exc).__name__}: {exc}")
        if failures:
            raise RuntimeError("Core import failure(s): " + " | ".join(failures))
        return "Core scientific imports available; " + ", ".join(versions)

    checks.append(_check("Core dependencies", dependency_check))

    def upload_check() -> str:
        from biointel.io.uploads import read_uploaded_table_bytes

        csv_data = b"sample,value\nA,1\nB,2\n"
        plain = read_uploaded_table_bytes(csv_data, "test.csv")
        compressed = read_uploaded_table_bytes(gzip.compress(csv_data), "test.csv.gz")
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("input/test.tsv", b"sample\tvalue\nA\t1\nB\t2\n")
        zipped = read_uploaded_table_bytes(buffer.getvalue(), "test.zip")
        if plain.frame.shape != (2, 2) or compressed.frame.shape != (2, 2) or zipped.frame.shape != (2, 2):
            raise RuntimeError("Upload parser returned an unexpected shape")
        return "CSV, gzip and safe single-table ZIP parsing passed"

    checks.append(_check("Robust upload pipeline", upload_check))

    def database_check() -> str:
        from biointel.intelligence.data_intelligence import all_database_health

        result = all_database_health(root)
        healthy = int(result.get("healthy_count", 0))
        total = int(result.get("database_count", 0))
        if total <= 0:
            raise RuntimeError("No registered SQLite databases were found")
        if healthy != total:
            unhealthy = [
                name
                for name, payload in dict(result.get("databases", {})).items()
                if not bool(payload.get("exists")) or str(payload.get("integrity", "")).lower() != "ok"
            ]
            suffix = f"; unhealthy: {', '.join(unhealthy[:8])}" if unhealthy else ""
            raise RuntimeError(f"Only {healthy}/{total} databases are healthy{suffix}")
        return f"{total} databases healthy; {int(result.get('total_rows', 0)):,} indexed rows"

    # Data/model readiness is important, but it must not trap the Windows installer
    # when the UI/API runtime itself is healthy. Strict verification still returns
    # non-zero unless --allow-degraded is explicitly supplied by the installer.
    checks.append(_check("SQLite database fabric", database_check, severity=ADVISORY))

    def model_check() -> str:
        from biointel.training.model_artifact import (
            discover_model_artifact_candidates,
            load_model_artifact,
        )

        paths, rejected = discover_model_artifact_candidates(root / "models")
        if not paths:
            raise RuntimeError(
                "No compatible BioIntel model metadata envelopes were found"
                + (f"; {len(rejected)} file(s) rejected" if rejected else "")
            )
        if not deep_models:
            return f"{len(paths)} compatible model envelopes discovered; {len(rejected)} isolated"

        load_errors: dict[str, str] = {}
        for path in paths:
            try:
                loaded = load_model_artifact(path, trusted_root=root / "models")
            except Exception as exc:
                load_errors[path.name] = str(exc)
                continue
            return (
                f"{len(paths)} compatible model envelopes; "
                f"{path.name} artifact {loaded.metadata.artifact_version} loaded; "
                f"{len(rejected)} non-BioIntel/unsupported artifact(s) isolated"
            )
        samples = " | ".join(f"{name}: {message}" for name, message in list(load_errors.items())[:3])
        raise RuntimeError(f"No model artifact could be loaded. {samples}")

    checks.append(_check("Trusted model artifacts", model_check, severity=ADVISORY))

    def compile_check() -> str:
        targets = [
            root / "app.py",
            root / "pages/102_Multi_Omics_Biomarker_Discovery.py",
            root / "pages/103_Visual_Workflow_Builder.py",
            root / "pages/104_Innovation_Modules_Hub.py",
            root / "pages/110_Reliability_Optimization_Center.py",
            root / "src/biointel/io/uploads.py",
            root / "src/biointel/ui/workflow.py",
            root / "src/biointel/ui/runtime_guard.py",
            root / "src/biointel/training/model_artifact.py",
            root / "src/biointel/projects/ppi.py",
            root / "src/biointel/innovation/professional_engines.py",
            root / "src/biointel/innovation/professional_ui.py",
            root / "src/biointel/step101/background.py",
            root / "src/biointel/step101/ui_regression.py",
            root / "src/biointel/step101/performance.py",
            root / "src/biointel/step101/reference_lifecycle.py",
            root / "src/biointel/step101/reports.py",
            root / "pages/111_Windows_UI_Regression_Performance_Center.py",
            root / "pages/166_Real_Engine_Native_Format_Integration.py",
            root / "src/biointel/native/formats.py",
            root / "src/biointel/native/engines.py",
            root / "src/biointel/native/viewers.py",
            root / "src/biointel/statistics/rigor.py",
            root / "src/biointel/ui/viewer_sync.py",
            root / "src/biointel/study_design/engine.py",
            root / "src/biointel/reference_lifecycle/manager.py",
            root / "src/biointel/bioinformatics/upgrades.py",
            root / "src/biointel/ui/bioinformatics_upgrades.py",
            root / "pages/121_Biostatistics_Power_and_Experimental_Design_Studio.py",
            root / "pages/153_Reference_Database_Lifecycle_Manager_2.py",
            root / "pages/167_Bioinformatics_Feature_Upgrade_Center.py",
            root / "scripts/background_job_worker.py",
        ]
        missing = [str(target.relative_to(root)) for target in targets if not target.is_file()]
        if missing:
            raise RuntimeError("Critical Python source missing: " + ", ".join(missing))
        for target in targets:
            py_compile.compile(str(target), doraise=True)
        return f"{len(targets)} critical Python entry points compiled"

    checks.append(_check("Critical code compilation", compile_check))

    def storage_check() -> str:
        local = Path(os.environ.get("LOCALAPPDATA") or root)
        user_data = Path(os.environ.get("BIOINTEL_USER_DATA_DIR") or local / "BioIntelAI" / "UserData")
        for name in ("data", "reports", "workspace", "exports", "projects", "runtime_logs"):
            directory = user_data / name
            directory.mkdir(parents=True, exist_ok=True)
            probe = directory / ".step175-write-test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
        return f"Persistent UserData writable at {user_data}"

    checks.append(_check("Persistent storage", storage_check))

    critical_failures = [item for item in checks if item["status"] != "PASS" and item["severity"] == CRITICAL]
    advisory_failures = [item for item in checks if item["status"] != "PASS" and item["severity"] == ADVISORY]
    if critical_failures:
        status = "FAIL"
    elif advisory_failures:
        status = "DEGRADED"
    else:
        status = "PASS"
    return {
        "schema": "biointel.step175.self-test.v2",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "root": str(root),
        "status": status,
        "passed": len([item for item in checks if item["status"] == "PASS"]),
        "failed": len(critical_failures) + len(advisory_failures),
        "critical_failed": len(critical_failures),
        "advisory_failed": len(advisory_failures),
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--output")
    parser.add_argument("--quick-models", action="store_true")
    parser.add_argument(
        "--allow-build-runtime",
        action="store_true",
        help="Allow Python 3.11–3.13 during source/build verification. Installed Windows runs remain strict 3.11.",
    )
    parser.add_argument(
        "--allow-degraded",
        action="store_true",
        help="Return success when only advisory database/model checks fail. Used only by the Windows installer.",
    )
    args = parser.parse_args()
    result = run(
        _normalize_root(args.root),
        deep_models=not args.quick_models,
        strict_python311=not args.allow_build_runtime,
    )
    text = json.dumps(result, indent=2, default=str)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n", encoding="utf-8")
    print(text)
    if result["status"] == "PASS":
        return 0
    if args.allow_degraded and result["status"] == "DEGRADED":
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
