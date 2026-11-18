from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from uuid import uuid4

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.reference_lifecycle import BUILTIN_REFERENCE_CATALOG, ReferenceLifecycleManager
from biointel.ui.components import metric_cards, scientific_boundary_banner, smart_dataframe, smart_json
from biointel.ui.theme import apply_theme, hero, section_title
from biointel.ui.workflow import render_upload_preflight, stage_streamlit_upload

st.set_page_config(page_title="Reference Database Lifecycle Manager · BioIntel AI", page_icon="🗄️", layout="wide")
apply_theme()

# STEP196_CONTEXTUAL_ONLINE_RESEARCH_HOOK · TOP RELEVANT WEBSITES
from biointel.contextual_research_v196.ui import render_contextual_online_research as _render_step196_contextual_online_research
_render_step196_contextual_online_research('reference_lifecycle_v2', expanded=False)

# STEP116_MODULE_EXPERIENCE_2_TO_9
from biointel.ui.module_experience_2_9 import render_module_experience as _render_step116_module_experience
_render_step116_module_experience("reference_lifecycle", key_prefix="step116_153_Reference_Database_Lifecycle_Manager_2_reference_lifecycle_1", expanded=False)
hero(
    "🗄️ Reference Database Lifecycle Manager",
    "Plan, register, verify, activate, roll back and audit local scientific reference databases with checksums, licences, compatibility metadata and storage forecasts.",
    eyebrow="Data Infrastructure · Reproducible Reference Assets",
    chips=["Version pinning", "SHA-256", "Rollback", "Licence tracking", "Dependency map"],
)
scientific_boundary_banner(
    source_kind="reference",
    release_eligible=False,
    message="Reference assets remain subject to provider licences, release notes, organism/build compatibility and project-specific validation. Activation does not imply scientific suitability.",
)
manager = ReferenceLifecycleManager(ROOT)

catalog_tab, register_tab, verify_tab, storage_tab, export_tab = st.tabs(
    ["1 · Catalogue & planning", "2 · Register / download", "3 · Verify / activate / rollback", "4 · Storage & dependencies", "5 · Manifest & audit"]
)

with catalog_tab:
    catalog = pd.DataFrame([item.to_dict() for item in BUILTIN_REFERENCE_CATALOG])
    catalog["expected_size_gb"] = (catalog["expected_size_bytes"] / 1_000_000_000).round(2)
    catalog["required_tools"] = catalog["required_tools"].map(lambda value: ", ".join(value) or "None")
    catalog["index_outputs"] = catalog["index_outputs"].map(lambda value: ", ".join(value))
    metric_cards([
        ("Curated database profiles", len(catalog), "Planning profiles; provider release metadata must be confirmed"),
        ("Estimated combined storage", f"{catalog['expected_size_gb'].sum():,.1f} GB", "Uncompressed planning estimate"),
        ("Database categories", int(catalog["database_name"].nunique()), None),
        ("Managed versions", len(manager.list_references()), "Locally registered versions"),
    ])
    selected_name = st.selectbox("Reference profile", catalog["database_name"].tolist())
    selected_profile = next(item for item in BUILTIN_REFERENCE_CATALOG if item.database_name == selected_name)
    smart_json(selected_profile.to_dict(), title="Selected planning profile", download_name="reference_profile.json", key="step112_reference_profile")
    smart_dataframe(catalog[["database_name", "version", "license_name", "expected_size_gb", "required_tools", "index_outputs"]], height=480, key="step112_reference_catalog")

    section_title("Create a controlled download plan", "⬇️")
    c1, c2 = st.columns(2)
    database_name = c1.text_input("Database name", value=selected_profile.database_name, key="ref_plan_name")
    version = c2.text_input("Version / release", value=selected_profile.version, key="ref_plan_version")
    source_url = st.text_input("Official HTTP(S) or file URL", value=selected_profile.source_url, placeholder="https://provider.example/reference.tar.gz")
    d1, d2 = st.columns(2)
    expected_size_gb = d1.number_input("Expected download size (GB)", min_value=0.0, max_value=10_000.0, value=float(selected_profile.expected_size_bytes / 1_000_000_000), step=0.1)
    expected_sha = d2.text_input("Expected SHA-256 (optional)", value="")
    license_name = st.text_input("Licence / provider terms", value=selected_profile.license_name)
    accepted = st.checkbox("I reviewed and accept the provider licence/terms for this local download plan")
    free_bytes = shutil.disk_usage(ROOT).free
    st.caption(f"Free disk space at project location: {free_bytes / 1_000_000_000:,.1f} GB")
    if expected_size_gb * 1_000_000_000 > free_bytes:
        st.error("Expected download exceeds currently available disk space.")
    if st.button("Create download plan", type="primary", width="stretch", disabled=not bool(source_url.strip() and accepted)):
        try:
            plan = manager.create_download_plan(
                database_name,
                version,
                source_url,
                expected_size_bytes=int(expected_size_gb * 1_000_000_000),
                license_name=license_name,
                license_accepted=accepted,
                checksum_expected=expected_sha,
            )
            st.success(f"Created plan {plan['plan_id']}")
            st.session_state["step112_last_download_plan"] = plan["plan_id"]
        except Exception as exc:
            st.error(str(exc))
    plans = manager.list_download_plans()
    if not plans.empty:
        smart_dataframe(plans, height=360, key="step112_download_plans")

with register_tab:
    source_mode = st.radio("Registration source", ["Upload one archive/file", "Register an existing local file or directory", "Execute a prepared download plan"], horizontal=True)
    if source_mode == "Upload one archive/file":
        upload = st.file_uploader("Reference asset", type=None, key="step112_reference_upload")
        upload_profile = render_upload_preflight(
            upload,
            key="step112_reference_upload_preflight",
            allowed_extensions=None,
            soft_limit_mb=100,
            hard_limit_mb=1024,
            block_large_files=False,
            module_key="reference_lifecycle_v2",
        )
        c1, c2, c3 = st.columns(3)
        db_name = c1.text_input("Database name", key="ref_upload_name")
        db_version = c2.text_input("Version", key="ref_upload_version")
        db_license = c3.text_input("Licence / terms", key="ref_upload_license")
        source_url_reg = st.text_input("Source URL / provider page", key="ref_upload_source")
        required_tools = st.text_input("Required tools (comma separated)", value="")
        index_outputs = st.text_input("Expected index outputs (comma separated)", value="")
        if st.button(
            "Store and register uploaded asset",
            type="primary",
            width="stretch",
            disabled=upload is None or upload_profile is None,
        ):
            incoming_root: Path | None = None
            try:
                incoming_root = manager.state_root / "incoming" / uuid4().hex
                incoming_root.mkdir(parents=True, exist_ok=False)
                safe_name = Path(upload.name).name
                target = incoming_root / safe_name
                staged = stage_streamlit_upload(
                    upload,
                    target,
                    max_bytes=1024 * 1024 * 1024,
                )
                if upload_profile is not None and staged["sha256"] != upload_profile.sha256:
                    raise ValueError("Upload changed between preflight and managed-storage staging.")
                record = manager.register_path(
                    db_name,
                    db_version,
                    target,
                    license_name=db_license,
                    source_url=source_url_reg,
                    required_tools=[item.strip() for item in required_tools.split(",") if item.strip()],
                    index_outputs=[item.strip() for item in index_outputs.split(",") if item.strip()],
                    copy_into_managed_storage=True,
                )
                st.success(f"Registered {record['database_name']} {record['version']}")
            except Exception as exc:
                st.error(str(exc))
            finally:
                if incoming_root is not None:
                    shutil.rmtree(incoming_root, ignore_errors=True)
    elif source_mode == "Register an existing local file or directory":
        c1, c2 = st.columns(2)
        db_name = c1.text_input("Database name", key="ref_local_name")
        db_version = c2.text_input("Version", key="ref_local_version")
        local_path = st.text_input("Existing local path", value="")
        c3, c4 = st.columns(2)
        db_license = c3.text_input("Licence / terms", key="ref_local_license")
        source_url_reg = c4.text_input("Source URL / provider page", key="ref_local_source")
        copy_managed = st.toggle("Copy into managed reference storage", value=False)
        if st.button("Verify and register local asset", type="primary", width="stretch"):
            try:
                record = manager.register_path(db_name, db_version, local_path, license_name=db_license, source_url=source_url_reg, copy_into_managed_storage=copy_managed)
                st.success(f"Registered {record['database_name']} {record['version']}")
            except Exception as exc:
                st.error(str(exc))
    else:
        plans = manager.list_download_plans()
        if plans.empty:
            st.info("Create a download plan first.")
        else:
            options = {f"{row.database_name} {row.version} · {row.status}": row.plan_id for row in plans.itertuples(index=False)}
            selected_plan = st.selectbox("Download plan", options)
            max_gb = st.number_input("Hard download limit (GB)", min_value=0.1, max_value=1000.0, value=250.0, step=1.0)
            st.warning("The download runs in the current process in this build. Use the Background Job Center for very large provider assets.")
            confirm = st.checkbox("Start the reviewed resumable download now")
            if st.button("Execute selected download", type="primary", width="stretch", disabled=not confirm):
                try:
                    result = manager.execute_download(options[selected_plan], max_download_bytes=int(max_gb * 1_000_000_000))
                    st.success(f"Downloaded {result['size_bytes'] / 1_000_000:.2f} MB")
                    smart_json(result, title="Download result", download_name="reference_download_result.json", key="step112_download_result")
                except Exception as exc:
                    st.error(str(exc))

with verify_tab:
    references = manager.list_references()
    if references.empty:
        st.info("No reference versions are registered.")
    else:
        display = references.copy()
        display["size_gb"] = (display["size_bytes"] / 1_000_000_000).round(3)
        metric_cards([
            ("Registered versions", len(display), None),
            ("Active versions", int(display["active"].sum()), None),
            ("Registered storage", f"{display['size_gb'].sum():,.2f} GB", None),
            ("Database families", display["database_name"].nunique(), None),
        ])
        smart_dataframe(display[["reference_id", "database_name", "version", "status", "active", "size_gb", "file_count", "verified_at_utc", "local_path"]], height=420, key="step112_reference_versions")
        options = {f"{row.database_name} {row.version} · {row.status}": row.reference_id for row in display.itertuples(index=False)}
        selected = st.selectbox("Selected reference version", options)
        b1, b2, b3 = st.columns(3)
        if b1.button("Verify checksum now", width="stretch"):
            try:
                st.session_state["step112_verify_result"] = manager.verify(options[selected])
            except Exception as exc:
                st.error(str(exc))
        if b2.button("Activate verified version", width="stretch"):
            try:
                activated = manager.activate(options[selected])
                st.success(f"Activated {activated['database_name']} {activated['version']}")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
        selected_record = manager.get_reference(options[selected])
        if b3.button("Rollback database family", width="stretch"):
            try:
                rolled = manager.rollback(selected_record["database_name"])
                st.success(f"Rolled back to {rolled['version']}")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
        verify_result = st.session_state.get("step112_verify_result")
        if verify_result:
            smart_json(verify_result, title="Checksum verification", download_name="reference_verification.json", key="step112_verify_json")

with storage_tab:
    storage = manager.storage_summary()
    dependencies = manager.dependency_matrix()
    if storage.empty:
        st.info("Register a reference version to populate storage analytics.")
    else:
        storage["size_gb"] = storage["size_bytes"] / 1_000_000_000
        st.plotly_chart(px.bar(storage, x="database_name", y="size_gb", color="active_versions", title="Managed reference storage by database"), width="stretch")
        smart_dataframe(storage, height=340, key="step112_reference_storage")
    section_title("Tool and index dependency matrix", "🔗")
    smart_dataframe(dependencies, height=460, key="step112_reference_dependencies")

with export_tab:
    manifest = manager.export_manifest()
    events = manager.events()
    smart_json(manifest, title="Reference lifecycle manifest", download_name="reference_lifecycle_manifest.json", key="step112_reference_manifest")
    if not events.empty:
        smart_dataframe(events, height=420, key="step112_reference_events")
    st.download_button("Download complete lifecycle manifest", json.dumps(manifest, indent=2, sort_keys=True, default=str).encode(), "reference_lifecycle_manifest.json", "application/json", width="stretch", key="step112_reference_manifest_download")

# Step 115 module-specific non-chart workspace: reference_db
from biointel.ui.non_chart_scientific_visuals import render_module_non_chart_panel as _render_step115_module_non_chart
_render_step115_module_non_chart("reference_db", key_prefix="step115_153_Reference_Database_Lifecycle_Manager_2_reference_db", expanded=False)

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='reference_lifecycle_v2', title='Reference Database Lifecycle Manager', category='Data')

# Step 179 platform/core production assurance
from biointel.target_modules_v179.ui import render_step179_module_upgrade as _render_step179_module_upgrade
_render_step179_module_upgrade("reference_lifecycle_v2", expanded=False)

# Step 183 all-module synthetic demo bundle
from biointel.portfolio_demo_v183.ui import render_step183_portfolio_demo as _render_step183_portfolio_demo
_render_step183_portfolio_demo("reference_lifecycle_v2", expanded=False)


# Step 186 final platform completion assurance
from biointel.platform_completion_v186.ui import render_step186_platform_completion as _render_step186_platform_completion
_render_step186_platform_completion("reference_lifecycle_v2", expanded=False)

# STEP188_MAJOR_MODULE_STANDARD_HOOK
from biointel.major_module_standard_v188.ui import render_step188_major_module_standard as _render_step188_major_module_standard
_render_step188_major_module_standard('reference_lifecycle_v2', expanded=False)

# STEP189_UNIVERSAL_PLATFORM_HOOK
from biointel.universal_platform_v189.ui import render_step189_universal_platform as _render_step189_universal_platform
_render_step189_universal_platform('reference_lifecycle_v2', expanded=False)

# STEP190_SCIENTIFIC_EXECUTION_HOOK
from biointel.scientific_execution_v190.ui import render_step190_scientific_execution as _render_step190_scientific_execution
_render_step190_scientific_execution('reference_lifecycle_v2', expanded=False)

# STEP192_RELEASE_INTEGRITY_PUBLICATION_HOOK
from biointel.release_integrity_v192.ui import render_step192_release_integrity as _render_step192_release_integrity
_render_step192_release_integrity('reference_lifecycle_v2', expanded=False)


# STEP193_MANDATORY_COMPLETION_HOOK
from biointel.mandatory_completion_v193.ui import render_step193_mandatory_completion as _render_step193_mandatory_completion
_render_step193_mandatory_completion('reference_lifecycle_v2', expanded=False)
