from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.integrations.chembl import (
    fetch_chembl_molecule,
    fetch_chembl_target,
)
from biointel.integrations.http_client import ExternalServiceError
from biointel.integrations.uniprot import fetch_uniprot_fasta
from biointel.internet.network_policy import internet_policy_from_environment
from biointel.internet.rcsb import FORMATS, download_rcsb_structure, fetch_rcsb_entry
from biointel.ui.theme import apply_theme, hero
from biointel.utils.runtime_cache import read_csv_cached

st.set_page_config(
    page_title="Scientific Database Lookup · BioIntel AI",
    page_icon="🌐",
    layout="wide",
)

apply_theme()
hero("🌐 Scientific Database Lookup", "Guided scientific analysis with validated inputs, clear status, professional results and export-ready outputs.", eyebrow="BioIntel AI · Scientific Intelligence for Life Sciences")
st.caption(
    "Official RCSB PDB, UniProt and ChEMBL lookup with automatic local caching. "
    "A previous cached response can be used during temporary outages."
)

starter_path = ROOT / "data" / "coverage" / "external_lookup_starters_20.csv"
starter_catalog = read_csv_cached(starter_path) if starter_path.is_file() else pd.DataFrame()

pdb_tab, uniprot_tab, molecule_tab, target_tab = st.tabs(
    ["RCSB PDB", "UniProt protein", "ChEMBL molecule", "ChEMBL target"]
)

with pdb_tab:
    st.subheader("RCSB Protein Data Bank")
    pdb_columns = st.columns([1.4, 1.2, 1])
    pdb_id = pdb_columns[0].text_input(
        "PDB identifier",
        value="4HHB",
        key="external_pdb_id",
    )
    pdb_format = pdb_columns[1].selectbox(
        "Coordinate format",
        list(FORMATS),
        key="external_pdb_format",
    )
    if pdb_columns[2].button(
        "Fetch PDB metadata",
        type="primary",
        width="stretch",
    ):
        try:
            entry = fetch_rcsb_entry(
                pdb_id,
                policy=internet_policy_from_environment(),
            )
        except Exception as exc:
            st.error(str(exc))
        else:
            st.session_state["external_rcsb_entry"] = asdict(entry)
    if st.session_state.get("external_rcsb_entry"):
        entry = st.session_state["external_rcsb_entry"]
        st.markdown(f"### {entry['pdb_id']} · {entry['title']}")
        columns = st.columns(4)
        columns[0].metric(
            "Method",
            ", ".join(entry["experimental_methods"]) or "N/A",
        )
        columns[1].metric(
            "Resolution",
            (
                f"{entry['resolution_angstrom']:.2f} Å"
                if entry["resolution_angstrom"] is not None
                else "N/A"
            ),
        )
        columns[2].metric(
            "Polymer entities",
            entry["polymer_entity_count"] or "N/A",
        )
        columns[3].metric(
            "Atoms",
            f"{entry['deposited_atom_count']:,}" if entry["deposited_atom_count"] else "N/A",
        )
    if st.button("Download PDB structure to workspace", width="stretch"):
        try:
            result, _ = download_rcsb_structure(
                pdb_id,
                FORMATS[pdb_format],
                project_root=ROOT,
                policy=internet_policy_from_environment(),
            )
        except Exception as exc:
            st.error(str(exc))
        else:
            st.success(f"Saved {result.filename} · SHA-256 {result.sha256[:16]}…")
            st.code(result.relative_path, language=None)
    try:
        st.page_link(
            "pages/42_Internet_Research_Hub.py",
            label="Open full Internet Research Hub",
            icon="🌐",
        )
    except (KeyError, RuntimeError):
        st.caption("Open Internet Research Hub from the sidebar.")

with uniprot_tab:
    uniprot_rows = (
        starter_catalog[starter_catalog["database"] == "UniProt"]
        if not starter_catalog.empty
        else pd.DataFrame()
    )
    default_accession = "P69905"
    if not uniprot_rows.empty:
        selected_starter = st.selectbox(
            "Ready UniProt starter",
            uniprot_rows["query_value"].tolist(),
            format_func=lambda value: next(
                (
                    f"{value} · {row.description}"
                    for row in uniprot_rows.itertuples(index=False)
                    if row.query_value == value
                ),
                value,
            ),
        )
        default_accession = selected_starter
    accession = st.text_input(
        "UniProtKB accession",
        value=default_accession,
        help="Example: P69905",
    )
    if st.button("Fetch UniProt FASTA", type="primary"):
        try:
            record = fetch_uniprot_fasta(accession)
        except (ValueError, ExternalServiceError) as exc:
            st.error(str(exc))
        else:
            st.success(f"Retrieved {record.accession}: {len(record.sequence):,} amino acids")
            st.code(f">{record.header}\n{record.sequence}", language=None)
            st.download_button(
                "Download FASTA",
                f">{record.header}\n{record.sequence}\n",
                f"{record.accession}.fasta",
                "text/plain",
            )
            st.session_state["imported_sequence"] = f">{record.header}\n{record.sequence}"
            st.page_link(
                "pages/1_Sequence_Analyzer.py",
                label="Open this sequence in Sequence Analyzer",
                icon="🧬",
            )
            st.caption(
                "Source URL is recorded in the downloaded metadata; "
                "verify accession and reviewed/unreviewed status in UniProt."
            )
            st.download_button(
                "Download lookup metadata",
                json.dumps(asdict(record), indent=2),
                f"{record.accession}_metadata.json",
                "application/json",
            )

with molecule_tab:
    molecule_rows = (
        starter_catalog[starter_catalog["database"] == "ChEMBL molecule"]
        if not starter_catalog.empty
        else pd.DataFrame()
    )
    default_molecule = "CHEMBL25"
    if not molecule_rows.empty:
        default_molecule = st.selectbox(
            "Ready ChEMBL molecule starter",
            molecule_rows["query_value"].tolist(),
            format_func=lambda value: next(
                (
                    f"{value} · {row.description}"
                    for row in molecule_rows.itertuples(index=False)
                    if row.query_value == value
                ),
                value,
            ),
        )
    molecule_id = st.text_input(
        "Molecule ChEMBL ID",
        value=default_molecule,
        help="Example: CHEMBL25",
    )
    if st.button("Fetch ChEMBL molecule", type="primary"):
        try:
            molecule = fetch_chembl_molecule(molecule_id)
        except (ValueError, ExternalServiceError) as exc:
            st.error(str(exc))
        else:
            columns = st.columns(4)
            columns[0].metric("ChEMBL ID", molecule.chembl_id)
            columns[1].metric(
                "Preferred name",
                molecule.preferred_name or "Not provided",
            )
            columns[2].metric(
                "Molecule type",
                molecule.molecule_type or "Not provided",
            )
            columns[3].metric(
                "Max phase",
                molecule.max_phase if molecule.max_phase is not None else "N/A",
            )
            if molecule.canonical_smiles:
                st.code(molecule.canonical_smiles, language=None)
                st.session_state["imported_smiles"] = molecule.canonical_smiles
                st.page_link(
                    "pages/3_Drug_SMILES_Analyzer.py",
                    label="Open this molecule in Drug Analyzer",
                    icon="💊",
                )
            else:
                st.warning("This ChEMBL entry did not provide a canonical SMILES.")
            st.download_button(
                "Download molecule metadata",
                json.dumps(asdict(molecule), indent=2),
                f"{molecule.chembl_id}_molecule.json",
                "application/json",
            )

with target_tab:
    target_rows = (
        starter_catalog[starter_catalog["database"] == "ChEMBL target"]
        if not starter_catalog.empty
        else pd.DataFrame()
    )
    default_target = "CHEMBL204"
    if not target_rows.empty:
        default_target = st.selectbox(
            "Ready ChEMBL target starter",
            target_rows["query_value"].tolist(),
            format_func=lambda value: next(
                (
                    f"{value} · {row.description}"
                    for row in target_rows.itertuples(index=False)
                    if row.query_value == value
                ),
                value,
            ),
        )
    target_id = st.text_input(
        "Target ChEMBL ID",
        value=default_target,
        help="Example: CHEMBL204",
    )
    if st.button("Fetch ChEMBL target", type="primary"):
        try:
            target = fetch_chembl_target(target_id)
        except (ValueError, ExternalServiceError) as exc:
            st.error(str(exc))
        else:
            columns = st.columns(4)
            columns[0].metric("ChEMBL ID", target.chembl_id)
            columns[1].metric(
                "Preferred name",
                target.preferred_name or "Not provided",
            )
            columns[2].metric(
                "Target type",
                target.target_type or "Not provided",
            )
            columns[3].metric(
                "Organism",
                target.organism or "Not provided",
            )
            st.download_button(
                "Download target metadata",
                json.dumps(asdict(target), indent=2),
                f"{target.chembl_id}_target.json",
                "application/json",
            )

st.info("Cache status and cleanup controls are available in System Diagnostics.")

st.info(
    "Remote records can change and may contain multiple forms, assay contexts "
    "or annotations. Store identifiers, access date and provenance with any "
    "dataset you build."
)

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='external_databases', title='Scientific Database Lookup', category='Data')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
