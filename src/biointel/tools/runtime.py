from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path, PureWindowsPath
from typing import Iterable, Sequence


@dataclass(frozen=True)
class ToolResolution:
    name: str
    available: bool
    backend: str
    executable: str | None
    tools_home: str
    detail: str
    distro: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def application_root() -> Path:
    return Path(__file__).resolve().parents[3]


def manifest_path() -> Path:
    return application_root() / "config" / "advanced_tools_manifest.json"


def load_manifest() -> dict[str, object]:
    path = manifest_path()
    if not path.is_file():
        return {"tools": []}
    return json.loads(path.read_text(encoding="utf-8"))


def tools_home() -> Path:
    explicit = os.environ.get("BIOINTEL_TOOLS_HOME", "").strip()
    if explicit:
        return Path(os.path.expandvars(explicit)).expanduser()
    bundled = application_root() / "tools"
    if bundled.exists():
        return bundled
    local = os.environ.get("LOCALAPPDATA", "").strip()
    if local:
        current = Path(local) / "BioIntelAI" / "Tools"
        legacy_candidates = (Path(local) / "B95Tools", Path(local) / "B91Tools")
        if current.exists():
            return current
        for legacy in legacy_candidates:
            if legacy.exists():
                return legacy
        return current
    return Path.home() / ".biointel" / "tools"


def _candidate_names(name: str) -> tuple[str, ...]:
    base = name.strip()
    if os.name == "nt":
        return (base, f"{base}.exe", f"{base}.cmd", f"{base}.bat")
    return (base,)


def _find_local(name: str, home: Path) -> Path | None:
    override = os.environ.get(f"BIOINTEL_TOOL_{name.upper().replace('-', '_')}", "").strip()
    if override and Path(override).is_file():
        return Path(override)
    roots = [home / "bin", home / "native", application_root() / "tools" / "bin"]
    for root in roots:
        if not root.exists():
            continue
        for candidate in _candidate_names(name):
            direct = root / candidate
            if direct.is_file():
                return direct
        # Official archives use versioned/nested directories. Keep recursion bounded
        # by the dedicated tools directory rather than scanning arbitrary user data.
        for candidate in _candidate_names(name):
            hits = sorted(root.rglob(candidate), key=lambda path: (len(path.parts), str(path).lower()))
            if hits:
                return hits[0]
    return None


def _wsl_marker(home: Path) -> dict[str, object]:
    marker = home / "state" / "wsl-tools.json"
    if not marker.is_file():
        return {}
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _manifest_entry(name: str) -> dict[str, object] | None:
    lowered = name.lower()
    for item in load_manifest().get("tools", []):
        names = [str(item.get("executable", "")), str(item.get("id", "")), *map(str, item.get("aliases", []))]
        if lowered in {entry.lower() for entry in names if entry}:
            return item
    return None


def resolve_tool(name: str) -> ToolResolution:
    home = tools_home()
    entry = _manifest_entry(name)
    candidates: list[str] = [name]
    if entry:
        candidates.extend([str(entry.get("executable", "")), *map(str, entry.get("aliases", []))])
    ordered = list(dict.fromkeys(candidate for candidate in candidates if candidate))
    for candidate in ordered:
        local = _find_local(candidate, home)
        if local:
            detail = "Application-local executable" if candidate == name else f"Application-local alias: {candidate}"
            return ToolResolution(name, True, "app-local", str(local), str(home), detail)
    for candidate in ordered:
        system = shutil.which(candidate)
        if system:
            detail = "Executable found on PATH" if candidate == name else f"Manifest alias found on PATH: {candidate}"
            return ToolResolution(name, True, "system-path", system, str(home), detail)
    marker = _wsl_marker(home)
    installed = {str(value).lower() for value in marker.get("tools", [])}
    distro = str(marker.get("distro", "")).strip() or None
    canonical = str((entry or {}).get("executable", name)).lower()
    aliases = {str(value).lower() for value in (entry or {}).get("aliases", [])}
    if distro and (canonical in installed or name.lower() in installed or installed.intersection(aliases)):
        if shutil.which("wsl.exe") or shutil.which("wsl"):
            return ToolResolution(name, True, "wsl", canonical, str(home), "Installed in BioIntel WSL toolchain", distro)
    preferred = str((entry or {}).get("backend", "not configured"))
    return ToolResolution(name, False, "missing", None, str(home), f"Not installed; preferred backend: {preferred}")


def tool_available(name: str) -> bool:
    return resolve_tool(name).available


def _looks_windows_path(value: str) -> bool:
    if len(value) >= 3 and value[1:3] in {":\\", ":/"}:
        return True
    return value.startswith("\\\\")


def windows_to_wsl_path(value: str) -> str:
    if not _looks_windows_path(value):
        return value
    path = PureWindowsPath(value)
    drive = path.drive.rstrip(":").lower()
    if not drive:
        return value
    parts = [part for part in path.parts[1:] if part not in {"\\", "/"}]
    escaped = "/".join(parts)
    return f"/mnt/{drive}/{escaped}"


def _convert_wsl_arguments(arguments: Sequence[str]) -> list[str]:
    converted: list[str] = []
    for value in arguments:
        text = str(value)
        if _looks_windows_path(text):
            converted.append(windows_to_wsl_path(text))
        else:
            converted.append(text)
    return converted


def run_tool(
    name: str,
    arguments: Sequence[str] = (),
    *,
    cwd: str | Path | None = None,
    timeout_seconds: int = 300,
    check: bool = False,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    resolution = resolve_tool(name)
    if not resolution.available or not resolution.executable:
        raise RuntimeError(f"{name} is not installed. Run INSTALL_ADVANCED_TOOLS_WINDOWS.bat.")
    args = [str(value) for value in arguments]
    command: list[str]
    effective_cwd = str(cwd) if cwd is not None else None
    if resolution.backend == "wsl":
        wsl = shutil.which("wsl.exe") or shutil.which("wsl") or "wsl.exe"
        command = [wsl, "-d", str(resolution.distro), "--", str(resolution.executable), *_convert_wsl_arguments(args)]
        # A Windows cwd cannot be passed to the Linux process through CreateProcess.
        effective_cwd = None
    else:
        executable = str(resolution.executable)
        suffix = Path(executable).suffix.lower()
        if os.name == "nt" and suffix in {".cmd", ".bat"}:
            command = [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/s", "/c", executable, *args]
        else:
            command = [executable, *args]
    return subprocess.run(
        command,
        cwd=effective_cwd,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=check,
        env=env,
    )


def tool_version(name: str, version_args: Iterable[str] | None = None) -> str:
    entry = _manifest_entry(name) or {}
    args = list(version_args if version_args is not None else entry.get("version_args", ["--version"]))
    try:
        completed = run_tool(name, args, timeout_seconds=12, check=False)
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        return f"Unavailable ({exc})"
    text = (completed.stdout or completed.stderr or "").strip().splitlines()
    return text[0][:240] if text else f"Exit {completed.returncode}"


def all_tool_status(*, include_versions: bool = False) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for item in load_manifest().get("tools", []):
        executable = str(item.get("executable", ""))
        resolution = resolve_tool(executable)
        row = {
            "id": item.get("public_key") or item.get("id"),
            "tool": item.get("public_label") or item.get("label"),
            "category": item.get("category"),
            "executable": executable,
            "available": resolution.available,
            "backend": resolution.backend,
            "path_or_command": resolution.executable or "",
            "purpose": item.get("purpose"),
            "database_required": bool(item.get("database_required", False)),
            "database_note": item.get("database_note", ""),
            "detail": resolution.detail,
        }
        if include_versions and resolution.available:
            row["version"] = tool_version(executable, item.get("version_args", []))
        rows.append(row)
    return rows

MODULE_TOOL_REQUIREMENTS: dict[str, list[str]] = {
    "Long-read assembly": ["dorado", "fastqc", "fastp", "minimap2", "samtools", "flye", "hifiasm", "racon", "medaka_consensus", "purge_dups", "quast", "busco", "merqury.sh"],
    "Pangenome analysis": ["minimap2", "bcftools", "mafft", "odgi", "vg", "minigraph", "panaroo"],
    "Pathogen genomics": ["kraken2", "bracken", "mash", "fastANI", "mlst", "amrfinder", "iqtree3", "run_gubbins.py"],
    "Virology": ["nextclade", "pangolin", "mafft", "iqtree3", "bcftools"],
    "Rare-disease annotation": ["vep", "snpEff", "bcftools", "whatshap", "ExpansionHunter"],
    "Sequence similarity": ["blastn", "mafft", "hmmscan", "mmseqs"],
    "Protein annotation": ["hmmscan", "interproscan.sh", "signalp6", "deeptmhmm"],
    "Proteomics": ["FileInfo", "comet", "MSGFPlus"],
    "Structural screening": ["vina", "obabel"],
    "Primer/construct design": ["primer3_core", "blastn", "bowtie2", "bcftools"],
    "Metagenomics": ["fastp", "bowtie2", "kraken2", "bracken", "metaphlan", "humann", "sourmash", "amrfinder"],
    "CRISPR screen": ["mageck", "BAGEL.py"],
}



def toolchain_preflight(*, include_versions: bool = False) -> dict[str, object]:
    status = all_tool_status(include_versions=include_versions)
    by_executable = {str(row.get("executable")): row for row in status}
    modules = []
    for module, requirements in MODULE_TOOL_REQUIREMENTS.items():
        available = [name for name in requirements if bool(by_executable.get(name, {}).get("available", False))]
        missing = [name for name in requirements if name not in available]
        modules.append({
            "module": module,
            "required_tools": len(requirements),
            "available_tools": len(available),
            "readiness": len(available) / max(1, len(requirements)),
            "available": ", ".join(available),
            "missing": ", ".join(missing),
        })
    total = len(status)
    available_total = sum(bool(row.get("available")) for row in status)
    return {
        "tools": status,
        "modules": modules,
        "summary": {
            "registered": total,
            "available": available_total,
            "missing": total - available_total,
            "coverage": available_total / max(1, total),
            "tools_home": str(tools_home()),
        },
    }


def export_toolchain_lock(*, include_versions: bool = True) -> dict[str, object]:
    report = toolchain_preflight(include_versions=include_versions)
    return {
        "schema": "biointel.toolchain.lock.v2",
        "tools_home": str(tools_home()),
        "manifest": str(manifest_path()),
        "tools": report["tools"],
        "module_readiness": report["modules"],
    }

# ---------------------------------------------------------------------------
# Step 95 provenance-first command execution
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ToolExecutionResult:
    name: str
    backend: str
    executable: str
    command: tuple[str, ...]
    returncode: int
    started_at: str
    finished_at: str
    duration_seconds: float
    stdout_path: str
    stderr_path: str
    manifest_path: str
    executable_sha256: str
    status: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _sha256_file(path: str | Path) -> str:
    import hashlib

    file_path = Path(path)
    if not file_path.is_file():
        return ""
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_tool_audited(
    name: str,
    arguments: Sequence[str],
    *,
    run_directory: str | Path,
    cwd: str | Path | None = None,
    timeout_seconds: int = 3600,
    allowed_exit_codes: Sequence[int] = (0,),
    env: dict[str, str] | None = None,
) -> ToolExecutionResult:
    """Run a registered tool with immutable command, log and executable evidence.

    The command is always passed as an argument vector; shell interpolation is
    never used. A manifest is written even when the command fails or times out.
    """
    from datetime import datetime, timezone
    import time

    from biointel.quality10.provenance import atomic_write_json

    resolution = resolve_tool(name)
    if not resolution.available or not resolution.executable:
        raise RuntimeError(f"{name} is not installed. Run INSTALL_ADVANCED_TOOLS_WINDOWS.bat.")
    output = Path(run_directory).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    safe_name = "".join(character if character.isalnum() or character in "._-" else "_" for character in name)
    stdout_path = output / f"{safe_name}.stdout.log"
    stderr_path = output / f"{safe_name}.stderr.log"
    manifest_path = output / f"{safe_name}.execution.json"
    started_at = datetime.now(timezone.utc).isoformat()
    started_clock = time.perf_counter()
    command = tuple([str(resolution.executable), *map(str, arguments)])
    returncode = -1
    status = "failed"
    error = ""
    stdout = ""
    stderr = ""
    try:
        completed = run_tool(
            name,
            arguments,
            cwd=cwd,
            timeout_seconds=timeout_seconds,
            check=False,
            env=env,
        )
        returncode = int(completed.returncode)
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        status = "completed" if returncode in {int(value) for value in allowed_exit_codes} else "failed"
    except subprocess.TimeoutExpired as exc:
        status = "timed_out"
        error = f"Timeout after {timeout_seconds} seconds"
        stdout = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        stderr = (exc.stderr or "") if isinstance(exc.stderr, str) else ""
    except Exception as exc:
        status = "failed"
        error = f"{type(exc).__name__}: {exc}"
    finished_at = datetime.now(timezone.utc).isoformat()
    duration = time.perf_counter() - started_clock
    stdout_path.write_text(stdout, encoding="utf-8", errors="replace")
    stderr_path.write_text((stderr + ("\n" + error if error else "")), encoding="utf-8", errors="replace")
    executable_hash = ""
    if resolution.backend != "wsl" and resolution.executable:
        executable_hash = _sha256_file(resolution.executable)
    payload = {
        "schema": "biointel.tool-execution.v1",
        "name": name,
        "backend": resolution.backend,
        "executable": resolution.executable,
        "executable_sha256": executable_hash,
        "command": list(command),
        "arguments": [str(value) for value in arguments],
        "cwd": str(cwd) if cwd is not None else "",
        "returncode": returncode,
        "allowed_exit_codes": [int(value) for value in allowed_exit_codes],
        "status": status,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_seconds": round(duration, 6),
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "error": error,
    }
    atomic_write_json(manifest_path, payload)
    result = ToolExecutionResult(
        name=name,
        backend=resolution.backend,
        executable=str(resolution.executable),
        command=command,
        returncode=returncode,
        started_at=started_at,
        finished_at=finished_at,
        duration_seconds=round(duration, 6),
        stdout_path=str(stdout_path),
        stderr_path=str(stderr_path),
        manifest_path=str(manifest_path),
        executable_sha256=executable_hash,
        status=status,
    )
    if status != "completed":
        raise RuntimeError(f"{name} execution {status}; see {stderr_path}")
    return result


def verified_tool_status(name: str) -> dict[str, object]:
    """Return path, version and binary hash for an installed executable."""
    resolution = resolve_tool(name)
    payload: dict[str, object] = resolution.to_dict()
    payload["version"] = tool_version(name) if resolution.available else "Unavailable"
    payload["executable_sha256"] = (
        _sha256_file(resolution.executable)
        if resolution.available and resolution.backend != "wsl" and resolution.executable
        else ""
    )
    return payload
