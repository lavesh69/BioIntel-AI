from __future__ import annotations

import json
import sqlite3
import sys
from dataclasses import asdict, replace
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.database.core import managed_connect  # noqa: E402

from biointel.data.dataset_registry import register_dataset
from biointel.integrations.public_sync import (
    sync_chembl_activities,
    sync_status,
    sync_uniprot_reviewed,
)
from biointel.internet.connectivity import (
    check_internet_services,
    internet_configuration,
)
from biointel.internet.download_registry import (
    download_summary,
    initialize_download_registry,
    list_downloads,
)
from biointel.internet.downloader import (
    InternetDownloadError,
    download_public_file,
)
from biointel.internet.network_policy import (
    NetworkPolicyError,
    internet_policy_from_environment,
)
from biointel.internet.pubchem import fetch_pubchem_compound_by_name
from biointel.internet.rcsb import (
    FORMATS,
    batch_download_rcsb,
    download_rcsb_structure,
    fetch_rcsb_entry,
)
from biointel.jobs.local_queue import LocalJobQueue
from biointel.ui.components import smart_dataframe, smart_json
from biointel.ui.performance import read_csv_cached
from biointel.ui.theme import (
    apply_theme,
    badge,
    command_bar,
    database_cards,
    executive_kpis,
    hero,
    insight_callout,
    section_title,
)
from biointel.ui.workflow import analysis_run, indeterminate_loader

st.set_page_config(
    page_title="Internet Research Hub · BioIntel AI",
    page_icon="🌐",
    layout="wide",
)

apply_theme()
registry_path = ROOT / "reports" / "internet_downloads.sqlite3"
initialize_download_registry(registry_path)
summary = download_summary(registry_path)
configuration = internet_configuration()
policy = internet_policy_from_environment()

hero(
    "Secure internet access for scientific research downloads.",
    (
        "Fetch RCSB PDB structures, resolve compounds with PubChem, use official UniProt and ChEMBL services, "
        "or import public HTTPS research files with provenance, checksums, "
        "retry handling and a local download registry."
    ),
    eyebrow="Quality-Hardened · Internet Research Hub",
    chips=[
        "RCSB PDB",
        "PubChem compounds",
        "Public HTTPS import",
        "SHA-256 provenance",
        "Offline-safe local storage",
    ],
)

badge(
    (
        "● Outbound internet enabled"
        if policy.enabled
        else "● Internet access disabled by environment"
    ),
    "success" if policy.enabled else "warning",
)



executive_kpis(
    [
        (
            "Downloaded files",
            f"{summary['downloads']:,}",
            "Tracked in the local internet-download registry",
        ),
        (
            "Stored bytes",
            f"{summary['total_bytes'] / (1024 * 1024):.2f} MB",
            "Scientific files plus provenance sidecars",
        ),
        (
            "Maximum file",
            f"{policy.max_download_bytes / (1024 * 1024):.0f} MB",
            "Configurable outbound safety limit",
        ),
        (
            "Server exposure",
            "Localhost only",
            "Internet access is outbound; app ports remain local",
        ),
    ]
)

pdb_tab, pubchem_tab, batch_tab, sync_tab, url_tab, library_tab, status_tab = st.tabs(
    [
        "RCSB PDB",
        "PubChem Compound",
        "Batch PDB",
        "Scientific Data Sync",
        "Public HTTPS Import",
        "Download Library",
        "Connectivity & Policy",
    ]
)

with pdb_tab:
    command_bar(
        "RCSB PDB structure retrieval",
        "Read official entry metadata and download PDBx/mmCIF or legacy PDB coordinate files.",
    )
    controls = st.columns([1.4, 1.2, 1])
    pdb_id = controls[0].text_input(
        "PDB identifier",
        value="4HHB",
        help="Classic ID: 4HHB. Extended ID: pdb_00006UV8.",
    )
    format_label = controls[1].selectbox(
        "Structure format",
        list(FORMATS),
        index=0,
    )
    metadata_clicked = controls[2].button(
        "Fetch metadata",
        type="primary",
        width="stretch",
    )

    if metadata_clicked:
        try:
            entry = fetch_rcsb_entry(pdb_id, policy=policy)
        except (ValueError, NetworkPolicyError, InternetDownloadError) as exc:
            st.error(str(exc))
        else:
            st.session_state["rcsb_entry"] = asdict(entry)

    entry_data = st.session_state.get("rcsb_entry")
    if entry_data:
        st.markdown(f"## {entry_data['pdb_id']} · {entry_data['title']}")
        metrics = st.columns(5)
        metrics[0].metric(
            "Method",
            ", ".join(entry_data["experimental_methods"]) or "Not provided",
        )
        metrics[1].metric(
            "Resolution",
            (
                f"{entry_data['resolution_angstrom']:.2f} Å"
                if entry_data["resolution_angstrom"] is not None
                else "N/A"
            ),
        )
        metrics[2].metric(
            "Polymer entities",
            entry_data["polymer_entity_count"] or "N/A",
        )
        metrics[3].metric(
            "Non-polymers",
            entry_data["nonpolymer_entity_count"] or "N/A",
        )
        metrics[4].metric(
            "Atoms",
            (
                f"{entry_data['deposited_atom_count']:,}"
                if entry_data["deposited_atom_count"]
                else "N/A"
            ),
        )
        st.caption(f"Initial release: {entry_data['initial_release_date'] or 'Not provided'}")
        st.download_button(
            "Download entry metadata JSON",
            json.dumps(entry_data, indent=2),
            f"{entry_data['pdb_id']}_rcsb_metadata.json",
            "application/json",
        )

    if st.button(
        "Download structure to BioIntel workspace",
        width="stretch",
    ):
        try:
            result, record = download_rcsb_structure(
                pdb_id,
                FORMATS[format_label],
                project_root=ROOT,
                policy=policy,
            )
        except (ValueError, NetworkPolicyError, InternetDownloadError) as exc:
            st.error(str(exc))
        else:
            st.session_state["last_internet_download"] = asdict(result)
            st.success(
                f"Saved {result.filename} · {result.size_bytes:,} bytes · "
                f"SHA-256 {result.sha256[:16]}…"
            )
            st.code(result.relative_path, language=None)
            if result.size_bytes <= 25 * 1024 * 1024:
                st.download_button(
                    "Download saved structure",
                    result.path.read_bytes(),
                    result.filename,
                    result.content_type,
                )
            st.caption(f"Registry record: {record.download_id}")

    insight_callout(
        "Recommended format",
        (
            "PDBx/mmCIF is the current archive format and supports both classic "
            "and extended PDB identifiers. Legacy PDB download remains available "
            "for compatible classic entries."
        ),
        "🧬",
    )


with pubchem_tab:
    command_bar(
        "Official PubChem compound-name resolver",
        (
            "Resolve a common or systematic compound name to PubChem CID, "
            "canonical SMILES and selected molecular properties."
        ),
    )
    controls = st.columns([3, 1])
    compound_name = controls[0].text_input(
        "Compound or drug name",
        value="aspirin",
        key="internet_hub_pubchem_name",
    )
    lookup_clicked = controls[1].button(
        "Resolve with PubChem",
        type="primary",
        width="stretch",
        key="internet_hub_pubchem_lookup",
    )
    if lookup_clicked:
        try:
            compound = fetch_pubchem_compound_by_name(
                compound_name,
                policy=policy,
            )
        except (
            ValueError,
            NetworkPolicyError,
            InternetDownloadError,
        ) as exc:
            st.error(str(exc))
        else:
            st.session_state["internet_hub_pubchem_result"] = asdict(compound)

    pubchem_result = st.session_state.get("internet_hub_pubchem_result")
    if pubchem_result:
        st.markdown(f"## {pubchem_result['title']} · CID {pubchem_result['cid']}")
        metrics = st.columns(4)
        metrics[0].metric(
            "Formula",
            pubchem_result.get("molecular_formula") or "N/A",
        )
        metrics[1].metric(
            "Molecular weight",
            (
                f"{pubchem_result['molecular_weight']:.2f}"
                if pubchem_result.get("molecular_weight") is not None
                else "N/A"
            ),
        )
        metrics[2].metric(
            "XLogP",
            (
                f"{pubchem_result['xlogp']:.2f}"
                if pubchem_result.get("xlogp") is not None
                else "N/A"
            ),
        )
        metrics[3].metric(
            "InChIKey",
            pubchem_result.get("inchikey") or "N/A",
        )
        st.code(
            pubchem_result["canonical_smiles"],
            language=None,
        )
        if pubchem_result.get("iupac_name"):
            st.caption(f"IUPAC name: {pubchem_result['iupac_name']}")
        action_columns = st.columns(2)
        if action_columns[0].button(
            "Send SMILES to Drug Analyzer",
            type="primary",
            width="stretch",
        ):
            st.session_state["imported_smiles"] = pubchem_result["canonical_smiles"]
            st.success("SMILES added to session. Open Drug SMILES Analyzer from the sidebar.")
        action_columns[1].download_button(
            "Download PubChem result JSON",
            json.dumps(pubchem_result, indent=2),
            f"pubchem_{pubchem_result['cid']}.json",
            "application/json",
            width="stretch",
        )

    insight_callout(
        "Name resolution is not approval evidence",
        (
            "PubChem identifiers and structures support research lookup. "
            "They do not establish medicine approval, safety, efficacy or indication."
        ),
        "⚗️",
    )

with batch_tab:
    command_bar(
        "Controlled PDB batch download",
        "Download up to 50 unique entries per run; one failed entry does not cancel the remaining batch.",
    )
    raw_ids = st.text_area(
        "PDB identifiers",
        value="4HHB\n1BNA\n1CRN",
        height=150,
        help="Separate identifiers with commas, spaces or new lines.",
    )
    batch_format_label = st.selectbox(
        "Batch format",
        list(FORMATS),
        key="pdb_batch_format",
    )
    if st.button("Run PDB batch download", type="primary"):
        identifiers = [item for item in raw_ids.replace(",", " ").split() if item.strip()]
        try:
            results = batch_download_rcsb(
                identifiers,
                FORMATS[batch_format_label],
                project_root=ROOT,
                policy=policy,
                max_entries=50,
            )
        except (ValueError, NetworkPolicyError) as exc:
            st.error(str(exc))
        else:
            frame = pd.DataFrame(results)
            smart_dataframe(frame)
            completed = int((frame["status"] == "completed").sum())
            st.success(f"Completed {completed}/{len(frame)} PDB downloads.")
            st.download_button(
                "Download batch result CSV",
                frame.to_csv(index=False),
                "rcsb_pdb_batch_results.csv",
                "text/csv",
            )


with sync_tab:
    command_bar(
        "Official scientific reference synchronization",
        "Download bounded, paginated public-reference records from official ChEMBL and UniProt services. Synced records remain reference-only until curation and evidence review are complete.",
    )
    status_payload = sync_status(ROOT, limit=200)
    sync_metrics = st.columns(3)
    sync_metrics[0].metric("Normalized records", f"{status_payload['normalized_records']:,}")
    sync_metrics[1].metric("Sync runs", f"{len(status_payload['runs']):,}")
    sync_metrics[2].metric("Providers used", f"{len(status_payload['provider_runs']):,}")
    provider = st.radio("Official provider", ["ChEMBL activities", "UniProt reviewed proteins"], horizontal=True)
    with st.form("official_scientific_sync"):
        columns = st.columns(3)
        maximum_records = columns[0].number_input(
            "Maximum records",
            min_value=10,
            max_value=10_000 if provider.startswith("ChEMBL") else 5_000,
            value=500,
            step=100,
        )
        if provider.startswith("ChEMBL"):
            organism = columns[1].text_input("Target organism", value="Homo sapiens")
            columns[2].caption("Activity endpoints: Ki, Kd, IC50 and EC50 in nM")
        else:
            organism_id = columns[1].number_input("NCBI taxonomy ID", min_value=1, value=9606, step=1)
            columns[2].caption("Reviewed UniProtKB/Swiss-Prot metadata")
        background = st.toggle("Queue as background job", value=False, help="Requires RUN_LOCAL_WORKER_WINDOWS.bat or scripts/run_local_worker.py to be running.")
        run_sync = st.form_submit_button("Queue sync" if background else "Run official sync", type="primary", width="stretch", disabled=not policy.enabled)
    if run_sync:
        try:
            if background:
                queue = LocalJobQueue(ROOT / "reports" / "jobs.sqlite3")
                job_type = "scientific_sync_chembl" if provider.startswith("ChEMBL") else "scientific_sync_uniprot"
                payload = ({"maximum_records": int(maximum_records), "organism": organism} if provider.startswith("ChEMBL") else {"maximum_records": int(maximum_records), "organism_id": int(organism_id)})
                job = queue.submit(job_type, payload, priority=40, stages=["prepare", "download", "normalize", "validate", "finalize"])
                st.success(f"Queued {job.job_id}. Start RUN_LOCAL_WORKER_WINDOWS.bat to process it.")
            else:
                with analysis_run(f"Synchronizing {provider}"):
                    if provider.startswith("ChEMBL"):
                        result = sync_chembl_activities(ROOT, maximum_records=int(maximum_records), organism=organism)
                    else:
                        result = sync_uniprot_reviewed(ROOT, maximum_records=int(maximum_records), organism_id=int(organism_id))
                st.success(f"Synced {result.records:,} {result.provider} records to {result.output_path}.")
                st.toast("Official scientific sync completed", icon="✅")
        except (RuntimeError, ValueError) as exc:
            st.error(str(exc))
    refreshed = sync_status(ROOT, limit=200)
    if refreshed["runs"]:
        runs = pd.DataFrame(refreshed["runs"])
        smart_dataframe(runs, height=420)
    else:
        st.info("No official provider synchronization has been run in this workspace yet.")
    insight_callout(
        "Scientific boundary",
        "ChEMBL activity records require curation, licence review, endpoint separation and evidence approval before model training. UniProt records are verified protein references, not activity evidence.",
        "🧾",
    )

with url_tab:
    command_bar(
        "Secure public HTTPS importer",
        (
            "Download research CSV, TSV, JSON, FASTA, PDB, CIF, text, PDF, GZ or ZIP files. "
            "Executables and scripts are blocked; archives are never auto-extracted."
        ),
    )
    url = st.text_input(
        "Public HTTPS URL",
        placeholder="https://example.org/research/data.csv",
    )
    options = st.columns(3)
    provider = options[0].text_input(
        "Provider label",
        value="Public HTTPS",
    )
    preferred_filename = options[1].text_input(
        "Optional filename",
        placeholder="dataset.csv",
    )
    official_only = options[2].toggle(
        "Official hosts only",
        value=policy.official_hosts_only,
        help="Restrict downloads to configured scientific hosts.",
    )
    max_mb = st.slider(
        "Per-file download limit (MB)",
        min_value=1,
        max_value=int(policy.max_download_bytes / (1024 * 1024)),
        value=min(100, int(policy.max_download_bytes / (1024 * 1024))),
    )
    active_policy = replace(policy, official_hosts_only=official_only)

    if st.button("Download public research file", type="primary", width="stretch"):
        try:
            result, record = download_public_file(
                url,
                ROOT / "data" / "internet_downloads" / "public_https",
                project_root=ROOT,
                registry_path=registry_path,
                provider=provider.strip() or "Public HTTPS",
                resource_id=None,
                preferred_filename=preferred_filename.strip() or None,
                policy=active_policy,
                max_bytes=max_mb * 1024 * 1024,
                notes="User-requested public HTTPS research download.",
            )
        except (NetworkPolicyError, InternetDownloadError, ValueError) as exc:
            st.error(str(exc))
        else:
            st.session_state["last_internet_download"] = asdict(result)
            st.success(
                f"Saved {result.filename} · {result.size_bytes:,} bytes · "
                f"SHA-256 {result.sha256[:16]}…"
            )
            st.code(result.relative_path, language=None)
            st.caption(f"Download registry record: {record.download_id}")

    last = st.session_state.get("last_internet_download")
    if last:
        file_path = Path(str(last["path"]))
        if file_path.is_file() and file_path.suffix.lower() in {".csv", ".tsv"}:
            section_title("Register downloaded tabular data", "🧾")
            separator = "\t" if file_path.suffix.lower() == ".tsv" else ","
            try:
                preview = read_csv_cached(file_path, sep=separator, nrows=100)
            except Exception as exc:
                st.warning(f"Tabular preview failed: {exc}")
            else:
                st.dataframe(preview, width="stretch", hide_index=True)
                with st.form("register_remote_dataset"):
                    dataset_name = st.text_input(
                        "Dataset name",
                        value=file_path.stem,
                    )
                    dataset_version = st.text_input("Version", value="1.0")
                    task_type = st.selectbox(
                        "Task type",
                        ["unlabelled", "classification", "regression"],
                    )
                    register_clicked = st.form_submit_button(
                        "Register full downloaded dataset",
                        type="primary",
                    )
                    if register_clicked:
                        try:
                            full_frame = read_csv_cached(file_path, sep=separator)
                            record = register_dataset(
                                ROOT / "reports" / "datasets.sqlite3",
                                full_frame,
                                dataset_name=dataset_name,
                                dataset_version=dataset_version,
                                task_type=task_type,
                                source_description=str(last["final_url"]),
                                notes="Downloaded through BioIntel Internet Research Hub.",
                                metadata={
                                    "remote_url": last["final_url"],
                                    "download_sha256": last["sha256"],
                                    "download_path": last["relative_path"],
                                },
                            )
                        except Exception as exc:
                            st.error(str(exc))
                        else:
                            st.success(
                                f"Registered {record.dataset_name} · {record.row_count:,} rows."
                            )

with library_tab:
    section_title("Local internet-download library", "📥")
    records = list_downloads(registry_path, limit=1000)
    provider_values = ["all", *sorted({record.provider for record in records})]
    selected_provider = st.selectbox("Provider filter", provider_values)
    filtered = [
        record
        for record in records
        if selected_provider == "all" or record.provider == selected_provider
    ]
    if not filtered:
        st.info("No internet downloads are registered yet.")
    else:
        frame = pd.DataFrame([asdict(record) for record in filtered])
        smart_dataframe(frame)
        selected = st.selectbox(
            "Inspect saved file",
            frame["filename"].tolist(),
        )
        row = frame.loc[frame["filename"] == selected].iloc[0]
        saved_path = ROOT / str(row["relative_path"])
        details = st.columns(4)
        details[0].metric("Provider", row["provider"])
        details[1].metric("Size", f"{int(row['size_bytes']):,} bytes")
        details[2].metric("Type", row["content_type"])
        details[3].metric("Status", row["status"])
        st.code(str(row["relative_path"]), language=None)
        if saved_path.is_file() and saved_path.stat().st_size <= 25 * 1024 * 1024:
            st.download_button(
                "Download selected local file",
                saved_path.read_bytes(),
                saved_path.name,
                str(row["content_type"]),
            )
        elif saved_path.is_file():
            st.info("Large file retained locally; use the displayed path to access it.")

with status_tab:
    section_title("Internet configuration", "⚙️")
    smart_json(configuration)
    database_cards(
        [
            {
                "icon": "🧬",
                "title": "RCSB PDB",
                "copy": "Official structure metadata and coordinate-file downloads.",
                "status": "configured",
                "stats": [("Metadata", "REST"), ("Files", "CIF/PDB"), ("Batch", "50")],
            },
            {
                "icon": "🧫",
                "title": "PubChem, UniProt & ChEMBL",
                "copy": "Official compound, protein and chemistry lookup integrations.",
                "status": "configured",
                "stats": [("PubChem", "SMILES"), ("UniProt", "FASTA"), ("ChEMBL", "JSON")],
            },
            {
                "icon": "🔒",
                "title": "Network Safety",
                "copy": "HTTPS-only public hosts, private-network blocking and executable-file blocking.",
                "status": "enforced",
                "stats": [
                    ("Inbound", "None"),
                    ("Redirects", "Checked"),
                    ("Archives", "No extract"),
                ],
            },
        ]
    )
    if st.button("Check scientific internet services", type="primary"):
        with indeterminate_loader("Checking RCSB PDB, PubChem, UniProt and ChEMBL…"):
            result = check_internet_services(policy=policy)
        st.session_state["internet_service_check"] = result
    if st.session_state.get("internet_service_check"):
        result = st.session_state["internet_service_check"]
        st.metric(
            "Available services",
            f"{result['available_count']}/{len(result['services'])}",
        )
        st.dataframe(
            pd.DataFrame([{"Service": key, **value} for key, value in result["services"].items()]),
            width="stretch",
            hide_index=True,
        )

st.info(
    "Remote files are untrusted research inputs. BioIntel records provenance and checksums, "
    "but you must verify licences, scientific validity, identifiers and data quality before use."
)


section_title("Scientific source connector catalogue", "🧭")
try:
    with managed_connect(registry_path) as connection:
        connection.row_factory = sqlite3.Row
        source_rows = [dict(row) for row in connection.execute("SELECT * FROM scientific_source_catalog ORDER BY local_status, provider").fetchall()]
except sqlite3.OperationalError:
    source_rows = []
if source_rows:
    st.dataframe(pd.DataFrame(source_rows), width="stretch", hide_index=True)
    st.caption("Catalogue rows describe connector readiness only. They do not claim that remote datasets are bundled or downloaded.")

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='internet_research', title='Internet Research Hub', category='Data')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
