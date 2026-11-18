from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def _required_paths(root: Path, lock_name: str) -> tuple[Path, ...]:
    return (
        root / lock_name,
        root / "scripts" / "verify_dependency_lock.py",
        root / "scripts" / "dev_doctor.py",
        root / "scripts" / "verify_windows_runtime_compatibility_step206.py",
        root / "requirements-windows-cp311-offline.lock",
        root / "app.py",
    )


def _check_package(root: Path, lock_name: str) -> None:
    missing = [path for path in _required_paths(root, lock_name) if not path.is_file()]
    if missing:
        joined = "\n".join(f"  - {path}" for path in missing)
        raise RuntimeError(
            "BioIntel AI package is incomplete. Required files are missing:\n"
            f"{joined}\n\n"
            "Extract all five matching Step220 ZIP parts into the same new folder and run INSTALL_WINDOWS.bat "
            "in the same folder. Do not install from a partially extracted archive."
        )


def _run(command: list[str], *, cwd: Path | None = None) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def _offline_available(root: Path) -> bool:
    return all(
        path.is_file()
        for path in (
            root / "requirements-windows-cp311-offline.lock",
            root / "wheelhouse" / "windows-cp311-x64" / "MANIFEST_SHA256.txt",
            root / "scripts" / "verify_windows_wheelhouse.py",
        )
    )


def _install_offline(root: Path, python: Path) -> None:
    wheelhouse = root / "wheelhouse" / "windows-cp311-x64"
    lock = root / "requirements-windows-cp311-offline.lock"
    _run(
        [
            str(python),
            str(root / "scripts" / "verify_windows_wheelhouse.py"),
            "--root",
            str(root),
        ],
        cwd=root,
    )
    common = ["--no-index", "--find-links", str(wheelhouse), "--only-binary=:all:"]
    _run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            *common,
            "--upgrade",
            "pip==26.1.2",
            "setuptools==80.9.0",
            "wheel==0.47.0",
        ]
    )
    _run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            *common,
            "--require-hashes",
            "-r",
            str(lock),
        ]
    )


def _install_online(root: Path, python: Path, lock_path: Path) -> None:
    _run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--upgrade",
            "pip==26.1.2",
            "setuptools==80.9.0",
            "wheel==0.47.0",
        ]
    )
    command = [str(python), "-m", "pip", "install", "--prefer-binary"]
    if lock_path.name == "requirements-windows-cp311-offline.lock":
        command.extend(("--require-hashes", "--only-binary=:all:"))
    _run([*command, "-r", str(lock_path)])


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create and verify a reproducible BioIntel AI virtual environment."
    )
    parser.add_argument("--venv", default=".venv")
    parser.add_argument("--dev", action="store_true")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--offline", action="store_true", help="Require the bundled Windows wheelhouse."
    )
    mode.add_argument(
        "--online", action="store_true", help="Ignore the wheelhouse and use the package index."
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    lock_name = "requirements-ci.txt" if args.dev else "requirements.lock"

    try:
        _check_package(root, lock_name)
        venv = root / args.venv
        python = venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        if venv.exists() and not python.is_file():
            import shutil
            print(f"Removing incomplete virtual environment: {venv}")
            shutil.rmtree(venv)
        if not venv.exists():
            print(f"Creating virtual environment: {venv}")
            _run([sys.executable, "-m", "venv", str(venv)])
        else:
            print(f"Using existing virtual environment: {venv}")

        if not python.is_file():
            raise RuntimeError(f"Virtual-environment Python was not created: {python}")

        offline = _offline_available(root) and not args.online and not args.dev
        if args.offline and not offline:
            raise RuntimeError("The complete offline wheelhouse is missing or incomplete.")
        if offline:
            print(
                "Installing from the bundled, SHA-256-verified Windows wheelhouse (no internet required)."
            )
            _install_offline(root, python)
        else:
            print("Installing from the configured Python package index.")
            online_lock = (
                root / "requirements-windows-cp311-offline.lock"
                if sys.platform == "win32" and not args.dev
                else root / lock_name
            )
            _install_online(root, python, online_lock)

        _run(
            [
                str(python),
                str(root / "scripts" / "verify_dependency_lock.py"),
                "--root",
                str(root),
            ],
            cwd=root,
        )
        _run([str(python), str(root / "scripts" / "dev_doctor.py")], cwd=root)
        if not args.dev:
            _run(
                [
                    str(python),
                    str(root / "scripts" / "verify_windows_runtime_compatibility_step206.py"),
                    "--root",
                    str(root),
                    "--strict-python",
                ],
                cwd=root,
            )
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        print("\nBioIntel AI installation could not be completed.", file=sys.stderr)
        print(str(exc), file=sys.stderr)
        return 1

    print("\nBioIntel AI virtual environment is ready and verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
