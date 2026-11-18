from __future__ import annotations

from biointel.runtime_paths import runtime_database_path

import hashlib
import json
import sqlite3
from biointel.database.core import managed_connect
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import streamlit as st

from biointel.expansion.catalog import ExpansionModule
from biointel.expansion.tool_adapters import tool_status
from biointel.ui.components import smart_dataframe
from biointel.ui.theme import insight_callout, section_title


def _lims_db(root: Path) -> Path:
    path = runtime_database_path(root, "step103_lims.sqlite3")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _init_lims(path: Path) -> None:
    with managed_connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS samples (
                sample_id TEXT PRIMARY KEY,
                parent_id TEXT,
                status TEXT NOT NULL,
                location TEXT,
                freeze_thaw INTEGER NOT NULL DEFAULT 0,
                days_to_expiry INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit_log (
                audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp_utc TEXT NOT NULL,
                action TEXT NOT NULL,
                sample_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                payload_sha256 TEXT NOT NULL
            );
            """
        )


def _upsert_lims(path: Path, record: dict[str, Any]) -> None:
    now = datetime.now(timezone.utc).isoformat()
    payload = json.dumps(record, sort_keys=True, default=str)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    with managed_connect(path) as connection:
        connection.execute(
            """
            INSERT INTO samples(sample_id,parent_id,status,location,freeze_thaw,days_to_expiry,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?)
            ON CONFLICT(sample_id) DO UPDATE SET
              parent_id=excluded.parent_id,
              status=excluded.status,
              location=excluded.location,
              freeze_thaw=excluded.freeze_thaw,
              days_to_expiry=excluded.days_to_expiry,
              updated_at=excluded.updated_at
            """,
            (
                record["sample_id"], record.get("parent_id", ""), record["status"],
                record.get("location", ""), int(record.get("freeze_thaw", 0)),
                int(record.get("days_to_expiry", 0)), now, now,
            ),
        )
        connection.execute(
            "INSERT INTO audit_log(timestamp_utc,action,sample_id,payload_json,payload_sha256) VALUES(?,?,?,?,?)",
            (now, "UPSERT", record["sample_id"], payload, digest),
        )


def _read_sql(path: Path, table: str) -> pd.DataFrame:
    with managed_connect(path) as connection:
        return pd.read_sql_query(f"SELECT * FROM {table} ORDER BY rowid DESC", connection)


def _render_lims_utility(root: Path, data: pd.DataFrame) -> None:
    section_title("Local LIMS registry", "🧾")
    st.caption("This local SQLite registry provides persistent sample CRUD and an append-only checksum audit log. It is not a validated electronic-signature system.")
    path = _lims_db(root)
    _init_lims(path)
    with st.form("step103_lims_entry"):
        c1, c2, c3 = st.columns(3)
        sample_id = c1.text_input("Sample ID")
        parent_id = c2.text_input("Parent ID")
        status = c3.selectbox("Status", ["Received", "Processing", "Stored", "Consumed", "Quarantined"])
        c4, c5, c6 = st.columns(3)
        location = c4.text_input("Storage location")
        freeze_thaw = c5.number_input("Freeze–thaw count", min_value=0, value=0, step=1)
        days_to_expiry = c6.number_input("Days to expiry", min_value=-3650, max_value=3650, value=180, step=1)
        submitted = st.form_submit_button("Save sample record", type="primary")
        if submitted:
            if not sample_id.strip():
                st.error("Sample ID is required.")
            else:
                _upsert_lims(path, {
                    "sample_id": sample_id.strip(), "parent_id": parent_id.strip(), "status": status,
                    "location": location.strip(), "freeze_thaw": int(freeze_thaw),
                    "days_to_expiry": int(days_to_expiry),
                })
                st.success("Sample saved with an audit-log entry.")
    if st.button("Import current analysis table into local LIMS", key="step103_lims_import"):
        imported = 0
        for row in data.to_dict(orient="records"):
            if str(row.get("sample_id", "")).strip():
                _upsert_lims(path, row)
                imported += 1
        st.success(f"Imported or updated {imported} sample record(s).")
    samples = _read_sql(path, "samples")
    audit = _read_sql(path, "audit_log")
    smart_dataframe(samples, height=360, key="step103_lims_samples")
    st.download_button("Download local LIMS registry", samples.to_csv(index=False).encode("utf-8"), "step103_lims_registry.csv", "text/csv", width="stretch")
    with st.expander("Checksum audit log"):
        smart_dataframe(audit, height=300, key="step103_lims_audit")


def _render_randomisation(data: pd.DataFrame) -> None:
    section_title("Reproducible randomisation schedule", "🎲")
    if data.empty:
        st.info("Load a design table to generate a schedule.")
        return
    designs = data["design"].astype(str).tolist()
    selected = st.selectbox("Design scenario", designs, key="step103_random_design")
    row = data.loc[data["design"].astype(str) == selected].iloc[0]
    total = int(row.get("total_sample_size", row.get("groups", 2) * 20))
    groups = max(2, int(row.get("groups", 2)))
    block_size = st.selectbox("Block size", [groups, groups * 2, groups * 4], index=1, key="step103_block_size")
    seed = st.number_input("Random seed", min_value=1, max_value=2_147_483_647, value=1032026, step=1)
    rng = np.random.default_rng(int(seed))
    labels = [f"Group {i + 1}" for i in range(groups)]
    assignments: list[str] = []
    while len(assignments) < total:
        block = (labels * max(1, block_size // groups))[:block_size]
        rng.shuffle(block)
        assignments.extend(block)
    schedule = pd.DataFrame({
        "participant_sequence": np.arange(1, total + 1),
        "allocation": assignments[:total],
        "block": (np.arange(total) // block_size) + 1,
        "seed": int(seed),
    })
    smart_dataframe(schedule, height=360, key="step103_randomisation")
    st.download_button("Download randomisation CSV", schedule.to_csv(index=False).encode("utf-8"), "randomisation_schedule.csv", "text/csv", width="stretch")


def render_module_utility(module: ExpansionModule, data: pd.DataFrame, root: Path) -> None:
    section_title("Advanced utilities and readiness", "🧰")
    readiness = tool_status(module.key)
    if readiness.empty:
        st.info("This module's advanced calculations are implemented with bundled Python libraries and transparent local methods. No external executable is required for the current table workflow.")
    else:
        smart_dataframe(readiness, height=280, key=f"{module.key}_utility_tool_status")
        installed = int(readiness["installed"].sum())
        st.caption(f"Detected {installed} of {len(readiness)} optional specialist executable(s). They are never run without an explicit user action.")

    if module.key == "lims_eln_chain":
        _render_lims_utility(root, data)
    elif module.key == "biostatistics_design":
        _render_randomisation(data)
    elif module.key == "pharmacogenomics":
        insight_callout(
            "Clinical-action lock",
            "The workspace can organise and flag evidence, but it deliberately does not generate dose or treatment instructions. Curated guideline integration and clinical governance must be supplied separately.",
            tone="warning",
        )
    elif module.key == "docking_dynamics":
        insight_callout(
            "Docking execution boundary",
            "Imported SDF/MOL files receive transparent molecular-descriptor proxies only. A real docking score requires an explicitly configured engine such as AutoDock Vina and validated receptor/ligand preparation.",
            tone="warning",
        )
    else:
        st.markdown(
            "Use this panel to verify optional local tools before attempting specialist workflows. "
            "The built-in analysis remains available when those tools are absent, but proxy or fallback calculations stay clearly labelled."
        )
