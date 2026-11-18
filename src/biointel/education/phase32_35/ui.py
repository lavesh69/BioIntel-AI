from __future__ import annotations

import hashlib
import json
from pathlib import Path

import streamlit as st

from ..paths import education_paths
from .base import ResearchPlatformError
from .sync import SYNC_SCOPES, SyncEngine


@st.cache_resource
def _sync_engine(root_text: str) -> SyncEngine:
    root = Path(root_text)
    database, media = education_paths(root)
    return SyncEngine(database, media)


def render_secure_sync(root: str | Path) -> None:
    service = _sync_engine(str(Path(root).resolve()))
    st.title("BioIntel Secure Sync")
    st.caption(
        "Optional, local-first continuity. BioIntel remains fully usable without a remote endpoint."
    )
    tenant_id = st.text_input("Institution or tenant ID", value="local-institution")
    status = service.status(tenant_id)
    first, second, third = st.columns(3)
    first.metric("Devices", len(status["devices"]))
    second.metric("Pending changes", status["pending_changes"])
    third.metric("Open conflicts", status["open_conflicts"])

    with st.expander("Register this device"):
        with st.form("phase32_device_registration"):
            owner_id = st.text_input("Owner ID", value="local-user")
            device_name = st.text_input("Device name", value="Windows workstation")
            scopes = st.multiselect(
                "Allowed sync categories",
                sorted(SYNC_SCOPES),
                default=["preferences", "notes", "research_projects"],
            )
            submitted = st.form_submit_button("Request device registration")
        if submitted:
            try:
                row = service.register_device(
                    tenant_id,
                    owner_id,
                    device_name=device_name,
                    device_type="desktop",
                    operating_system="Windows",
                    permissions=scopes,
                )
                st.success(f"Registration saved as {row['state']}. Administrator approval is required.")
            except ResearchPlatformError as exc:
                st.error(str(exc))

    with st.expander("Queue an offline note change"):
        trusted = [row for row in status["devices"] if row["state"] == "trusted"]
        if not trusted:
            st.info("Approve a device before it can enqueue synchronized changes.")
        else:
            device_id = st.selectbox(
                "Trusted device",
                [row["device_id"] for row in trusted],
            )
            note_id = st.text_input("Note ID", value="note-001")
            body = st.text_area("Note text")
            if st.button("Queue local change", width="stretch"):
                try:
                    row = service.append_change(
                        tenant_id,
                        device_id,
                        trusted[0]["owner_id"],
                        entity_type="notes",
                        entity_id=note_id,
                        operation="UPDATE",
                        payload={"body": body},
                        idempotency_key=(
                            f"ui:{device_id}:{note_id}:"
                            f"{hashlib.sha256(body.encode('utf-8')).hexdigest()}"
                        ),
                    )
                    st.success(f"Queued durable journal entry {row['change_id']}.")
                except ResearchPlatformError as exc:
                    st.error(str(exc))

    st.subheader("Device registry")
    st.dataframe(status["devices"], width="stretch", hide_index=True)
    st.subheader("Encryption boundary")
    st.json(status["encryption_boundary"])
    st.download_button(
        "Export redacted diagnostics",
        data=json.dumps(service.diagnostic_bundle(tenant_id), indent=2),
        file_name="biointel-sync-diagnostics.json",
        mime="application/json",
        width="stretch",
    )
