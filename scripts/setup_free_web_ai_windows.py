from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
LOCAL = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
USER_DATA = LOCAL / "BioIntelAI" / "UserData"
REPORT = USER_DATA / "reports" / "step196-free-web-ai-setup.json"
LOCK = USER_DATA / "runtime" / "free-web-ai-setup.lock"
DEFAULT_MODEL = os.getenv("BIOINTEL_OLLAMA_MODEL", "gemma3:1b").strip() or "gemma3:1b"


class SetupAlreadyRunning(RuntimeError):
    pass


class FileLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.handle: BinaryIO | None = None

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+b")
        self.handle.seek(0, os.SEEK_END)
        if self.handle.tell() == 0:
            self.handle.write(b"0")
            self.handle.flush()
        self.handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.handle.close()
            self.handle = None
            raise SetupAlreadyRunning("Ollama/model setup is already continuing in the background.") from exc
        self.handle.seek(0)
        self.handle.truncate(0)
        self.handle.write(json.dumps({"pid": os.getpid(), "started": time.time()}).encode("utf-8"))
        self.handle.flush()

    def release(self) -> None:
        if self.handle is None:
            return
        try:
            self.handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        self.handle.close()
        self.handle = None
        try:
            self.path.unlink(missing_ok=True)
        except OSError:
            pass


@contextmanager
def setup_lock():
    lock = FileLock(LOCK)
    lock.acquire()
    try:
        yield
    finally:
        lock.release()


def _write_report(payload: dict[str, object]) -> None:
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    temp = REPORT.with_suffix(REPORT.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    temp.replace(REPORT)


def _ollama_candidates() -> list[Path]:
    rows: list[Path] = []
    found = shutil.which("ollama")
    if found:
        rows.append(Path(found))
    rows.extend(
        [
            LOCAL / "Programs" / "Ollama" / "ollama.exe",
            Path.home() / "AppData" / "Local" / "Programs" / "Ollama" / "ollama.exe",
            Path(os.environ.get("ProgramFiles", r"C:\\Program Files")) / "Ollama" / "ollama.exe",
        ]
    )
    unique: list[Path] = []
    seen: set[str] = set()
    for path in rows:
        key = str(path).lower()
        if key not in seen:
            unique.append(path)
            seen.add(key)
    return unique


def find_ollama() -> Path | None:
    return next((path for path in _ollama_candidates() if path.is_file()), None)


def install_ollama_with_winget(timeout_seconds: int) -> bool:
    winget = shutil.which("winget")
    if not winget:
        return False
    command = [
        winget,
        "install",
        "--id",
        "Ollama.Ollama",
        "-e",
        "--scope",
        "user",
        "--silent",
        "--disable-interactivity",
        "--accept-package-agreements",
        "--accept-source-agreements",
    ]
    try:
        return subprocess.run(command, check=False, timeout=timeout_seconds).returncode == 0
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            "Ollama installation exceeded the safe timeout. Core BioIntel remains installed; retry from Provider Integration Center."
        )


def api_available() -> bool:
    try:
        request = Request("http://127.0.0.1:11434/api/tags", headers={"Accept": "application/json"})
        with urlopen(request, timeout=3) as response:  # nosec B310 - fixed loopback URL
            return response.status == 200
    except Exception:
        return False


def start_ollama(executable: Path) -> None:
    if api_available():
        return
    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    subprocess.Popen(
        [str(executable), "serve"],
        cwd=str(executable.parent),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
        close_fds=True,
    )
    for _ in range(45):
        if api_available():
            return
        time.sleep(1)
    raise RuntimeError("Ollama is installed, but its local API did not start on port 11434.")


def model_names(executable: Path) -> list[str]:
    result = subprocess.run(
        [str(executable), "list"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    names: list[str] = []
    for line in result.stdout.splitlines()[1:]:
        name = line.split(maxsplit=1)[0].strip() if line.strip() else ""
        if name:
            names.append(name)
    return names


def ensure_model(executable: Path, model: str, timeout_seconds: int) -> None:
    names = model_names(executable)
    if model in names or any(name.split(":", 1)[0] == model.split(":", 1)[0] for name in names):
        return
    print(f"Downloading free local AI model {model}. This runs independently from core installation...", flush=True)
    try:
        code = subprocess.run([str(executable), "pull", model], check=False, timeout=timeout_seconds).returncode
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"Ollama model download timed out after {timeout_seconds} seconds: {model}. Retry later from Provider Integration Center."
        ) from exc
    if code:
        raise RuntimeError(f"Ollama model download failed with exit code {code}: {model}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--no-install", action="store_true")
    parser.add_argument("--no-pull", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--background-worker", action="store_true")
    parser.add_argument("--install-timeout", type=int, default=1200)
    parser.add_argument("--pull-timeout", type=int, default=7200)
    args = parser.parse_args()
    payload: dict[str, object] = {
        "schema": "biointel.step196.free-web-ai-setup.v2",
        "started_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "platform": sys.platform,
        "model": args.model,
        "background_worker": args.background_worker,
        "passed": False,
        "ollama_installed": False,
        "ollama_api": False,
        "model_ready": False,
        "searxng_mode": "automatic public-instance discovery with official-provider fallback",
    }
    try:
        with setup_lock():
            if os.name != "nt":
                raise RuntimeError("Automatic Ollama installation is supported only on Windows.")
            executable = find_ollama()
            if executable is None and not args.no_install:
                print("Ollama not found. Installing verified user-scope package through winget...", flush=True)
                install_ollama_with_winget(args.install_timeout)
                executable = find_ollama()
            if executable is None:
                raise RuntimeError(
                    "Ollama is not installed. Core BioIntel is usable; install Ollama later from Provider Integration Center."
                )
            payload["ollama_executable"] = str(executable)
            payload["ollama_installed"] = True
            start_ollama(executable)
            payload["ollama_api"] = api_available()
            if not args.no_pull:
                ensure_model(executable, args.model, args.pull_timeout)
            names = model_names(executable)
            payload["available_models"] = names
            payload["model_ready"] = args.model in names or any(
                name.split(":", 1)[0] == args.model.split(":", 1)[0] for name in names
            )
            payload["passed"] = bool(payload["ollama_api"] and (payload["model_ready"] or args.no_pull))
            payload["message"] = (
                "Free Web AI is ready. SearXNG auto-discovers a healthy HTTPS instance; official scientific providers remain available as fallback."
            )
            return 0 if payload["passed"] else (1 if args.strict else 0)
    except SetupAlreadyRunning as exc:
        payload["setup_in_progress"] = True
        payload["message"] = str(exc)
        print(str(exc), flush=True)
        return 0
    except Exception as exc:
        payload["message"] = str(exc)
        print("FREE WEB AI SETUP WARNING: " + str(exc), flush=True)
        print("Core BioIntel installation remains usable; retry later in Provider Integration Center.", flush=True)
        return 1 if args.strict else 0
    finally:
        payload["finished_at_utc"] = datetime.now(UTC).isoformat(timespec="seconds")
        _write_report(payload)
        print(f"Free Web AI setup report: {REPORT}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
