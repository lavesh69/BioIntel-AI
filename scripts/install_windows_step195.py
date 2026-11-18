from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData' / 'Local')))
USER_DATA = LOCAL / 'BioIntelAI' / 'UserData'
LOCK = USER_DATA / 'runtime' / 'install-step195.lock'
REPORT = USER_DATA / 'reports' / 'step195-install.json'
LOG = USER_DATA / 'runtime_logs' / f"step195-install-{datetime.now():%Y%m%d-%H%M%S}.log"


def write(msg: str = '') -> None:
    print(msg, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open('a', encoding='utf-8', errors='replace') as fh:
        fh.write(msg + '\n')


def run(cmd: list[str], *, check: bool = True) -> int:
    write('RUN: ' + subprocess.list2cmdline(cmd))
    proc = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding='utf-8', errors='replace', env=_env())
    assert proc.stdout is not None
    for line in proc.stdout:
        write(line.rstrip())
    code = proc.wait()
    if check and code:
        raise RuntimeError(f"Command failed ({code}): {subprocess.list2cmdline(cmd)}")
    return code


def _env() -> dict[str, str]:
    env = os.environ.copy()
    short = LOCAL / 'BioIntelAI' / 'Temp'
    short.mkdir(parents=True, exist_ok=True)
    env.update({
        'BIOINTEL_USER_DATA_DIR': str(USER_DATA), 'BIOINTEL_SHORT_TEMP': str(short),
        'TEMP': str(short), 'TMP': str(short), 'PYTHONPATH': str(ROOT / 'src'),
        'PYTHONUTF8': '1', 'PYTHONIOENCODING': 'utf-8', 'PIP_NO_INPUT': '1',
        'PIP_DISABLE_PIP_VERSION_CHECK': '1', 'PIP_NO_CACHE_DIR': '1',
    })
    return env


@contextmanager
def install_lock():
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    if LOCK.exists():
        try:
            payload = json.loads(LOCK.read_text(encoding='utf-8'))
            age = time.time() - float(payload.get('created_epoch', 0))
        except Exception:
            age = 999999
        if age < 7200:
            raise RuntimeError('Another BioIntel AI installation/repair is already running.')
        LOCK.unlink(missing_ok=True)
    LOCK.write_text(json.dumps({'pid': os.getpid(), 'created_epoch': time.time()}, indent=2), encoding='utf-8')
    try:
        yield
    finally:
        LOCK.unlink(missing_ok=True)


def check_root() -> None:
    required = ['app.py', 'requirements.lock', 'scripts/bootstrap.py',
                'scripts/step195_validate_release.py', 'scripts/verify_windows_wheelhouse.py']
    missing = [x for x in required if not (ROOT / x).is_file()]
    if missing:
        raise RuntimeError('Incomplete extraction. Missing: ' + ', '.join(missing))
    for i in range(1, 5):
        if not (ROOT / '.release_parts' / f'step195_part{i}.ok').is_file():
            raise RuntimeError(f'Step 195 Part {i} marker is missing. Extract all four matching ZIPs together.')
    if len(str(ROOT)) > 180:
        raise RuntimeError('Installation path is too long. Extract to a short path such as C:\\BioIntelAI.')
    free = shutil.disk_usage(ROOT).free
    if free < 5 * 1024**3:
        raise RuntimeError(f'At least 5 GB free disk space is required; available={free/1024**3:.2f} GB.')


def verify_before_change() -> None:
    run([sys.executable, 'scripts/step195_validate_release.py', '--root', '.', '--allow-uninstalled', '--deep-hashes'])
    run([sys.executable, 'scripts/verify_dependency_lock.py', '--root', '.'])
    run([sys.executable, 'scripts/verify_windows_wheelhouse.py', '--root', '.'])


def install_with_rollback(force: bool) -> None:
    venv = ROOT / '.venv'
    backup = ROOT / '.venv.step195-backup'
    if backup.exists():
        shutil.rmtree(backup, ignore_errors=True)
    keep_existing = venv.is_dir() and (venv / 'Scripts' / 'python.exe').is_file() and not force
    if keep_existing:
        code = run([str(venv / 'Scripts' / 'python.exe'), '-m', 'pip', 'check'], check=False)
        if code == 0:
            write('Existing environment is healthy; dependency reinstall skipped.')
            return
    if venv.exists():
        write('Preserving current environment for rollback...')
        venv.replace(backup)
    try:
        run([sys.executable, 'scripts/bootstrap.py', '--offline'])
        py = venv / 'Scripts' / 'python.exe'
        if not py.is_file():
            raise RuntimeError('Virtual environment was not created.')
        run([str(py), '-m', 'pip', 'check'])
        run([str(py), 'scripts/step193_self_test.py', '--root', '.', '--output',
             str(USER_DATA / 'reports' / 'step195-post-install-self-test.json'), '--allow-degraded'])
    except Exception:
        shutil.rmtree(venv, ignore_errors=True)
        if backup.exists():
            write('Installation failed; restoring the previous working environment...')
            backup.replace(venv)
        raise
    else:
        shutil.rmtree(backup, ignore_errors=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--force-repair', action='store_true')
    args = ap.parse_args()
    status = {'schema': 'biointel.step195.install.v1', 'started_at': datetime.now(timezone.utc).isoformat(), 'passed': False}
    try:
        USER_DATA.mkdir(parents=True, exist_ok=True)
        with install_lock():
            write('BioIntel AI Step 195 verified installation/repair')
            check_root()
            verify_before_change()
            install_with_rollback(args.force_repair)
            write('Configuring optional free Ollama + SearXNG web AI...')
            free_setup = ROOT / 'scripts' / 'setup_free_web_ai_windows.py'
            if free_setup.is_file() and os.environ.get('BIOINTEL_SKIP_FREE_WEB_AI_SETUP', '').strip().lower() not in {'1', 'true', 'yes'}:
                free_rc = run([sys.executable, str(free_setup), '--model', os.environ.get('BIOINTEL_OLLAMA_MODEL', 'gemma3:1b')], check=False)
                status['free_web_ai_setup_exit_code'] = free_rc
                if free_rc:
                    write('Free Web AI setup reported a warning; the core application installation remains valid.')
            else:
                status['free_web_ai_setup_exit_code'] = None
            (ROOT / '.biointel_step195_installed').write_text(datetime.now(timezone.utc).isoformat()+'\n', encoding='utf-8')
            status['passed'] = True
            status['message'] = 'Installation and self-test completed.'
            return 0
    except Exception as exc:
        status['message'] = str(exc)
        status['traceback'] = traceback.format_exc()
        write('INSTALLATION FAILED: ' + str(exc))
        return 1
    finally:
        status['finished_at'] = datetime.now(timezone.utc).isoformat()
        status['log'] = str(LOG)
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(status, indent=2), encoding='utf-8')


if __name__ == '__main__':
    raise SystemExit(main())
