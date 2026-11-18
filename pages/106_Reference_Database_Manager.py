from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.jobs.local_queue import LocalJobQueue
from biointel.reference_assets.manager import AssetRecord, download_asset, import_local_asset, safe_extract_archive
from biointel.step101.reference_lifecycle import ReferenceLifecycleManager, ReleaseRecord
from biointel.ui.components import metric_cards, smart_dataframe, smart_json
from biointel.ui.phase108_visuals import render_phase108_visual_suite  # noqa: E402
from biointel.ui.theme import apply_theme, hero, insight_callout, section_title
from biointel.ui.workflow import render_upload_preflight

st.set_page_config(page_title="Reference Database Lifecycle · BioIntel AI", page_icon="🗄️", layout="wide")
apply_theme()

# STEP116_MODULE_EXPERIENCE_2_TO_9
from biointel.ui.module_experience_2_9 import render_module_experience as _render_step116_module_experience
_render_step116_module_experience("reference_manager", key_prefix="step116_106_Reference_Database_Manager_reference_manager_1", expanded=False)
hero(
    "Full Reference Database Lifecycle",
    "Register releases, resume verified downloads, preserve licences, create rollback snapshots, run compatibility checks, build indexes and control local storage.",
    eyebrow="BioIntel AI 10.1 · Reference Governance",
    chips=["Releases", "Resume", "SHA-256", "Compatibility", "Indexing", "Rollback", "Storage quota"],
)

local = os.environ.get("LOCALAPPDATA")
default_root = Path(os.environ.get("BIOINTEL_REFERENCE_ASSETS_DIR", str(Path(local) / "BioIntelAI" / "ReferenceAssets" if local else Path.home() / ".biointel" / "reference-assets")))
asset_root = Path(st.text_input("Reference asset root", str(default_root))).expanduser().resolve()
manager = ReferenceLifecycleManager(asset_root)
registry = manager.registry
queue = LocalJobQueue(ROOT / "reports" / "jobs.sqlite3")
assets = registry.list_assets()
storage = manager.storage_summary()
metric_cards(
    [
        ("Registered assets", len(assets), None),
        ("Provider verified", sum(row.get("status") == "verified" for row in assets), None),
        ("Known releases", len(manager.releases()), None),
        ("Snapshots", len(manager.snapshots()), "Rollback points"),
        ("Storage", f"{storage['used_bytes'] / 1024**3:.2f} GB", f"{storage['files']:,} files"),
    ]
)

catalog_tab, release_tab, install_tab, lifecycle_tab, compatibility_tab, storage_tab, history_tab = st.tabs(
    ["Catalog", "Release registry", "Download/import", "Verify & rollback", "Compatibility & indexing", "Storage", "Audit history"]
)

with catalog_tab:
    catalog_path = ROOT / "config" / "reference_assets_manifest.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8")) if catalog_path.is_file() else {"templates": [], "policy": {}}
    templates = pd.DataFrame(catalog.get("templates", []))
    if templates.empty:
        st.info("No curated templates are registered.")
    else:
        smart_dataframe(templates, height=430, key="step101_reference_templates")
    smart_json(catalog.get("policy", {}), title="Reference installation policy")
    insight_callout(
        "Scientific boundary",
        "A valid file hash proves local integrity, not biological suitability. Organism, genome build, release, indexing method and intended analysis must be recorded per project.",
        tone="info",
    )

with release_tab:
    section_title("Register provider release", "🏷️")
    with st.form("step101_register_release"):
        cols = st.columns(3)
        release_asset = cols[0].text_input("Asset ID", "custom-reference")
        release_version = cols[1].text_input("Version/release", "2026-01")
        release_provider = cols[2].text_input("Provider", "Official provider")
        release_url = st.text_input("Direct HTTPS download URL")
        release_sha = st.text_input("Provider SHA-256")
        release_license = st.text_input("Licence", "Review required")
        release_date = st.date_input("Release date")
        compatibility_json = st.text_area("Compatibility JSON", value=json.dumps({"genome_build": "GRCh38"}, indent=2), height=120)
        register = st.form_submit_button("Register release", type="primary", width="stretch")
    if register:
        try:
            compatibility = json.loads(compatibility_json or "{}")
            manager.register_release(
                ReleaseRecord(
                    asset_id=release_asset,
                    version=release_version,
                    provider=release_provider,
                    download_url=release_url,
                    sha256=release_sha,
                    license_name=release_license,
                    release_date=str(release_date),
                    compatibility=compatibility,
                )
            )
        except Exception as exc:
            st.error(f"Release registration failed: {exc}")
        else:
            st.success("Reference release registered.")
            st.rerun()
    releases = pd.DataFrame(manager.releases())
    if not releases.empty:
        smart_dataframe(releases, height=430, key="step101_reference_releases")

with install_tab:
    mode = st.radio("Source", ["Provider download", "Local file import"], horizontal=True)
    if mode == "Provider download":
        with st.form("step101_download_reference"):
            cols = st.columns(2)
            asset_id = cols[0].text_input("Asset ID", "custom-reference", key="dl_asset")
            provider = cols[1].text_input("Provider", "Official provider", key="dl_provider")
            version = cols[0].text_input("Release/version", "unversioned", key="dl_version")
            license_name = cols[1].text_input("Licence", "Review required", key="dl_license")
            url = st.text_input("Direct HTTPS URL", key="dl_url")
            expected = st.text_input("Expected SHA-256", key="dl_sha")
            accepted = st.checkbox("I reviewed and accept the provider licence/terms")
            extract = st.checkbox("Safely extract ZIP/TAR after verification", value=True)
            download = st.form_submit_button("Download, verify and register", type="primary", width="stretch")
        if download:
            if not accepted:
                st.error("Licence acknowledgement is required.")
            else:
                filename = url.rsplit("/", 1)[-1].split("?", 1)[0] or f"{asset_id}.bin"
                target = asset_root / "downloads" / filename
                progress = st.progress(0.0, text="Preparing download…")

                def update(done: int, total: int | None) -> None:
                    if total:
                        progress.progress(min(done / total, 1.0), text=f"{done / 1024**2:.1f} / {total / 1024**2:.1f} MB")

                try:
                    result = download_asset(url, target, expected_sha256=expected, resume=True, progress=update)
                    installed = target
                    if extract:
                        installed = asset_root / "installed" / asset_id / version
                        safe_extract_archive(target, installed)
                    record = AssetRecord(
                        asset_id=asset_id.strip(),
                        provider=provider.strip(),
                        version=version.strip(),
                        status="verified" if expected.strip() else "locally_hashed",
                        source_url=url.strip(),
                        local_path=str(installed),
                        expected_sha256=expected.strip(),
                        observed_sha256=str(result["sha256"]),
                        size_bytes=int(result["size_bytes"]),
                        license_name=license_name.strip(),
                        license_accepted=True,
                        installed_at_utc=datetime.now(timezone.utc).isoformat(),
                        metadata_json=json.dumps({"extracted": extract, "resumed": result.get("resumed", False)}),
                    )
                    registry.upsert(record, event_type="download_install")
                except Exception as exc:
                    st.error(f"Reference installation failed: {exc}")
                else:
                    progress.progress(1.0, text="Installed and registered")
                    st.success("Reference asset installed.")
                    st.rerun()
    else:
        upload = st.file_uploader("Reference archive or file")
        render_upload_preflight(
            upload, key="reference_import",
            allowed_extensions=["zip", "gz", "tgz", "tar", "fasta", "fa", "fna", "faa", "vcf", "bed", "gtf", "gff", "gff3", "csv", "tsv", "txt", "json"],
            soft_limit_mb=250, hard_limit_mb=2048,
        )
        with st.form("step101_import_reference"):
            cols = st.columns(2)
            import_id = cols[0].text_input("Asset ID", "local-reference")
            import_version = cols[1].text_input("Version", "local")
            import_sha = st.text_input("Expected SHA-256")
            import_license = st.text_input("Licence", "User supplied")
            import_accept = st.checkbox("I am permitted to use and store this file")
            do_import = st.form_submit_button("Import and verify", type="primary", width="stretch")
        if do_import:
            if upload is None:
                st.error("Choose a reference file first.")
            elif not import_accept:
                st.error("Permission/licence acknowledgement is required.")
            else:
                incoming = asset_root / "incoming" / upload.name
                incoming.parent.mkdir(parents=True, exist_ok=True)
                incoming.write_bytes(upload.getvalue())
                target = asset_root / "downloads" / upload.name
                try:
                    result = import_local_asset(incoming, target, expected_sha256=import_sha)
                    registry.upsert(
                        AssetRecord(
                            asset_id=import_id,
                            provider="Local import",
                            version=import_version,
                            status="verified" if import_sha.strip() else "locally_hashed",
                            source_url="",
                            local_path=str(target),
                            expected_sha256=import_sha,
                            observed_sha256=str(result["sha256"]),
                            size_bytes=int(result["size_bytes"]),
                            license_name=import_license,
                            license_accepted=True,
                            installed_at_utc=datetime.now(timezone.utc).isoformat(),
                        ),
                        event_type="local_import",
                    )
                except Exception as exc:
                    st.error(f"Import failed: {exc}")
                else:
                    st.success("Local reference asset verified and registered.")
                    st.rerun()

with lifecycle_tab:
    asset_ids = [str(row["asset_id"]) for row in registry.list_assets()]
    if not asset_ids:
        st.info("Install or import a reference asset first.")
    else:
        selected = st.selectbox("Asset", asset_ids, key="lifecycle_asset")
        actions = st.columns(4)
        if actions[0].button("Verify now", type="primary", width="stretch"):
            try:
                result = manager.verify_installed(selected)
            except Exception as exc:
                st.error(str(exc))
            else:
                st.session_state["reference_verify_result"] = result
        if actions[1].button("Queue verification", width="stretch"):
            record = queue.submit("reference_asset_verify", {"asset_id": selected}, stages=["prepare", "hash", "validate", "finalize"], resources={"cpu_threads": 1, "ram_gb": 2}, estimated_seconds=60)
            st.success(f"Queued {record.job_id}.")
        if actions[2].button("Create rollback snapshot", width="stretch"):
            with st.spinner("Creating snapshot…"):
                result = manager.snapshot(selected)
            st.success(f"Snapshot created: {result['snapshot_id']}")
            st.rerun()
        if actions[3].button("Refresh", width="stretch"):
            st.rerun()
        if st.session_state.get("reference_verify_result"):
            smart_json(st.session_state["reference_verify_result"], title="Integrity verification")
        snapshots = manager.snapshots(selected)
        if snapshots:
            frame = pd.DataFrame(snapshots)
            smart_dataframe(frame, height=330, key="step101_reference_snapshots")
            snapshot_id = st.selectbox("Rollback snapshot", [str(row["snapshot_id"]) for row in snapshots])
            confirm = st.checkbox("I understand rollback replaces the current local asset", key="rollback_confirm")
            if st.button("Rollback selected snapshot", disabled=not confirm, width="stretch"):
                with st.spinner("Restoring snapshot atomically…"):
                    result = manager.rollback(snapshot_id)
                st.success(f"Restored {result['restored_path']}.")

with compatibility_tab:
    asset_ids = [str(row["asset_id"]) for row in registry.list_assets()]
    if not asset_ids:
        st.info("No installed assets are available.")
    else:
        selected = st.selectbox("Asset", asset_ids, key="compat_asset")
        version = next(str(row.get("version", "")) for row in registry.list_assets() if str(row["asset_id"]) == selected)
        with st.form("step101_compatibility"):
            genome_build = st.text_input("Genome build", "GRCh38")
            tool_version = st.text_input("Tool version", "")
            check = st.form_submit_button("Check compatibility", type="primary", width="stretch")
        if check:
            result = manager.compatibility_check(selected, {"asset_version": version, "genome_build": genome_build, "tool_version": tool_version})
            smart_json(result, title="Compatibility result")
        st.caption("Index commands execute as argument vectors without shell interpolation.")
        with st.form("step101_index_command"):
            index_type = st.text_input("Index type", "custom")
            command_json = st.text_area("Command vector JSON", value=json.dumps(["python", "--version"], indent=2), height=100)
            output_path = st.text_input("Expected output path", str(asset_root / "indexes" / selected / index_type))
            run_index = st.form_submit_button("Run index command", width="stretch")
        if run_index:
            try:
                command = json.loads(command_json)
                result = manager.run_index(selected, version, index_type, command, output_path)
            except Exception as exc:
                st.error(f"Indexing failed: {exc}")
            else:
                smart_json(result, title="Index result")

with storage_tab:
    quota_gb = st.number_input("Storage quota (GB, 0 = unlimited)", 0, 100_000, 500)
    summary = manager.storage_summary(quota_bytes=int(quota_gb * 1024**3) if quota_gb else None)
    smart_json(summary, title="Reference storage summary")
    keep = st.slider("Rollback snapshots retained per asset", 0, 20, 2)
    if st.button("Clean older snapshots", width="stretch"):
        result = manager.cleanup_snapshots(keep_per_asset=keep)
        st.success(f"Removed {result['removed_snapshots']} older snapshot(s).")
        st.rerun()

with history_tab:
    assets_frame = pd.DataFrame(registry.list_assets())
    events_frame = pd.DataFrame(registry.events(limit=1000))
    tabs = st.tabs(["Assets", "Events"])
    with tabs[0]:
        smart_dataframe(assets_frame, height=520, key="step101_reference_assets")
    with tabs[1]:
        smart_dataframe(events_frame, height=520, key="step101_reference_events")

# Step 108 Phase 1+2 decision visual workspace
render_phase108_visual_suite("reference_manager", ROOT, context=locals())

# Step 115 module-specific non-chart workspace: reference_db
from biointel.ui.non_chart_scientific_visuals import render_module_non_chart_panel as _render_step115_module_non_chart
_render_step115_module_non_chart("reference_db", key_prefix="step115_106_Reference_Database_Manager_reference_db", expanded=False)

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='reference_database_manager', title='Reference Database & Asset Manager', category='Data')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
