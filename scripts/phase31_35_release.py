from __future__ import annotations

import argparse
import hashlib
import json
import os
import py_compile
import shutil
import subprocess
import sys
import textwrap
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

RELEASE_NAME = "BioIntel-AI-Phase31-to-35-Production-Windows"
PRODUCTION_ZIP_NAME = f"{RELEASE_NAME}.zip"
INSTALLER_NAME = "BioIntel-AI-Windows-Installer.exe"
DEVELOPER_PREFIX = "BioIntel-AI-Phase31-to-35-Developer-Source"
DEVELOPER_ROOT = f"{DEVELOPER_PREFIX}/"
PHASE_VERSION = "31-35"

RUNTIME_APP_DIRECTORIES = (
    ".streamlit",
    "assets",
    "brand",
    "config",
    "data",
    "engine-packs",
    "models",
    "pages",
    "platform",
    "research",
    "src",
    "store",
    "visual",
    "workspace",
)

DEVELOPER_EXCLUDED_DIRECTORIES = {
    ".git",
    ".pytest_cache",
    ".qualification",
    ".release_parts",
    ".ruff_cache",
    ".test-tmp",
    ".test-user-data-phase23",
    ".test-user-data-regression",
    ".test-user-data-regression-final",
    ".test-user-data-streamlit",
    ".test-user-data-streamlit-auth",
    ".venv",
    "UserData",
    "__pycache__",
    "pytest-of-lavesh dobriyal",
    "work",
}

COPY_IGNORED_DIRECTORIES = {
    ".git",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
}

ALLOWED_PRODUCTION_BOOTSTRAPS = {
    "app.py",
    "launcher/boot.py",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def reset_directory(path: Path, allowed_parent: Path) -> None:
    resolved = path.resolve()
    if not is_within(resolved, allowed_parent) or resolved == allowed_parent.resolve():
        raise RuntimeError(f"Refusing to reset unsafe path: {resolved}")
    if resolved.exists():
        shutil.rmtree(resolved)
    resolved.mkdir(parents=True, exist_ok=True)


def copytree_filtered(source: Path, destination: Path, *, skip_site_packages: bool = False) -> None:
    source = source.resolve()

    def ignore(directory: str, names: list[str]) -> set[str]:
        relative = Path(directory).resolve().relative_to(source)
        ignored = {name for name in names if name in COPY_IGNORED_DIRECTORIES}
        if skip_site_packages and relative.as_posix().lower() == "lib":
            ignored.add("site-packages")
        return ignored

    shutil.copytree(source, destination, dirs_exist_ok=True, ignore=ignore)


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8", newline="\n")


def compile_to_pyc(source: Path, destination: Path, display_name: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    py_compile.compile(
        str(source),
        cfile=str(destination),
        dfile=display_name,
        doraise=True,
        optimize=2,
    )


def bootstrap_source(target_expression: str) -> str:
    return textwrap.dedent(
        f"""\
        # Generic bytecode bootstrap. Application source is not present in this package.
        import marshal
        from pathlib import Path

        _target = {target_expression}
        _payload = _target.read_bytes()
        if len(_payload) < 17:
            raise RuntimeError("Protected application payload is invalid.")
        exec(marshal.loads(_payload[16:]), globals(), globals())
        """
    )


SUPERVISOR_SOURCE = r'''
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "app"
RUNTIME = ROOT / "runtime"
PYTHONW = RUNTIME / "pythonw.exe"
DATA = Path(os.environ.get("BIOINTEL_USER_DATA_DIR", Path(os.environ.get("LOCALAPPDATA", ROOT)) / "BioIntelAI" / "UserData"))
STATE = DATA / "desktop-state.json"
STOP = DATA / "desktop-stop.signal"
LOG = DATA / "launcher.log"


def log(message: str) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {message}\n")


def health(port: int, timeout: float = 1.0) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/_stcore/health", timeout=timeout) as response:
            return response.status == 200 and response.read(32).strip() == b"ok"
    except Exception:
        return False


def prior_instance() -> bool:
    try:
        state = json.loads(STATE.read_text(encoding="utf-8"))
        if Path(state["root"]).resolve() != ROOT.resolve():
            return False
        port = int(state["port"])
        if health(port):
            webbrowser.open(f"http://127.0.0.1:{port}", new=1)
            return True
    except Exception:
        return False
    return False


def reserve_port() -> int:
    for port in range(8501, 8600):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError("No available local BioIntel AI port was found.")


def main() -> int:
    DATA.mkdir(parents=True, exist_ok=True)
    STOP.unlink(missing_ok=True)
    if prior_instance():
        return 0
    if not PYTHONW.exists():
        log(f"Runtime missing: {PYTHONW}")
        return 2

    port = reserve_port()
    environment = os.environ.copy()
    environment["BIOINTEL_USER_DATA_DIR"] = str(DATA)
    environment["PYTHONUTF8"] = "1"
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    command = [
        str(PYTHONW),
        "-m",
        "streamlit",
        "run",
        "app.py",
        "--server.headless=true",
        f"--server.port={port}",
        "--server.address=127.0.0.1",
        "--browser.gatherUsageStats=false",
        "--global.developmentMode=false",
    ]
    backend = subprocess.Popen(
        command,
        cwd=str(APP),
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags,
    )
    state = {
        "root": str(ROOT),
        "port": port,
        "supervisor_pid": os.getpid(),
        "backend_pid": backend.pid,
        "started_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    ready = False
    for _ in range(120):
        if backend.poll() is not None:
            break
        if health(port):
            ready = True
            break
        time.sleep(0.5)
    if not ready:
        if backend.poll() is None:
            backend.terminate()
        log(f"Startup failed on port {port}; backend exit={backend.poll()}")
        STATE.unlink(missing_ok=True)
        return 3

    log(f"Started backend pid={backend.pid} port={port}")
    webbrowser.open(f"http://127.0.0.1:{port}", new=1)
    try:
        while backend.poll() is None:
            if STOP.exists():
                backend.terminate()
                try:
                    backend.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    backend.kill()
                    backend.wait(timeout=5)
                break
            time.sleep(0.25)
        return int(backend.returncode or 0)
    finally:
        STOP.unlink(missing_ok=True)
        STATE.unlink(missing_ok=True)
        log(f"Stopped backend pid={backend.pid}")


if __name__ == "__main__":
    raise SystemExit(main())
'''


STOPPER_SOURCE = r'''
from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(os.environ.get("BIOINTEL_USER_DATA_DIR", Path(os.environ.get("LOCALAPPDATA", ROOT)) / "BioIntelAI" / "UserData"))
STATE = DATA / "desktop-state.json"
STOP = DATA / "desktop-stop.signal"


def health(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/_stcore/health", timeout=2.0) as response:
            return response.status == 200
    except Exception:
        return False


def stop_pid(pid: int) -> None:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.run(
        ["taskkill.exe", "/PID", str(pid), "/T", "/F"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags,
        check=False,
    )


def main() -> int:
    try:
        state = json.loads(STATE.read_text(encoding="utf-8"))
        if Path(state["root"]).resolve() != ROOT.resolve():
            return 2
        if not health(int(state["port"])):
            STATE.unlink(missing_ok=True)
            return 0
        STOP.write_text("stop\n", encoding="utf-8")
        for _ in range(80):
            if not health(int(state["port"])):
                return 0
            time.sleep(0.25)
        stop_pid(int(state["backend_pid"]))
        stop_pid(int(state["supervisor_pid"]))
        return 0 if not health(int(state["port"])) else 4
    except FileNotFoundError:
        return 0
    except Exception:
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
'''


INSTALL_SCRIPT = r'''
[CmdletBinding()]
param(
    [string]$PackageZip = (Join-Path $PSScriptRoot "BioIntel-AI-Phase31-to-35-Production-Windows.zip"),
    [string]$TargetRoot = $env:BIOINTEL_INSTALL_ROOT,
    [switch]$NoLaunch
)

$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($TargetRoot)) {
    $TargetRoot = Join-Path $env:LOCALAPPDATA "BioIntelAI"
}
$TargetRoot = [IO.Path]::GetFullPath($TargetRoot)
$PackageZip = [IO.Path]::GetFullPath($PackageZip)
if (-not (Test-Path -LiteralPath $PackageZip -PathType Leaf)) {
    throw "Production package not found: $PackageZip"
}

$current = Join-Path $TargetRoot "current"
$rollback = Join-Path $TargetRoot "rollback"
$staging = Join-Path $TargetRoot (".installing-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $TargetRoot, $rollback, $staging | Out-Null

try {
    Expand-Archive -LiteralPath $PackageZip -DestinationPath $staging -Force
    $payload = Join-Path $staging "BioIntel-AI-Phase31-to-35-Production-Windows"
    if (-not (Test-Path -LiteralPath (Join-Path $payload "BioIntel AI.vbs") -PathType Leaf)) {
        throw "The production package is missing its verified launcher."
    }
    if (Test-Path -LiteralPath $current) {
        $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
        Move-Item -LiteralPath $current -Destination (Join-Path $rollback $stamp)
    }
    Move-Item -LiteralPath $payload -Destination $current
    @{
        installed_at_utc = [DateTime]::UtcNow.ToString("o")
        package = [IO.Path]::GetFileName($PackageZip)
        target = $current
        version = "Phase31-35"
    } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $TargetRoot "install-state.json") -Encoding UTF8

    try {
        $shell = New-Object -ComObject WScript.Shell
        $shortcutPath = Join-Path ([Environment]::GetFolderPath("Desktop")) "BioIntel AI.lnk"
        $shortcut = $shell.CreateShortcut($shortcutPath)
        $shortcut.TargetPath = Join-Path $current "BioIntel AI.vbs"
        $shortcut.WorkingDirectory = $current
        $shortcut.Description = "BioIntel AI Phase 31-35"
        $shortcut.Save()
    } catch {
        Write-Warning "Desktop shortcut could not be created: $($_.Exception.Message)"
    }

    if (-not $NoLaunch -and $env:BIOINTEL_INSTALL_NO_LAUNCH -ne "1") {
        Start-Process -FilePath "wscript.exe" -ArgumentList ('"' + (Join-Path $current "BioIntel AI.vbs") + '"')
    }
    Write-Output "BIOINTEL_INSTALL_OK=$current"
} finally {
    if (Test-Path -LiteralPath $staging) {
        Remove-Item -LiteralPath $staging -Recurse -Force
    }
}
'''


INSTALL_VBS = r'''
Option Explicit
Dim fso, shell, folder, ps1, archive, command
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
folder = fso.GetParentFolderName(WScript.ScriptFullName)
ps1 = fso.BuildPath(folder, "install.ps1")
archive = fso.BuildPath(shell.CurrentDirectory, "BioIntel-AI-Phase31-to-35-Production-Windows.zip")
If Not fso.FileExists(archive) Then
    archive = fso.BuildPath(folder, "BioIntel-AI-Phase31-to-35-Production-Windows.zip")
End If
If Not fso.FileExists(archive) Then
    MsgBox "Keep the production ZIP beside the installer and run it again.", 16, "BioIntel AI Installer"
    WScript.Quit 2
End If
command = "powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & ps1 & """ -PackageZip """ & archive & """"
shell.Run command, 0, True
'''


UNINSTALL_SCRIPT = r'''
[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$TargetRoot = $env:BIOINTEL_INSTALL_ROOT
)
$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($TargetRoot)) {
    $TargetRoot = Join-Path $env:LOCALAPPDATA "BioIntelAI"
}
$TargetRoot = [IO.Path]::GetFullPath($TargetRoot)
$current = Join-Path $TargetRoot "current"
if (Test-Path -LiteralPath (Join-Path $current "Stop BioIntel AI.vbs")) {
    Start-Process -FilePath "wscript.exe" -ArgumentList ('"' + (Join-Path $current "Stop BioIntel AI.vbs") + '"') -Wait
}
if (Test-Path -LiteralPath $current) {
    Remove-Item -LiteralPath $current -Recurse -Force
}
$state = Join-Path $TargetRoot "install-state.json"
if (Test-Path -LiteralPath $state) {
    Remove-Item -LiteralPath $state -Force
}
Write-Output "BioIntel AI application files were removed. UserData and rollback copies were preserved."
'''


ROLLBACK_SCRIPT = r'''
[CmdletBinding()]
param(
    [string]$TargetRoot = $env:BIOINTEL_INSTALL_ROOT
)
$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($TargetRoot)) {
    $TargetRoot = Join-Path $env:LOCALAPPDATA "BioIntelAI"
}
$TargetRoot = [IO.Path]::GetFullPath($TargetRoot)
$current = Join-Path $TargetRoot "current"
$rollback = Join-Path $TargetRoot "rollback"
$previous = Get-ChildItem -LiteralPath $rollback -Directory -ErrorAction Stop | Sort-Object Name -Descending | Select-Object -First 1
if (-not $previous) { throw "No rollback release is available." }
$failed = Join-Path $TargetRoot ("failed-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
if (Test-Path -LiteralPath $current) { Move-Item -LiteralPath $current -Destination $failed }
Move-Item -LiteralPath $previous.FullName -Destination $current
Write-Output "BIOINTEL_ROLLBACK_OK=$current"
'''


def create_compiled_launcher(stage: Path, build_temp: Path) -> None:
    launcher = stage / "launcher"
    protected = launcher / "_protected"
    protected.mkdir(parents=True, exist_ok=True)
    write_text(
        launcher / "boot.py",
        textwrap.dedent(
            """\
            # Generic launcher bootstrap. Product implementation is stored as bytecode.
            import marshal
            import sys
            from pathlib import Path

            _name = sys.argv[1] if len(sys.argv) > 1 else "supervisor"
            if _name not in {"supervisor", "stopper"}:
                raise SystemExit(2)
            _target = Path(__file__).with_name("_protected") / f"{_name}.pyc"
            _namespace = {"__name__": "__main__", "__file__": str(_target)}
            exec(marshal.loads(_target.read_bytes()[16:]), _namespace, _namespace)
            """
        ),
    )
    sources = {
        "supervisor": SUPERVISOR_SOURCE,
        "stopper": STOPPER_SOURCE,
    }
    for name, source in sources.items():
        temporary = build_temp / f"{name}.py"
        write_text(temporary, textwrap.dedent(source).lstrip())
        compile_to_pyc(temporary, protected / f"{name}.pyc", f"launcher/{name}.py")

    launch_vbs = textwrap.dedent(
        r'''
        Option Explicit
        Dim fso, shell, root, pythonw, boot, command
        Set fso = CreateObject("Scripting.FileSystemObject")
        Set shell = CreateObject("WScript.Shell")
        root = fso.GetParentFolderName(WScript.ScriptFullName)
        pythonw = fso.BuildPath(root, "runtime\pythonw.exe")
        boot = fso.BuildPath(root, "launcher\boot.py")
        command = """" & pythonw & """ """ & boot & """ supervisor"
        shell.Run command, 0, False
        '''
    ).lstrip()
    stop_vbs = textwrap.dedent(
        r'''
        Option Explicit
        Dim fso, shell, root, pythonw, boot, command
        Set fso = CreateObject("Scripting.FileSystemObject")
        Set shell = CreateObject("WScript.Shell")
        root = fso.GetParentFolderName(WScript.ScriptFullName)
        pythonw = fso.BuildPath(root, "runtime\pythonw.exe")
        boot = fso.BuildPath(root, "launcher\boot.py")
        command = """" & pythonw & """ """ & boot & """ stopper"
        shell.Run command, 0, True
        '''
    ).lstrip()
    write_text(stage / "BioIntel AI.vbs", launch_vbs)
    write_text(stage / "Stop BioIntel AI.vbs", stop_vbs)


def copy_runtime(python_home: Path, venv_site_packages: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for filename in (
        "LICENSE.txt",
        "python.exe",
        "python3.dll",
        "python311.dll",
        "pythonw.exe",
        "vcruntime140.dll",
        "vcruntime140_1.dll",
    ):
        source = python_home / filename
        if source.exists():
            shutil.copy2(source, destination / filename)
    copytree_filtered(python_home / "DLLs", destination / "DLLs")
    copytree_filtered(python_home / "Lib", destination / "Lib", skip_site_packages=True)
    copytree_filtered(venv_site_packages, destination / "Lib" / "site-packages")


def protect_application(app_directory: Path, build_temp: Path) -> dict[str, int]:
    original_app = app_directory / "app.py"
    protected_app = app_directory / "_protected" / "app.pyc"
    compile_to_pyc(original_app, protected_app, "app.py")
    write_text(
        original_app,
        bootstrap_source("Path(__file__).with_name('_protected') / 'app.pyc'"),
    )

    protected_pages = app_directory / "_protected_pages"
    page_sources = sorted((app_directory / "pages").rglob("*.py"))
    for page in page_sources:
        relative = page.relative_to(app_directory / "pages")
        destination = protected_pages / relative.with_suffix(".pyc")
        compile_to_pyc(page, destination, f"pages/{relative.as_posix()}")
        expression = (
            "Path(__file__).resolve().parents[1] / '_protected_pages' / "
            f"{relative.with_suffix('.pyc').as_posix()!r}"
        )
        write_text(page, bootstrap_source(expression))

    compiled_other = 0
    for source in sorted(app_directory.rglob("*.py")):
        relative = source.relative_to(app_directory).as_posix()
        if relative == "app.py" or relative.startswith("pages/"):
            continue
        destination = source.with_suffix(".pyc")
        compile_to_pyc(source, destination, relative)
        source.unlink()
        compiled_other += 1
    return {
        "page_sources_protected": len(page_sources),
        "other_sources_protected": compiled_other,
        "total_sources_protected": 1 + len(page_sources) + compiled_other,
    }


def production_source_leak_scan(stage: Path) -> dict[str, object]:
    app = stage / "app"
    raw_python = sorted(path.relative_to(app).as_posix() for path in app.rglob("*.py"))
    unexpected = [
        name
        for name in raw_python
        if name not in ALLOWED_PRODUCTION_BOOTSTRAPS and not name.startswith("pages/")
    ]
    page_bootstraps = [name for name in raw_python if name.startswith("pages/")]
    readable_python_outside_runtime = sorted(
        path.relative_to(stage).as_posix()
        for path in stage.rglob("*.py")
        if "runtime/Lib/" not in path.relative_to(stage).as_posix()
    )
    return {
        "passed": not unexpected,
        "unexpected_raw_proprietary_python": unexpected,
        "allowed_generic_bootstraps": raw_python,
        "page_bootstrap_count": len(page_bootstraps),
        "readable_python_outside_runtime": readable_python_outside_runtime,
    }


def zip_directory(source: Path, destination: Path, root_name: str) -> dict[str, int]:
    files = sorted(
        path
        for path in source.rglob("*")
        if path.is_file() and "__pycache__" not in path.relative_to(source).parts
    )
    with zipfile.ZipFile(
        destination,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=6,
        allowZip64=True,
    ) as archive:
        for path in files:
            relative = path.relative_to(source).as_posix()
            archive.write(path, f"{root_name}/{relative}")
    return {"file_count": len(files), "archive_bytes": destination.stat().st_size}


def validate_protected_runtime(stage: Path) -> None:
    app = stage / "app"
    runtime_python = stage / "runtime" / "python.exe"
    import_check = (
        "import sys; "
        f"sys.path.insert(0, {str(app / 'src')!r}); "
        "import biointel; "
        "from biointel.education.phase32_35.sync import SyncEngine; "
        "from biointel.education.phase32_35.twin import DigitalTwinLab; "
        "from biointel.education.phase32_35.compute import ResearchCompute; "
        "from biointel.education.phase32_35.discovery import DiscoveryEcosystem; "
        "print('PROTECTED_IMPORT_OK')"
    )
    result = subprocess.run(
        [str(runtime_python), "-c", import_check],
        cwd=str(app),
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )
    if result.returncode != 0 or "PROTECTED_IMPORT_OK" not in result.stdout:
        raise RuntimeError(
            "Protected runtime import check failed:\n"
            f"stdout={result.stdout}\nstderr={result.stderr}"
        )


def build_production(args: argparse.Namespace) -> None:
    root = args.root.resolve()
    output = args.output.resolve()
    work = args.work.resolve()
    output.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    stage = work / RELEASE_NAME
    reset_directory(stage, work)
    app = stage / "app"
    app.mkdir(parents=True, exist_ok=True)

    shutil.copy2(root / "app.py", app / "app.py")
    for filename in ("VERSION", "LICENSE", "LICENSE.txt", "NOTICE", "NOTICE.txt"):
        source = root / filename
        if source.exists():
            shutil.copy2(source, app / filename)
    for name in RUNTIME_APP_DIRECTORIES:
        source = root / name
        if source.exists():
            copytree_filtered(source, app / name)

    build_temp = work / "_compiler_inputs"
    reset_directory(build_temp, work)
    protection = protect_application(app, build_temp)
    copy_runtime(args.python_home.resolve(), args.venv_site.resolve(), stage / "runtime")
    create_compiled_launcher(stage, build_temp)

    write_text(stage / "Uninstall-BioIntel.ps1", textwrap.dedent(UNINSTALL_SCRIPT).lstrip())
    write_text(stage / "Rollback-BioIntel.ps1", textwrap.dedent(ROLLBACK_SCRIPT).lstrip())
    write_text(
        stage / "README-FIRST.txt",
        textwrap.dedent(
            """\
            BioIntel AI Phase 31-35 - Windows Production Distribution

            Start: double-click "BioIntel AI.vbs".
            Stop: double-click "Stop BioIntel AI.vbs".

            The application opens in the default browser while all backend processes
            remain hidden. User data is stored separately under LocalAppData\\BioIntelAI\\UserData.
            Biomedical Twin and Discovery features are research/education-only and are
            not clinical diagnostic or treatment systems.
            """
        ),
    )

    leak = production_source_leak_scan(stage)
    if not leak["passed"]:
        raise RuntimeError(f"Production source leak scan failed: {leak}")

    verification = {
        "generated_at_utc": utc_now(),
        "phase": PHASE_VERSION,
        "python": sys.version,
        "protection": protection,
        "source_leak_scan": leak,
        "runtime": {
            "python_exe": "runtime/python.exe",
            "pythonw_exe": "runtime/pythonw.exe",
            "streamlit_version": "1.58.0",
        },
    }
    write_text(
        stage / "PRODUCTION_BUILD_VERIFICATION.json",
        json.dumps(verification, indent=2, sort_keys=True),
    )

    validate_protected_runtime(stage)

    destination = output / PRODUCTION_ZIP_NAME
    destination.unlink(missing_ok=True)
    archive = zip_directory(stage, destination, RELEASE_NAME)
    print(
        json.dumps(
            {
                "status": "ok",
                "production_zip": str(destination),
                "sha256": sha256(destination),
                **archive,
                **protection,
            },
            indent=2,
        )
    )


def resume_production(args: argparse.Namespace) -> None:
    output = args.output.resolve()
    work = args.work.resolve()
    stage = work / RELEASE_NAME
    verification_path = stage / "PRODUCTION_BUILD_VERIFICATION.json"
    if not verification_path.exists():
        raise FileNotFoundError(
            "No verified staged production build is available; run the production command first."
        )
    leak = production_source_leak_scan(stage)
    if not leak["passed"]:
        raise RuntimeError(f"Production source leak scan failed: {leak}")
    validate_protected_runtime(stage)
    output.mkdir(parents=True, exist_ok=True)
    destination = output / PRODUCTION_ZIP_NAME
    destination.unlink(missing_ok=True)
    archive = zip_directory(stage, destination, RELEASE_NAME)
    verification = json.loads(verification_path.read_text(encoding="utf-8"))
    print(
        json.dumps(
            {
                "status": "ok",
                "production_zip": str(destination),
                "sha256": sha256(destination),
                **archive,
                **verification["protection"],
            },
            indent=2,
        )
    )


def developer_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(part in DEVELOPER_EXCLUDED_DIRECTORIES for part in relative.parts):
            continue
        if path.suffix.lower() in {".pyc", ".pyo"}:
            continue
        files.append(path)
    return sorted(files, key=lambda item: item.relative_to(root).as_posix().lower())


def partition_balanced(files: list[Path], count: int) -> list[list[Path]]:
    groups: list[list[Path]] = [[] for _ in range(count)]
    sizes = [0 for _ in range(count)]
    for path in sorted(files, key=lambda item: item.stat().st_size, reverse=True):
        index = sizes.index(min(sizes))
        groups[index].append(path)
        sizes[index] += path.stat().st_size
    for group in groups:
        group.sort(key=lambda item: item.as_posix().lower())
    return groups


def build_developer(args: argparse.Namespace) -> None:
    root = args.root.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    files = developer_files(root)
    groups = partition_balanced(files, args.parts)
    generated: list[dict[str, object]] = []
    for index, group in enumerate(groups, start=1):
        destination = output / f"{DEVELOPER_PREFIX}-Part{index}.zip"
        destination.unlink(missing_ok=True)
        entries = []
        with zipfile.ZipFile(
            destination,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=6,
            allowZip64=True,
        ) as archive:
            for path in group:
                relative = path.relative_to(root).as_posix()
                archive.write(path, f"{DEVELOPER_ROOT}{relative}")
                entries.append(
                    {
                        "path": relative,
                        "bytes": path.stat().st_size,
                        "sha256": sha256(path),
                    }
                )
            archive.writestr(
                f"{DEVELOPER_ROOT}PART{index}_MANIFEST.json",
                json.dumps(
                    {
                        "part": index,
                        "part_count": args.parts,
                        "generated_at_utc": utc_now(),
                        "readable_source": True,
                        "entries": entries,
                    },
                    indent=2,
                    sort_keys=True,
                ),
            )
        generated.append(
            {
                "path": str(destination),
                "file_count": len(group),
                "uncompressed_bytes": sum(path.stat().st_size for path in group),
                "archive_bytes": destination.stat().st_size,
                "sha256": sha256(destination),
            }
        )
        print(f"BUILT_DEVELOPER_PART={index}/{args.parts} FILES={len(group)}")
    print(json.dumps({"status": "ok", "parts": generated}, indent=2))


def installer_sed(payload: Path, output: Path, sed_path: Path) -> None:
    files = [
        payload / "install.vbs",
        payload / "install.ps1",
    ]
    lines = [
        "[Version]",
        "Class=IEXPRESS",
        "SEDVersion=3",
        "[Options]",
        "PackagePurpose=InstallApp",
        "ShowInstallProgramWindow=1",
        "HideExtractAnimation=1",
        "UseLongFileName=1",
        "InsideCompressed=0",
        "CAB_FixedSize=0",
        "CAB_ResvCodeSigning=0",
        "RebootMode=N",
        "InstallPrompt=%InstallPrompt%",
        "DisplayLicense=%DisplayLicense%",
        "FinishMessage=%FinishMessage%",
        f"TargetName={output}",
        "FriendlyName=%FriendlyName%",
        "AppLaunched=%AppLaunched%",
        "PostInstallCmd=%PostInstallCmd%",
        "AdminQuietInstCmd=",
        "UserQuietInstCmd=",
        "SourceFiles=SourceFiles",
        "[SourceFiles]",
        f"SourceFiles0={payload}\\",
        "[SourceFiles0]",
        *(f"%FILE{index}%=" for index in range(len(files))),
        "[Strings]",
        "InstallPrompt=",
        "DisplayLicense=",
        "FinishMessage=",
        "FriendlyName=BioIntel AI Phase 31-35 Installer",
        "AppLaunched=wscript.exe install.vbs",
        "PostInstallCmd=<None>",
        *(f'FILE{index}="{path.name}"' for index, path in enumerate(files)),
    ]
    value = "\n".join(lines) + "\n"
    write_text(sed_path, value)


def installer_csharp_source() -> str:
    embedded_script = textwrap.dedent(INSTALL_SCRIPT).lstrip().replace('"', '""')
    return textwrap.dedent(
        f'''\
        using System;
        using System.Diagnostics;
        using System.IO;
        using System.Text;
        using System.Windows.Forms;

        internal static class BioIntelInstaller
        {{
            private const string ArchiveName = "{PRODUCTION_ZIP_NAME}";
            private const string InstallScript = @"{embedded_script}";

            [STAThread]
            private static int Main()
            {{
                bool silent = Environment.GetEnvironmentVariable("BIOINTEL_INSTALL_SILENT") == "1";
                string directory = AppDomain.CurrentDomain.BaseDirectory;
                string archive = Path.Combine(directory, ArchiveName);
                if (!File.Exists(archive))
                {{
                    if (!silent)
                    {{
                        MessageBox.Show(
                            "Keep " + ArchiveName + " beside this installer and run it again.",
                            "BioIntel AI Installer",
                            MessageBoxButtons.OK,
                            MessageBoxIcon.Error
                        );
                    }}
                    return 2;
                }}

                string script = Path.Combine(
                    Path.GetTempPath(),
                    "BioIntel-Install-" + Guid.NewGuid().ToString("N") + ".ps1"
                );
                try
                {{
                    File.WriteAllText(script, InstallScript, new UTF8Encoding(false));
                    ProcessStartInfo start = new ProcessStartInfo();
                    start.FileName = "powershell.exe";
                    start.Arguments =
                        "-NoLogo -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File \\"" +
                        script + "\\" -PackageZip \\"" + archive + "\\"";
                    start.WorkingDirectory = directory;
                    start.UseShellExecute = false;
                    start.CreateNoWindow = true;
                    start.WindowStyle = ProcessWindowStyle.Hidden;
                    using (Process process = Process.Start(start))
                    {{
                        process.WaitForExit();
                        if (process.ExitCode != 0)
                        {{
                            if (!silent)
                            {{
                                MessageBox.Show(
                                    "Installation did not complete. Exit code: " + process.ExitCode,
                                    "BioIntel AI Installer",
                                    MessageBoxButtons.OK,
                                    MessageBoxIcon.Error
                                );
                            }}
                            return process.ExitCode;
                        }}
                    }}
                    if (!silent)
                    {{
                        MessageBox.Show(
                            "BioIntel AI was installed successfully.",
                            "BioIntel AI Installer",
                            MessageBoxButtons.OK,
                            MessageBoxIcon.Information
                        );
                    }}
                    return 0;
                }}
                catch (Exception error)
                {{
                    if (!silent)
                    {{
                        MessageBox.Show(
                            error.Message,
                            "BioIntel AI Installer",
                            MessageBoxButtons.OK,
                            MessageBoxIcon.Error
                        );
                    }}
                    return 1;
                }}
                finally
                {{
                    try {{ if (File.Exists(script)) File.Delete(script); }} catch {{ }}
                }}
            }}
        }}
        '''
    )


def build_installer(args: argparse.Namespace) -> None:
    output = args.output.resolve()
    work = args.work.resolve()
    output.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    production_zip = output / PRODUCTION_ZIP_NAME
    if not production_zip.exists():
        raise FileNotFoundError(production_zip)
    payload = work / "installer_payload"
    reset_directory(payload, work)
    write_text(payload / "install.ps1", textwrap.dedent(INSTALL_SCRIPT).lstrip())
    write_text(payload / "install.vbs", textwrap.dedent(INSTALL_VBS).lstrip())
    destination = output / INSTALLER_NAME
    destination.unlink(missing_ok=True)
    compiled_installer = (
        Path(os.environ.get("TEMP", str(work)))
        / f"BioIntel-AI-Windows-Installer-{os.getpid()}.bin"
    )
    compiled_installer.unlink(missing_ok=True)
    source_path = work / "BioIntel-Installer.cs"
    write_text(source_path, installer_csharp_source())
    csc = (
        Path(os.environ.get("SystemRoot", r"C:\Windows"))
        / "Microsoft.NET"
        / "Framework64"
        / "v4.0.30319"
        / "csc.exe"
    )
    if not csc.exists():
        csc = (
            Path(os.environ.get("SystemRoot", r"C:\Windows"))
            / "Microsoft.NET"
            / "Framework"
            / "v4.0.30319"
            / "csc.exe"
        )
    result = subprocess.run(
        [
            str(csc),
            "/nologo",
            "/target:winexe",
            "/platform:anycpu",
            "/optimize+",
            "/reference:System.Windows.Forms.dll",
            f"/out:{compiled_installer}",
            str(source_path),
        ],
        cwd=str(work),
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )
    if result.returncode != 0 or not compiled_installer.exists():
        raise RuntimeError(
            f"Native installer compilation failed ({result.returncode}).\n"
            f"stdout={result.stdout}\nstderr={result.stderr}"
        )
    if compiled_installer.read_bytes()[:2] != b"MZ":
        raise RuntimeError("Native installer does not have a valid Windows PE header.")
    shutil.copy2(compiled_installer, destination)
    compiled_installer.unlink(missing_ok=True)
    print(
        json.dumps(
            {
                "status": "ok",
                "installer": str(destination),
                "archive_bytes": destination.stat().st_size,
                "sha256": sha256(destination),
            },
            indent=2,
        )
    )


def test_install(args: argparse.Namespace) -> None:
    output = args.output.resolve()
    work = args.work.resolve()
    payload_script = work / "installer_payload" / "install.ps1"
    production_zip = output / PRODUCTION_ZIP_NAME
    test_root = work / "installer_test" / "BioIntelAI"
    reset_directory(test_root.parent, work)
    test_root.mkdir(parents=True, exist_ok=True)
    old_current = test_root / "current"
    old_current.mkdir(parents=True)
    write_text(old_current / "upgrade-marker.txt", "previous release")
    powershell = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    command = [
        str(powershell),
        "-NoLogo",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(payload_script),
        "-PackageZip",
        str(production_zip),
        "-TargetRoot",
        str(test_root),
        "-NoLaunch",
    ]
    result = subprocess.run(
        command,
        text=True,
        capture_output=True,
        timeout=900,
        check=False,
    )
    current = test_root / "current"
    rollback_markers = list((test_root / "rollback").rglob("upgrade-marker.txt"))
    passed = (
        result.returncode == 0
        and (current / "BioIntel AI.vbs").exists()
        and (current / "runtime" / "pythonw.exe").exists()
        and len(rollback_markers) == 1
    )
    report = {
        "passed": passed,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "upgrade_backup_count": len(rollback_markers),
        "launcher_present": (current / "BioIntel AI.vbs").exists(),
        "runtime_present": (current / "runtime" / "pythonw.exe").exists(),
        "test_root": str(test_root),
    }
    report_path = work / "installer-test-report.json"
    write_text(report_path, json.dumps(report, indent=2))
    if not passed:
        raise RuntimeError(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


def verify_archives(args: argparse.Namespace) -> None:
    output = args.output.resolve()
    results: list[dict[str, object]] = []
    developer_entries: dict[str, dict[str, object]] = {}
    developer_archive_names: set[str] = set()
    for path in sorted(output.glob("*.zip")):
        with zipfile.ZipFile(path) as archive:
            bad = archive.testzip()
            names = archive.namelist()
            if path.name.startswith(DEVELOPER_PREFIX):
                manifest_names = [
                    name
                    for name in names
                    if name.startswith(f"{DEVELOPER_ROOT}PART")
                    and name.endswith("_MANIFEST.json")
                    and "/" not in name.removeprefix(DEVELOPER_ROOT)
                ]
                if len(manifest_names) != 1:
                    raise RuntimeError(
                        f"{path.name} does not contain exactly one part manifest."
                    )
                part_manifest = json.loads(
                    archive.read(manifest_names[0]).decode("utf-8")
                )
                for entry in part_manifest["entries"]:
                    name = str(entry["path"])
                    if name in developer_entries:
                        raise RuntimeError(f"Duplicate developer source entry: {name}")
                    developer_entries[name] = entry
                developer_archive_names.update(
                    name.removeprefix(DEVELOPER_ROOT)
                    for name in names
                    if name.startswith(DEVELOPER_ROOT)
                    and name not in manifest_names
                )
        result = {
            "path": path.name,
            "passed": bad is None,
            "first_bad_entry": bad,
            "entry_count": len(names),
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
        if path.name == PRODUCTION_ZIP_NAME:
            raw_proprietary = [
                name
                for name in names
                if name.startswith(f"{RELEASE_NAME}/app/")
                and name.endswith(".py")
                and not name.startswith(f"{RELEASE_NAME}/app/pages/")
                and name
                not in {
                    f"{RELEASE_NAME}/app/app.py",
                    f"{RELEASE_NAME}/launcher/boot.py",
                }
            ]
            result["unexpected_raw_proprietary_python"] = raw_proprietary
            required_prefixes = [
                f"{RELEASE_NAME}/app/src/",
                f"{RELEASE_NAME}/app/pages/",
                f"{RELEASE_NAME}/app/data/",
                f"{RELEASE_NAME}/runtime/Lib/site-packages/",
                f"{RELEASE_NAME}/launcher/_protected/",
            ]
            missing_prefixes = [
                prefix
                for prefix in required_prefixes
                if not any(name.startswith(prefix) for name in names)
            ]
            result["missing_required_prefixes"] = missing_prefixes
            result["passed"] = (
                result["passed"] and not raw_proprietary and not missing_prefixes
            )
        results.append(result)
    expected_files = developer_files(args.root.resolve())
    expected_names = {
        path.relative_to(args.root.resolve()).as_posix() for path in expected_files
    }
    mismatches = []
    for path in expected_files:
        name = path.relative_to(args.root.resolve()).as_posix()
        entry = developer_entries.get(name)
        if (
            entry is None
            or int(entry["bytes"]) != path.stat().st_size
            or str(entry["sha256"]) != sha256(path)
        ):
            mismatches.append(name)
    developer_verification = {
        "expected_file_count": len(expected_names),
        "packaged_manifest_file_count": len(developer_entries),
        "packaged_archive_file_count": len(developer_archive_names),
        "missing": sorted(expected_names - developer_archive_names),
        "unexpected": sorted(developer_archive_names - expected_names),
        "hash_or_size_mismatches": mismatches,
    }
    developer_verification["passed"] = not any(
        (
            developer_verification["missing"],
            developer_verification["unexpected"],
            developer_verification["hash_or_size_mismatches"],
        )
    )
    installer = output / INSTALLER_NAME
    installer_passed = installer.exists() and installer.read_bytes()[:2] == b"MZ"
    if not results or not all(bool(item["passed"]) for item in results):
        raise RuntimeError(json.dumps(results, indent=2))
    if not developer_verification["passed"] or not installer_passed:
        raise RuntimeError(
            json.dumps(
                {
                    "developer_verification": developer_verification,
                    "installer_pe": installer_passed,
                },
                indent=2,
            )
        )
    print(
        json.dumps(
            {
                "status": "ok",
                "archives": results,
                "developer_source_match": developer_verification,
                "installer_pe": installer_passed,
            },
            indent=2,
        )
    )


def finalize_manifests(args: argparse.Namespace) -> None:
    output = args.output.resolve()
    manifest_path = output / "BioIntel-AI-Phase31-to-35-Package-Manifest.json"
    hashes_path = output / "BioIntel-AI-Phase31-to-35-SHA256.txt"
    manifest_path.unlink(missing_ok=True)
    hashes_path.unlink(missing_ok=True)
    artifacts = []
    for path in sorted(item for item in output.iterdir() if item.is_file()):
        artifacts.append(
            {
                "filename": path.name,
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
    required = {
        PRODUCTION_ZIP_NAME,
        INSTALLER_NAME,
        f"{DEVELOPER_PREFIX}-Part1.zip",
    }
    names = {item["filename"] for item in artifacts}
    missing = sorted(required - names)
    if missing:
        raise RuntimeError(f"Cannot finalize; required artifacts are missing: {missing}")
    manifest = {
        "product": "BioIntel AI",
        "phase": PHASE_VERSION,
        "version": "15.6.0",
        "generated_at_utc": utc_now(),
        "distribution_model": {
            "production": "Protected bytecode application with bundled CPython 3.11 runtime",
            "installer": (
                "Native Windows .NET winexe bootstrap; installs the adjacent verified "
                "production ZIP per-user without administrator rights"
            ),
            "developer": "Readable source, tests, reports, docs, build scripts and offline assets",
        },
        "research_boundary": (
            "Biomedical Twin and Scientific Discovery outputs are for research and education only; "
            "they are not clinical diagnoses, treatment recommendations, or externally validated claims."
        ),
        "artifacts": artifacts,
    }
    write_text(manifest_path, json.dumps(manifest, indent=2, sort_keys=True))
    hash_targets = sorted(
        item for item in output.iterdir() if item.is_file() and item != hashes_path
    )
    lines = [f"{sha256(path)} *{path.name}" for path in hash_targets]
    write_text(hashes_path, "\n".join(lines) + "\n")
    print(
        json.dumps(
            {
                "status": "ok",
                "manifest": str(manifest_path),
                "hashes": str(hashes_path),
                "artifact_count": len(hash_targets),
            },
            indent=2,
        )
    )


def parser() -> argparse.ArgumentParser:
    root_default = Path(__file__).resolve().parents[1]
    workspace_default = root_default.parents[2]
    output_default = workspace_default / "deliverables"
    work_default = workspace_default / "work" / "phase31_35_release"
    command = argparse.ArgumentParser(description="Build BioIntel AI Phase 31-35 releases.")
    subparsers = command.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", type=Path, default=root_default)
    common.add_argument("--output", type=Path, default=output_default)
    common.add_argument("--work", type=Path, default=work_default)

    production = subparsers.add_parser("production", parents=[common])
    production.add_argument(
        "--python-home",
        type=Path,
        default=Path(sys.base_prefix),
    )
    production.add_argument(
        "--venv-site",
        type=Path,
        default=Path(sys.prefix) / "Lib" / "site-packages",
    )
    production.set_defaults(function=build_production)

    resume = subparsers.add_parser("resume-production", parents=[common])
    resume.set_defaults(function=resume_production)

    installer = subparsers.add_parser("installer", parents=[common])
    installer.set_defaults(function=build_installer)

    install_test = subparsers.add_parser("test-installer", parents=[common])
    install_test.set_defaults(function=test_install)

    developer = subparsers.add_parser("developer", parents=[common])
    developer.add_argument("--parts", type=int, default=4)
    developer.set_defaults(function=build_developer)

    verify = subparsers.add_parser("verify", parents=[common])
    verify.set_defaults(function=verify_archives)

    manifests = subparsers.add_parser("manifests", parents=[common])
    manifests.set_defaults(function=finalize_manifests)
    return command


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    started = time.perf_counter()
    args.function(args)
    print(f"ELAPSED_SECONDS={time.perf_counter() - started:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
