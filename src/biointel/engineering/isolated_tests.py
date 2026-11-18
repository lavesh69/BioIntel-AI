from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Iterable


def _run_one(
    root: Path,
    test_file: str,
    *,
    timeout_seconds: int,
) -> dict[str, object]:
    args = ["-q", test_file]
    wrapper = (
        "import os,pytest,sys; "
        f"code=pytest.main({args!r}); "
        "sys.stdout.flush(); sys.stderr.flush(); os._exit(int(code))"
    )
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(root / "src")
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment.setdefault("OMP_NUM_THREADS", "1")
    environment.setdefault("OPENBLAS_NUM_THREADS", "1")
    environment.setdefault("MKL_NUM_THREADS", "1")
    environment.setdefault("NUMEXPR_NUM_THREADS", "1")
    started = time.perf_counter()
    with tempfile.TemporaryFile(mode="w+") as stdout_file, tempfile.TemporaryFile(
        mode="w+"
    ) as stderr_file:
        process = subprocess.Popen(
            [sys.executable, "-c", wrapper],
            cwd=root,
            env=environment,
            text=True,
            stdout=stdout_file,
            stderr=stderr_file,
            start_new_session=True,
        )
        timed_out = False
        try:
            returncode = process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            returncode = process.wait()
        finally:
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
        stdout_file.seek(0)
        stderr_file.seek(0)
        stdout = stdout_file.read()
        stderr = stderr_file.read()
    return {
        "file": test_file,
        "passed": returncode == 0 and not timed_out,
        "returncode": int(returncode),
        "timed_out": timed_out,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "stdout_tail": stdout[-4000:],
        "stderr_tail": stderr[-4000:],
    }


def run_test_files_isolated(
    root: str | Path,
    test_files: Iterable[str | Path],
    *,
    timeout_seconds: int = 300,
    max_workers: int = 1,
) -> dict[str, object]:
    """Run each pytest file in a process group with a hard timeout.

    This prevents non-daemon UI/database threads in one historical test file from
    holding the complete qualification process open. Results are deterministic and
    file-scoped, while optional bounded parallelism keeps large repositories fast.
    """

    base = Path(root).resolve()
    files = sorted({Path(item).as_posix() for item in test_files})
    workers = max(1, min(int(max_workers), 8, len(files) or 1))
    results: list[dict[str, object]] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                _run_one,
                base,
                test_file,
                timeout_seconds=max(1, int(timeout_seconds)),
            ): test_file
            for test_file in files
        }
        for future in as_completed(futures):
            results.append(future.result())
    results.sort(key=lambda item: str(item["file"]))
    return {
        "file_count": len(results),
        "passed_files": sum(bool(item["passed"]) for item in results),
        "failed_files": sum(not bool(item["passed"]) for item in results),
        "timed_out_files": sum(bool(item["timed_out"]) for item in results),
        "elapsed_seconds_total": round(
            sum(float(item["elapsed_seconds"]) for item in results), 3
        ),
        "results": results,
    }
