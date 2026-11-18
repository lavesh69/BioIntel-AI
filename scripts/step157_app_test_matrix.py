from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import tempfile
import shutil
import signal
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _run_page(root: Path, page: Path, timeout: int) -> dict[str, Any]:
    relative = page.relative_to(root).as_posix()
    code = (
        "from streamlit.testing.v1 import AppTest;"
        f"app=AppTest.from_file({str(page)!r});"
        f"app.run(timeout={float(max(5, timeout - 5))!r});"
        "errors=list(app.exception);"
        "assert not errors, [str(item.value) for item in errors];"
        "print('BIOINTEL_APPTEST_OK')"
    )
    isolated_user_data = Path(tempfile.mkdtemp(prefix="biointel_step157_apptest_"))
    env = {
        **os.environ,
        "PYTHONPATH": str(root / "src"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "BIOINTEL_APPTEST": "1",
        "BIOINTEL_USER_DATA_DIR": str(isolated_user_data),
        "LOCALAPPDATA": str(isolated_user_data / "LocalAppData"),
    }
    started = time.monotonic()
    process = None
    try:
        popen_kwargs = {
            "cwd": root,
            "env": env,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
        }
        if os.name == "nt":
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_kwargs["start_new_session"] = True
        process = subprocess.Popen([sys.executable, "-c", code], **popen_kwargs)
        stdout, stderr = process.communicate(timeout=timeout)
        duration = time.monotonic() - started
        text = (stdout + stderr)[-5000:]
        return {
            "page": relative,
            "passed": process.returncode == 0 and "BIOINTEL_APPTEST_OK" in stdout,
            "return_code": process.returncode,
            "duration_seconds": round(duration, 3),
            "detail": text,
            "timed_out": False,
        }
    except subprocess.TimeoutExpired:
        if process is not None:
            try:
                if os.name == "nt":
                    process.kill()
                else:
                    os.killpg(process.pid, signal.SIGKILL)
            except Exception:
                process.kill()
            try:
                stdout, stderr = process.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                try:
                    if process.stdout:
                        process.stdout.close()
                    if process.stderr:
                        process.stderr.close()
                except Exception:
                    pass
                stdout = stderr = ""
        else:
            stdout = stderr = ""
        return {
            "page": relative,
            "passed": False,
            "return_code": None,
            "duration_seconds": round(time.monotonic() - started, 3),
            "detail": (stdout + stderr)[-2000:] + "\nTIMEOUT",
            "timed_out": True,
        }
    except Exception as exc:
        return {
            "page": relative,
            "passed": False,
            "return_code": None,
            "duration_seconds": round(time.monotonic() - started, 3),
            "detail": f"{type(exc).__name__}: {exc}",
            "timed_out": False,
        }
    finally:
        shutil.rmtree(isolated_user_data, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run every BioIntel Streamlit screen through isolated AppTest workers.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--timeout", type=int, default=40)
    parser.add_argument("--output", default="reports/step157_all_pages_app_test.json")
    parser.add_argument("--include-app", action="store_true")
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    root = Path(args.root).expanduser().resolve()
    pages = sorted((root / "pages").glob("*.py"), key=lambda path: path.name.casefold())
    if args.include_app and (root / "app.py").is_file():
        pages.insert(0, root / "app.py")
    start = max(0, int(args.start))
    pages = pages[start : start + int(args.limit)] if int(args.limit) > 0 else pages[start:]
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 16))) as executor:
        future_map = {executor.submit(_run_page, root, page, max(10, args.timeout)): page for page in pages}
        for future in as_completed(future_map):
            result = future.result()
            results.append(result)
            marker = "PASS" if result["passed"] else "FAIL"
            print(f"[{marker}] {result['page']} ({result['duration_seconds']}s)", flush=True)
    results.sort(key=lambda item: item["page"].casefold())
    failures = [item for item in results if not item["passed"]]
    payload = {
        "schema": "biointel.step157.all-pages-app-test.v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "root": str(root),
        "pages_collected": len(pages),
        "passed": len(results) - len(failures),
        "failed": len(failures),
        "timeouts": sum(bool(item["timed_out"]) for item in results),
        "workers": max(1, min(args.workers, 16)),
        "timeout_seconds_per_page": max(10, args.timeout),
        "start_index": start,
        "limit": int(args.limit),
        "results": results,
    }
    output = Path(args.output)
    if not output.is_absolute():
        output = root / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: payload[key] for key in ("pages_collected", "passed", "failed", "timeouts")}, indent=2))
    print(f"REPORT_PATH={output}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
