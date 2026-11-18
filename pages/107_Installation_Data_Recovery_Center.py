from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.production.service_health import health_from_url
from biointel.production.user_data import MANIFEST_NAME, PERSISTENT_DIRECTORIES, build_manifest, validate_backup
from biointel.operations.runtime_control import inspect_local_runtime
from biointel.ui.components import metric_cards, smart_dataframe, smart_json
from biointel.ui.theme import apply_theme, badge, hero, insight_callout, section_title

st.set_page_config(page_title="Installation & Recovery · BioIntel AI", page_icon="🛡️", layout="wide")
apply_theme()
hero(
    "Installation, Data Safety & Recovery Center",
    "Inspect the separated user-data store, validate backups, review rollback points and probe optional production services without exposing credentials.",
    eyebrow="BioIntel AI · Step 196 local installation",
    chips=["Separated UserData", "Desktop shortcut", "SHA-256 manifests", "Runtime controls", "Service probes", "No secret display"],
)

local = os.environ.get("LOCALAPPDATA")
default_data = Path(local) / "BioIntelAI" / "UserData" if local else ROOT
user_data = Path(os.environ.get("BIOINTEL_USER_DATA_DIR", str(default_data))).expanduser()
backup_root = Path.home() / "Documents" / "BioIntel AI Backups"
rows = []
for name in PERSISTENT_DIRECTORIES:
    path = user_data / name
    files = [item for item in path.rglob("*") if item.is_file()] if path.exists() else []
    rows.append({"directory": name, "path": str(path), "exists": path.exists(), "files": len(files), "size_mb": round(sum(item.stat().st_size for item in files) / 1024**2, 2)})
frame = pd.DataFrame(rows)
metric_cards([
    ("User data root", str(user_data), None),
    ("Persistent areas", len(PERSISTENT_DIRECTORIES), None),
    ("Files", int(frame["files"].sum()), None),
    ("Size", f"{frame['size_mb'].sum():.1f} MB", None),
])

storage_tab, backup_tab, runtime_tab, services_tab, guide_tab = st.tabs(["Persistent storage", "Backup validation", "Runtime control", "Production services", "Recovery guide"])
with storage_tab:
    smart_dataframe(frame, height=400, key="persistent_storage_table")
    manifest = build_manifest(user_data, label="live-user-data")
    st.download_button("Download live-data manifest", json.dumps(manifest, indent=2).encode(), "biointel_live_user_data_manifest.json", "application/json")
    insight_callout("Upgrade safety", "Step 96 keeps data, reports, workspaces, exports and projects outside the replaceable application directory. Installer upgrades merge missing seed content and preserve existing user-owned files.", tone="success")

with backup_tab:
    backups = sorted([path for path in backup_root.glob("BioIntel-*") if path.is_dir()], reverse=True) if backup_root.exists() else []
    if not backups:
        st.info(f"No Step 96 backup folders found under {backup_root}.")
    else:
        selected = st.selectbox("Backup", backups, format_func=lambda path: path.name)
        result = validate_backup(selected)
        if result.valid:
            badge(f"● Backup valid · {result.checked_files} files verified", "success")
        else:
            badge("● Backup validation failed", "danger")
        smart_json(result.to_dict(), key="backup_validation")

with runtime_tab:
    runtime = inspect_local_runtime(ROOT, user_data)
    state = str(runtime.get("state", "unknown"))
    tone = "success" if state == "running" else ("warning" if state in {"stale", "different-release"} else "success")
    badge(f"● Local runtime: {state}", tone)
    processes = runtime.get("processes", [])
    if processes:
        smart_dataframe(pd.DataFrame(processes), key="local_runtime_processes")
    else:
        st.caption("No current BioIntel UI, API or worker process is registered.")
    if state == "running":
        st.warning("Stopping the local runtime closes this browser session, API and worker in about two seconds.")
        if st.button("Stop local BioIntel services", type="secondary", key="stop_local_biointel"):
            command = [
                sys.executable,
                str(ROOT / "scripts" / "stop_biointel.py"),
                "--root",
                str(ROOT),
                "--delay-seconds",
                "2",
            ]
            flags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0)) if os.name == "nt" else 0
            subprocess.Popen(
                command,
                cwd=ROOT,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=flags,
            )
            st.success("Stop requested. This local BioIntel session will close shortly.")
    elif state == "different-release":
        st.info(
            "A different extracted release is registered. The current V16 launcher performs the preserved verified automatic handover "
            "when you start it with RUN_BOTH_WINDOWS.bat; this page still does not manually stop another release."
        )

with services_tab:
    st.caption("These are connectivity probes only. Full repository migration requires production configuration and organisation-specific qualification.")
    endpoints = {
        "PostgreSQL": st.text_input("PostgreSQL URL", os.environ.get("DATABASE_URL", "postgresql://127.0.0.1:5432/biointel"), type="password"),
        "Redis": st.text_input("Redis URL", os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0"), type="password"),
        "MinIO/S3 health": st.text_input("Object-storage health URL", os.environ.get("MINIO_HEALTH_URL", "http://127.0.0.1:9000/minio/health/live")),
    }
    if st.button("Probe services"):
        statuses = [health_from_url(name, value) for name, value in endpoints.items()]
        # Hide credentials/query strings in display.
        display = []
        for item in statuses:
            row = item.to_dict()
            endpoint = str(row["endpoint"])
            if "@" in endpoint:
                endpoint = endpoint.split("@", 1)[-1]
            row["endpoint"] = endpoint
            display.append(row)
        smart_dataframe(pd.DataFrame(display), key="service_health_table")

with guide_tab:
    st.markdown("""
### Current release recovery flow

1. Keep the original five matching ZIP parts together and extract them into one new empty folder.
2. Run `INSTALL_WINDOWS.bat`; it verifies the source manifest, release markers, CPython 3.11.x x64 (3.11.9 preferred), dependency lock and offline wheelhouse before it changes the environment.
3. Start the workspace with `RUN_BOTH_WINDOWS.bat` or the refreshed **BioIntel AI** Desktop shortcut.
4. Use this page to inspect persistent user data, backups and the local runtime before a repair.
5. Use repair tools only when the installer report identifies a specific issue; generated user data remains outside the replaceable application folder.
""")

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
