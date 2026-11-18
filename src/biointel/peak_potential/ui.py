from __future__ import annotations

import json
from typing import Any

from biointel import __version__
from biointel.ui.operational_canvas import render_operational_canvas

from .bundle import build_peak_bundle, safe_bundle_name
from .catalog import contract_for, is_peak_target
from .quality import build_manifest, refresh_manifest_hash, stable_error_id
from .workflow import interpretation_summary, performance_profile, requirements_for, workflow_stage_rows


def _streamlit():
    import streamlit as st

    return st


def _coerce_table(value: Any):
    import pandas as pd

    if value is None:
        return None
    if isinstance(value, pd.DataFrame):
        return value.copy(deep=False)
    if isinstance(value, pd.Series):
        return value.to_frame()
    try:
        return pd.DataFrame(value)
    except (TypeError, ValueError):
        if isinstance(value, dict):
            return pd.DataFrame([value])
        return pd.DataFrame({"value": [value]})


def _release_decision(*, has_run: bool, blockers: list[str]) -> str:
    if not has_run:
        return "awaiting_run"
    return "blocked" if blockers else "quality_checks_passed_research_use"


def render_peak_sidebar_for_page(*, page_key: str, title: str, category: str, path: str = "") -> None:
    """Attach a compact reliability contract to only the requested scientific domains."""
    if not is_peak_target(page_key=page_key, category=category, title=title):
        return
    st = _streamlit()
    contract = contract_for(page_key=page_key, title=title, category=category)
    st.session_state["_bio_peak_target_active"] = True
    st.session_state["_bio_peak_contract"] = {
        "page_key": page_key,
        "domain": contract.domain,
        "visual_minimum": contract.visual_minimum,
    }
    with st.sidebar.expander("Peak scientific assurance", expanded=False):
        st.markdown(f"**{contract.domain}**")
        st.caption(title)
        toggle_key = f"peak_enabled_{page_key}"
        if toggle_key not in st.session_state:
            st.session_state[toggle_key] = True
        peak_enabled = st.toggle(
            "Peak safeguards",
            key=toggle_key,
            help="Prevents blank visuals, exposes quality blockers and preserves reproducibility metadata.",
        )
        st.session_state["_bio_peak_mode_active"] = bool(peak_enabled)

        latest_upload = dict(st.session_state.get("_bio_latest_table_upload", {}) or {})
        latest_run = dict(st.session_state.get("_bio_latest_run", {}) or {})
        checks = {
            "Safeguards": "Active" if peak_enabled else "Paused",
            "Latest upload": "Profiled" if latest_upload else "Awaiting data",
            "Latest run": str(latest_run.get("status", "Awaiting run")).replace("_", " ").title(),
            "Visual contract": f"≥ {contract.visual_minimum} meaningful views",
        }
        st.dataframe(
            [{"Control": key, "Status": value} for key, value in checks.items()],
            hide_index=True,
            width="stretch",
            height=178,
        )
        with st.popover("Quality gates", width="stretch"):
            for gate in contract.quality_gates:
                st.markdown(f"- {gate}")
            st.caption(contract.evidence_boundary)

        diagnostic = build_manifest(
            module_key=page_key,
            title=title,
            domain=contract.domain,
            run_manifest=latest_run,
            evidence_status="research_use",
            software_version=__version__,
        )
        diagnostic["page_path"] = path
        diagnostic["upload_profile"] = latest_upload
        diagnostic["contract"] = {
            "quality_gates": list(contract.quality_gates),
            "required_outputs": list(contract.required_outputs),
            "handoffs": list(contract.handoffs),
            "visual_minimum": contract.visual_minimum,
        }
        diagnostic["capability_requirements"] = [
            item.to_dict() for item in requirements_for(page_key, contract.domain)
        ]
        diagnostic["performance_profile"] = performance_profile(page_key, contract.domain)
        diagnostic = refresh_manifest_hash(diagnostic)
        st.download_button(
            "Download assurance diagnostic",
            json.dumps(diagnostic, indent=2, sort_keys=True, default=str),
            f"{page_key}-peak-diagnostic.json",
            "application/json",
            key=f"peak_diag_{page_key}",
            width="stretch",
        )
        shell_key = f"_bio_peak_sidebar_shell_{page_key}"
        shell_hash_key = f"_bio_peak_sidebar_shell_hash_{page_key}"
        if st.session_state.get(shell_hash_key) != diagnostic.get("manifest_sha256"):
            st.session_state.pop(shell_key, None)
        if st.button(
            "Prepare evidence shell",
            key=f"peak_prepare_sidebar_shell_{page_key}",
            width="stretch",
            help="Prepared only on demand so navigation reruns remain fast.",
        ):
            try:
                st.session_state[shell_key] = build_peak_bundle(module_key=page_key, manifest=diagnostic)
                st.session_state[shell_hash_key] = diagnostic.get("manifest_sha256")
            except Exception as exc:  # pragma: no cover - Streamlit surface guard
                st.error(f"Evidence shell preparation failed safely · {stable_error_id(exc, module_key=page_key)}")
        if st.session_state.get(shell_key):
            st.download_button(
                "Download evidence shell",
                st.session_state[shell_key],
                safe_bundle_name(page_key),
                "application/zip",
                key=f"peak_bundle_{page_key}",
                width="stretch",
            )


def render_peak_assurance_workspace(
    *,
    page_key: str,
    title: str,
    category: str,
    input_frame: Any = None,
    result_frame: Any = None,
    secondary_frame: Any = None,
    extra_tables: dict[str, Any] | None = None,
    run_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Render bounded data/visual/provenance checks and an on-demand evidence bundle."""
    from .quality import audit_frame

    st = _streamlit()
    contract = contract_for(page_key=page_key, title=title, category=category)
    requirements = requirements_for(page_key, contract.domain)
    tables: dict[str, Any] = {}
    for label, value in (
        ("input", input_frame),
        ("results", result_frame),
        ("secondary", secondary_frame),
    ):
        table = _coerce_table(value)
        if table is None:
            continue
        if not table.empty or label in {"input", "results"}:
            tables[label] = table
    for label, value in (extra_tables or {}).items():
        table = _coerce_table(value)
        if table is not None and not table.empty:
            tables[f"extra_{label}"] = table

    audits = {label: audit_frame(table) for label, table in tables.items()}
    blockers = [message for audit in audits.values() for message in audit.blockers]
    warnings = [message for audit in audits.values() for message in audit.warnings]
    visual_audits = dict(st.session_state.get("_bio_peak_visual_audits", {}) or {})
    blank_visuals = [key for key, audit in visual_audits.items() if not bool(audit.get("has_data"))]
    if blank_visuals:
        blockers.append(f"{len(blank_visuals)} blank visual(s) were suppressed and require filter/data review.")

    has_run = bool(run_manifest) or result_frame is not None
    if has_run and len(visual_audits) < contract.visual_minimum:
        warnings.append(
            f"Only {len(visual_audits)} visual(s) were audited; the module contract recommends at least "
            f"{contract.visual_minimum} meaningful views."
        )

    manifest = build_manifest(
        module_key=page_key,
        title=title,
        domain=contract.domain,
        frame_audits=audits,
        run_manifest=run_manifest,
        evidence_status="research_use",
        software_version=__version__,
    )
    manifest["visual_audits"] = visual_audits
    manifest["contract"] = {
        "visual_minimum": contract.visual_minimum,
        "quality_gates": list(contract.quality_gates),
        "required_outputs": list(contract.required_outputs),
        "handoffs": list(contract.handoffs),
    }
    manifest["capability_requirements"] = [item.to_dict() for item in requirements]
    manifest["performance_profile"] = performance_profile(page_key, contract.domain)
    manifest["workflow_stages"] = workflow_stage_rows(
        upload_profile=st.session_state.get("_bio_latest_table_upload", {}),
        run_manifest=run_manifest or st.session_state.get("_bio_latest_run", {}),
        frame_audits={label: audit.to_dict() for label, audit in audits.items()},
        visual_audits=visual_audits,
        export_prepared=False,
    )
    manifest["interpretation"] = interpretation_summary(
        title=title,
        domain=contract.domain,
        run_manifest=run_manifest or st.session_state.get("_bio_latest_run", {}),
        frame_audits={label: audit.to_dict() for label, audit in audits.items()},
        visual_audits=visual_audits,
        requirements=requirements,
    )
    manifest["release_decision"] = _release_decision(has_run=has_run, blockers=blockers)
    manifest["blockers"] = list(dict.fromkeys(blockers))
    manifest["warnings"] = list(dict.fromkeys(warnings))
    manifest = refresh_manifest_hash(manifest)

    scores = [audit.score for audit in audits.values()]
    mean_score = round(sum(scores) / len(scores), 1) if scores else 0.0
    metrics = st.columns(4)
    metrics[0].metric("Quality score", f"{mean_score:.0f}/100" if scores else "Awaiting data")
    metrics[1].metric("Tables audited", len(audits))
    metrics[2].metric("Blocked issues", len(manifest["blockers"]))
    metrics[3].metric("Visuals checked", len(visual_audits))

    if manifest["release_decision"] == "awaiting_run":
        st.info("Run the module to create a release decision. Input quality is shown below without claiming completion.")
    elif manifest["blockers"]:
        st.error("Peak release is blocked until the findings below are resolved.")
    else:
        st.success("Automated quality checks passed for research-use export. External validation may still be required.")

    left, right = st.columns([1.25, 1])
    with left:
        st.markdown("#### Data quality")
        rows = []
        for label, audit in audits.items():
            rows.append(
                {
                    "Table": label,
                    "Rows": audit.rows,
                    "Audited rows": audit.audited_rows,
                    "Columns": audit.columns,
                    "Missing %": audit.missing_percent,
                    "Duplicates": audit.duplicate_rows,
                    "Infinite": audit.infinite_cells,
                    "Score": audit.score,
                }
            )
        if rows:
            st.dataframe(rows, hide_index=True, width="stretch")
        else:
            st.info("Run or import data to populate the quality audit.")
    with right:
        st.markdown("#### Release findings")
        if manifest["blockers"]:
            for item in manifest["blockers"][:12]:
                st.markdown(f"- **Blocker:** {item}")
        if manifest["warnings"]:
            for item in manifest["warnings"][:12]:
                st.markdown(f"- Review: {item}")
        if not manifest["blockers"] and not manifest["warnings"]:
            st.caption("No automated findings. Continue with domain review and external validation where applicable.")

    st.markdown("#### Scientific workflow")
    st.dataframe(manifest["workflow_stages"], hide_index=True, width="stretch", height=318)

    st.markdown("#### Interpretation and next action")
    interpretation = manifest["interpretation"]
    st.markdown(f"**Main finding:** {interpretation['finding']}")
    st.caption(f"Confidence: {interpretation['confidence']}")
    interpretation_columns = st.columns(2, gap="large")
    with interpretation_columns[0]:
        st.markdown("**Limitations / confounders**")
        for item in interpretation["limitations"][:8]:
            st.markdown(f"- {item}")
    with interpretation_columns[1]:
        st.markdown("**Recommended next actions**")
        for item in interpretation["recommended_next_actions"][:8]:
            st.markdown(f"- {item}")

    with st.expander("Module capability contract", expanded=False):
        st.dataframe([item.to_dict() for item in requirements], hide_index=True, width="stretch")
        render_operational_canvas(
            title="Performance-profile canvas",
            subtitle="Local performance and resource posture for this assurance workflow.",
            payload=manifest["performance_profile"],
            stages=("Prepare", "Execute", "Observe", "Recover"),
            key=f"peak_performance_{page_key}",
        )

    st.markdown("#### Cross-module handoff")
    st.caption("Recommended next destinations: " + " · ".join(contract.handoffs))

    # Preparing large CSV payloads on every Streamlit rerun causes freezes. Build
    # the bounded bundle only on explicit request and reuse it while the manifest
    # hash is unchanged.
    bundle_state_key = f"_bio_peak_prepared_bundle_{page_key}"
    bundle_hash_key = f"_bio_peak_prepared_hash_{page_key}"
    prepare_left, download_right = st.columns(2)
    if prepare_left.button(
        "Prepare bounded evidence bundle",
        key=f"peak_prepare_bundle_{page_key}",
        width="stretch",
        help="Exports up to 100,000 rows and 16 MB per table with explicit truncation metadata.",
    ):
        try:
            st.session_state[bundle_state_key] = build_peak_bundle(
                module_key=page_key,
                manifest=manifest,
                tables=tables,
                notes=contract.evidence_boundary,
            )
            st.session_state[bundle_hash_key] = manifest.get("manifest_sha256")
        except Exception as exc:  # pragma: no cover - Streamlit surface guard
            st.error(f"Evidence bundle preparation failed safely · {stable_error_id(exc, module_key=page_key)}")

    prepared = st.session_state.get(bundle_state_key)
    prepared_hash = st.session_state.get(bundle_hash_key)
    if prepared and prepared_hash == manifest.get("manifest_sha256"):
        download_right.download_button(
            "Download peak evidence bundle",
            prepared,
            safe_bundle_name(page_key),
            "application/zip",
            key=f"peak_workspace_bundle_{page_key}",
            width="stretch",
        )
    else:
        download_right.caption("Prepare the bundle after the latest run or filter change.")

    st.download_button(
        "Download peak manifest",
        json.dumps(manifest, indent=2, sort_keys=True, default=str),
        f"{page_key}-peak-manifest.json",
        "application/json",
        key=f"peak_workspace_manifest_{page_key}",
        width="stretch",
    )
    with st.expander("Peak scientific contract", expanded=False):
        for gate in contract.quality_gates:
            st.markdown(f"- {gate}")
        st.warning(contract.evidence_boundary)
    return manifest


def render_peak_session_footer(*, page_key: str, title: str, category: str) -> dict[str, Any] | None:
    """Summarize quality/visual checks collected while a legacy page rendered."""
    if not is_peak_target(page_key=page_key, category=category, title=title):
        return None
    st = _streamlit()
    contract = contract_for(page_key=page_key, title=title, category=category)
    requirements = requirements_for(page_key, contract.domain)
    frame_audits = dict(st.session_state.get("_bio_peak_frame_audits", {}) or {})
    visual_audits = dict(st.session_state.get("_bio_peak_visual_audits", {}) or {})
    latest_run = dict(st.session_state.get("_bio_latest_run", {}) or {})
    blank_visuals = [name for name, audit in visual_audits.items() if not bool(audit.get("has_data"))]
    table_blockers: list[str] = []
    table_warnings: list[str] = []
    for audit in frame_audits.values():
        table_blockers.extend(map(str, audit.get("blockers", []) or []))
        table_warnings.extend(map(str, audit.get("warnings", []) or []))
    if blank_visuals:
        table_blockers.append(f"{len(blank_visuals)} blank visual(s) were suppressed.")
    has_run = bool(latest_run)
    if has_run and len(visual_audits) < contract.visual_minimum:
        table_warnings.append(
            f"Only {len(visual_audits)} visual(s) were audited; {contract.visual_minimum} are recommended."
        )

    manifest = build_manifest(
        module_key=page_key,
        title=title,
        domain=contract.domain,
        run_manifest=latest_run,
        evidence_status="research_use",
        software_version=__version__,
    )
    manifest["frame_audits"] = frame_audits
    manifest["visual_audits"] = visual_audits
    manifest["blockers"] = list(dict.fromkeys(table_blockers))
    manifest["warnings"] = list(dict.fromkeys(table_warnings))
    manifest["release_decision"] = _release_decision(has_run=has_run, blockers=manifest["blockers"])
    manifest["contract"] = {
        "visual_minimum": contract.visual_minimum,
        "quality_gates": list(contract.quality_gates),
        "required_outputs": list(contract.required_outputs),
        "handoffs": list(contract.handoffs),
    }
    footer_bundle_key = f"_bio_peak_footer_bundle_{page_key}"
    footer_bundle_hash_key = f"_bio_peak_footer_bundle_hash_{page_key}"
    manifest["capability_requirements"] = [item.to_dict() for item in requirements]
    manifest["performance_profile"] = performance_profile(page_key, contract.domain)
    manifest["workflow_stages"] = workflow_stage_rows(
        upload_profile=st.session_state.get("_bio_latest_table_upload", {}),
        run_manifest=latest_run,
        frame_audits=frame_audits,
        visual_audits=visual_audits,
        export_prepared=bool(st.session_state.get(footer_bundle_key)),
    )
    manifest["interpretation"] = interpretation_summary(
        title=title,
        domain=contract.domain,
        run_manifest=latest_run,
        frame_audits=frame_audits,
        visual_audits=visual_audits,
        requirements=requirements,
    )
    manifest = refresh_manifest_hash(manifest)
    if st.session_state.get(footer_bundle_hash_key) != manifest.get("manifest_sha256"):
        st.session_state.pop(footer_bundle_key, None)

    with st.expander("Peak assurance · quality, visuals and reproducibility", expanded=False):
        columns = st.columns(4)
        columns[0].metric("Tables checked", len(frame_audits))
        columns[1].metric("Visuals checked", len(visual_audits))
        columns[2].metric("Blank visuals", len(blank_visuals))
        columns[3].metric("Run", str(latest_run.get("status", "Awaiting run")).replace("_", " ").title())
        if manifest["release_decision"] == "awaiting_run":
            st.info("Run the analysis before interpreting this as a completed quality decision.")
        elif manifest["blockers"]:
            st.error("Automated blockers remain. The module is not ready for a scientific release decision.")
            for item in manifest["blockers"][:10]:
                st.markdown(f"- {item}")
        else:
            st.success("No automated rendering/data blockers detected. Domain review and external validation still apply.")
        if manifest["warnings"]:
            with st.popover("Review warnings", width="stretch"):
                for item in manifest["warnings"][:15]:
                    st.markdown(f"- {item}")
        st.markdown("#### Workflow completion")
        st.dataframe(manifest["workflow_stages"], hide_index=True, width="stretch", height=318)
        interpretation = manifest["interpretation"]
        st.markdown(f"**Main finding:** {interpretation['finding']}")
        st.caption(f"Confidence: {interpretation['confidence']}")
        with st.popover("Limitations and next actions", width="stretch"):
            st.markdown("**Limitations / confounders**")
            for item in interpretation["limitations"][:8]:
                st.markdown(f"- {item}")
            st.markdown("**Recommended next actions**")
            for item in interpretation["recommended_next_actions"][:8]:
                st.markdown(f"- {item}")
        with st.popover("Capability contract", width="stretch"):
            st.dataframe([item.to_dict() for item in requirements], hide_index=True, width="stretch")
            render_operational_canvas(
                title="Performance-profile canvas",
                subtitle="Local performance and resource posture for this assurance workflow.",
                payload=manifest["performance_profile"],
                stages=("Prepare", "Execute", "Observe", "Recover"),
                key=f"peak_footer_performance_{page_key}",
            )
        st.caption("Recommended handoff: " + " · ".join(contract.handoffs))
        left, right = st.columns(2)
        if left.button(
            "Prepare assurance bundle",
            key=f"peak_prepare_footer_bundle_{page_key}",
            width="stretch",
            help="Generated only on demand to keep module reruns responsive.",
        ):
            try:
                st.session_state[footer_bundle_key] = build_peak_bundle(module_key=page_key, manifest=manifest)
                st.session_state[footer_bundle_hash_key] = manifest.get("manifest_sha256")
            except Exception as exc:  # pragma: no cover - Streamlit surface guard
                st.error(f"Assurance bundle preparation failed safely · {stable_error_id(exc, module_key=page_key)}")
        if st.session_state.get(footer_bundle_key):
            left.download_button(
                "Download assurance bundle",
                st.session_state[footer_bundle_key],
                safe_bundle_name(page_key),
                "application/zip",
                key=f"peak_footer_bundle_{page_key}",
                width="stretch",
            )
        right.download_button(
            "Download assurance manifest",
            json.dumps(manifest, indent=2, sort_keys=True, default=str),
            f"{page_key}-peak-manifest.json",
            "application/json",
            key=f"peak_footer_manifest_{page_key}",
            width="stretch",
        )
        st.warning(contract.evidence_boundary)
    return manifest
