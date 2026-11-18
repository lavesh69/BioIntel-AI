from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from .catalog import pack_catalog
from .acquisition import acquisition_catalog, build_acquisition_bundle
from .manager import EngineManager
from .hardware import hardware_inventory
from .qualification import qualify_engine
from .packs import inspect_pack
from biointel.ui.public_branding import public_engine_key, public_engine_name


def render_engine_control_center() -> None:
    manager = EngineManager()
    st.title("BioIntel Engine Control Center")
    st.caption("76-engine inventory, verified offline packs, advanced format adapters, repair controls and production-service readiness. External engines remain fail-closed until licence, hash and target-machine evidence pass.")

    health = manager.health_report()
    cols = st.columns(5)
    cols[0].metric("Registered engines", health["registered_engines"])
    cols[1].metric("Qualified engines", health["qualified_engines"])
    cols[2].metric("Ready adapters", f"{health['ready_adapters']}/{health['advanced_adapters']}")
    cols[3].metric("Configured services", f"{health['configured_services']}/{health['production_services']}")
    cols[4].metric("State DB", health["database"]["status"])

    tabs = st.tabs(["Engine inventory", "Install plan", "Full acquisition", "Offline packs", "Qualification", "Format adapters", "Production services", "Operations & report"])

    with tabs[0]:
        probe = st.checkbox("Probe executable paths now", value=False, help="Runs only bounded version probes. It does not install or download engines.")
        frame = manager.catalog(probe_runtime=probe)
        priorities = sorted(frame["priority_tier"].unique())
        selected = st.multiselect("Priority", priorities, default=priorities)
        visible = frame[frame["priority_tier"].isin(selected)] if selected else frame.iloc[0:0]
        columns = ["public_engine_key", "label", "category", "priority_tier", "windows_mode", "pack_key", "qualification_status", "install_manifest_complete", "local_state", "local_version", "local_qualified", "blockers"]
        st.dataframe(visible[[column for column in columns if column in visible]], width="stretch", height=620)
        export_columns = [column for column in columns if column in frame]
        st.download_button("Download BioIntel engine inventory CSV", frame[export_columns].to_csv(index=False).encode("utf-8"), "biointel-engine-inventory.csv", "text/csv", width="stretch")

    with tabs[1]:
        catalog = manager.catalog()
        engine = st.selectbox("BioIntel engine", list(catalog["engine"]), format_func=lambda key: str(catalog.loc[catalog['engine']==key, 'label'].iloc[0]))
        pack_path = st.text_input("Optional verified offline-pack path", value="")
        if st.button("Build installation plan", type="primary", width="stretch"):
            try:
                plan = manager.plan(engine, offline_pack=pack_path or None)
                st.json(plan.to_dict())
            except Exception as exc:
                st.error(str(exc))
        left, right = st.columns(2)
        if left.button("Probe selected engine", width="stretch"):
            st.json(manager.probe(engine))
        if right.button("Repair assessment", width="stretch"):
            st.json(manager.repair(engine))

    with tabs[2]:
        st.subheader("Full scientific-engine acquisition")
        acquisition = acquisition_catalog(root=manager.project).copy()
        acquisition["public_engine_key"] = acquisition["engine"].map(public_engine_key)
        acquisition["label"] = acquisition["engine"].map(public_engine_name)
        st.dataframe(
            acquisition[["public_engine_key", "label", "priority", "mode", "windows_mode", "licence_acceptance_required", "model_weights_required", "exact_release_qualified", "blockers"]],
            width="stretch",
            height=560,
        )
        st.warning(
            "INSTALL_ALL_ENGINES_WINDOWS.bat installs eligible WSL2 packages only after explicit confirmation. "
            "Restricted-provider engines, reference databases and model weights remain separate authorized assets."
        )
        if st.button("Regenerate acquisition and qualification bundle", width="stretch"):
            destination = manager.home / "acquisition" / "v19.6"
            st.json(build_acquisition_bundle(destination, root=manager.project))

    with tabs[3]:
        st.dataframe(pack_catalog(), width="stretch")
        uploaded = st.file_uploader("Inspect/import a BioIntel Engine Pack", type=["zip", "biep"])
        if uploaded is not None:
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as handle:
                handle.write(uploaded.getbuffer())
                staged = Path(handle.name)
            try:
                inspection = inspect_pack(staged)
                st.success("Pack integrity verified")
                st.json({key: value for key, value in inspection.items() if key != "manifest"})
                restricted_ack = st.checkbox(
                    "I explicitly accept any provider/restricted licence terms declared by this pack.",
                    key="engine_pack_restricted_ack",
                )
                if st.button("Install verified pack", type="primary", width="stretch"):
                    st.json(manager.install_pack(staged, accept_restricted_licences=restricted_ack))
            except Exception as exc:
                st.error(str(exc))
            finally:
                staged.unlink(missing_ok=True)

    with tabs[4]:
        st.subheader("Target-machine qualification")
        st.json(hardware_inventory(manager.tools))
        st.caption("Qualification requires an executable SHA-256, version regex, positive fixture, negative control and expected output hashes. Arbitrary shell execution is not used.")
        qualification_file = st.file_uploader("Upload qualification specification JSON", type=["json"], key="engine_qualification_spec")
        acknowledged = st.checkbox("I confirm this specification was prepared for this exact engine release and target machine.", key="engine_qualification_ack")
        if qualification_file is not None:
            try:
                spec = json.loads(qualification_file.getvalue().decode("utf-8"))
                st.json({key: value for key, value in spec.items() if key not in {"positive_command", "negative_command"}})
                if st.button("Run bounded qualification", type="primary", disabled=not acknowledged, width="stretch"):
                    engine = str(spec.pop("engine"))
                    result = qualify_engine(engine, spec, store=manager.store, workspace_root=manager.home / "qualification")
                    st.json(result.to_dict())
                    if result.passed:
                        st.success("Target-machine qualification passed")
                    else:
                        st.error("Qualification failed closed")
            except Exception as exc:
                st.error(str(exc))

    with tabs[5]:
        st.dataframe(manager.adapter_status(), width="stretch", height=520)
        st.info("Adapters activate only when their exact package/executable is present and target-machine qualification succeeds. Binary formats are not silently approximated.")

    with tabs[6]:
        st.dataframe(manager.service_status(), width="stretch")
        st.warning("PostgreSQL, Redis, object storage, OIDC, OpenTelemetry and CRDT are optional Lab deployment services. Personal Local Mode continues to use the existing local-first stack.")

    with tabs[7]:
        st.subheader("Recent operations")
        operations = manager.store.operations()
        if operations.empty:
            st.caption("No engine operations recorded yet.")
        else:
            st.dataframe(operations, width="stretch")
        report = manager.health_report()
        st.download_button("Download engine health JSON", (json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8"), "biointel-engine-health.json", "application/json", width="stretch")
        st.caption(report["claim_boundary"])
