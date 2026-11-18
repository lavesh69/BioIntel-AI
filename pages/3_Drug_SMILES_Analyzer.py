from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.chemistry.common_compounds import (
    DIRECTORY_FILENAME,
    load_common_compound_directory,
    search_common_compounds,
)
from biointel.chemistry.descriptors import calculate_descriptors
from biointel.chemistry.fingerprints import (
    generate_morgan_fingerprint,
)
from biointel.chemistry.medicinal_chemistry import (
    medicinal_chemistry_dict,
    profile_medicinal_chemistry,
)
from biointel.chemistry.molecule_visualization import molecule_png
from biointel.chemistry.similarity_search import (
    compare_molecules,
    greedy_diverse_subset,
    similarity_search,
)
from biointel.chemistry.smiles_validator import (
    validate_smiles,
)
from biointel.chemistry.standardization import standardization_dict, standardize_molecule
from biointel.internet.downloader import InternetDownloadError
from biointel.internet.network_policy import (
    NetworkPolicyError,
    internet_policy_from_environment,
)
from biointel.internet.pubchem import fetch_pubchem_compound_by_name
from biointel.ui.components import smart_dataframe, smart_json
from biointel.ui.workflow import read_uploaded_table, render_upload_preflight
from biointel.ui.theme import (
    apply_theme,
    badge,
    command_bar,
    executive_kpis,
    hero,
    insight_callout,
    section_title,
)
from biointel.utils.exceptions import InvalidSmilesError
from biointel.utils.runtime_cache import read_csv_cached

st.set_page_config(
    page_title="Drug SMILES Analyzer · BioIntel AI",
    page_icon="⚗️",
    layout="wide",
)

apply_theme()

from biointel.ui.scientific_integrations import render_page_integrations as _render_biointel_integrations
_render_biointel_integrations("pages/3_Drug_SMILES_Analyzer.py", key_prefix="3_drug_smiles_analyzer", expanded=False)

# STEP116_MODULE_EXPERIENCE_2_TO_9
from biointel.ui.module_experience_2_9 import render_module_experience as _render_step116_module_experience
_render_step116_module_experience("smiles", key_prefix="step116_3_Drug_SMILES_Analyzer_smiles_1", expanded=False)
policy = internet_policy_from_environment()
directory_path = ROOT / "data" / "chemistry" / DIRECTORY_FILENAME
compound_directory = load_common_compound_directory(ROOT)
coverage_path = ROOT / "data" / "coverage" / "molecule_analysis_library_1000.csv"
coverage_molecules = read_csv_cached(coverage_path) if coverage_path.is_file() else pd.DataFrame()

hero(
    "Search by compound name, resolve SMILES and inspect molecular properties.",
    (
        "Use a bundled 5,000-name compound directory, official PubChem "
        "name lookup, the 1,000-structure coverage library or custom SMILES."
    ),
    eyebrow="Quality-Hardened · Connected Drug SMILES Intelligence",
    chips=[
        "5,000 labelled structures",
        "PubChem online resolver",
        "BioIntel molecular descriptors",
        "Morgan similarity",
    ],
)

badge(
    "● Internet compound lookup enabled" if policy.enabled else "● Offline directory mode",
    "success" if policy.enabled else "warning",
)

curated_count = int((compound_directory["name_type"] == "curated_common_name").sum())
executive_kpis(
    [
        (
            "Compound names",
            f"{len(compound_directory):,}",
            "Curated common and clearly labelled registry names",
        ),
        (
            "Curated common",
            f"{curated_count:,}",
            "Known names with aliases",
        ),
        (
            "Unique structures",
            f"{compound_directory['canonical_smiles'].nunique():,}",
            "Canonical BioIntel-validated SMILES",
        ),
        (
            "Online fallback",
            "PubChem",
            "Official name-to-structure lookup",
        ),
    ]
)

selection_tab, analysis_tab, compare_tab, library_tab = st.tabs(
    [
        "Compound Selection",
        "Molecular Analysis",
        "Pair Comparison",
        "Library Similarity Search",
    ]
)

selected_metadata: dict[str, object] = {}
default_smiles = st.session_state.pop(
    "imported_smiles",
    "",
)
incoming_smiles = default_smiles
source_signature = "custom"

with selection_tab:
    command_bar(
        "Compound source and provenance",
        (
            "Choose a bundled directory entry, resolve a name online or "
            "paste a custom structure. Every source remains clearly labelled."
        ),
    )
    source = st.radio(
        "Molecule source",
        [
            "5,000-record molecular structure directory",
            "PubChem online name lookup",
            "Coverage molecule library — 1,000 structures",
            "Common examples",
            "Custom SMILES",
        ],
        horizontal=True,
        index=4 if incoming_smiles else 0,
    )

    examples = {
        "Aspirin": "CC(=O)OC1=CC=CC=C1C(=O)O",
        "Caffeine": "Cn1c(=O)c2c(ncn2C)n(C)c1=O",
        "Ibuprofen": "CC(C)CC1=CC=C(C=C1)C(C)C(=O)O",
        "Paracetamol": "CC(=O)NC1=CC=C(C=C1)O",
    }

    if source == "5,000-record molecular structure directory":
        filters = st.columns([2.3, 1.2, 1])
        query = filters[0].text_input(
            "Search common name, alias, identifier or formula",
            value="Aspirin",
            key="compound_directory_query",
        )
        name_type_labels = {
            "all": "All names",
            "curated_common_name": "Curated common names",
            "registry_screening_name": "NCI registry names",
            "reference_registry_name": "BioIntel reference names",
        }
        name_type = filters[1].selectbox(
            "Name class",
            list(name_type_labels),
            format_func=lambda value: name_type_labels[value],
        )
        result_limit = filters[2].selectbox(
            "Result limit",
            [25, 50, 100, 250, 500],
            index=2,
        )
        matches = search_common_compounds(
            compound_directory,
            query,
            name_type=name_type,
            limit=result_limit,
        )
        st.caption(f"{len(matches):,} matching record(s) from the 5,000-name directory")
        if matches.empty:
            st.warning("No local match. Try a broader search or use PubChem online lookup.")
        else:
            labels = {
                (
                    f"{row.common_name} · {row.molecular_formula} · "
                    f"MW {float(row.molecular_weight):.1f}"
                ): row.compound_key
                for row in matches.itertuples(index=False)
            }
            selected_label = st.selectbox(
                "Select compound",
                list(labels),
            )
            selected_key = labels[selected_label]
            selected_row = matches.loc[matches["compound_key"] == selected_key].iloc[0]
            default_smiles = str(selected_row["canonical_smiles"])
            selected_metadata = selected_row.to_dict()
            source_signature = f"directory:{selected_key}:" f"{default_smiles}"
            info = st.columns(4)
            info[0].metric(
                "Name source",
                str(selected_row["name_type"])
                .replace(
                    "_",
                    " ",
                )
                .title(),
            )
            info[1].metric(
                "Formula",
                str(selected_row["molecular_formula"]),
            )
            info[2].metric(
                "Molecular weight",
                f"{float(selected_row['molecular_weight']):.2f}",
            )
            info[3].metric(
                "Lipinski violations",
                int(selected_row["lipinski_violations"]),
            )
            st.caption(f"Aliases: {selected_row['aliases']} · " f"Source: {selected_row['source']}")
            if selected_row["name_type"] != "curated_common_name":
                st.info(
                    "This is a registry/screening name, not a claim that the "
                    "compound is an approved medicine or has a widely used common name."
                )
            st.download_button(
                "Download complete 5,000-name directory",
                directory_path.read_bytes(),
                directory_path.name,
                "text/csv",
            )

    elif source == "PubChem online name lookup":
        command_bar(
            "Official PubChem name resolver",
            (
                "Enter a common, generic, brand-independent or systematic name. "
                "The returned record is used only after explicit lookup."
            ),
        )
        controls = st.columns([3, 1])
        pubchem_query = controls[0].text_input(
            "Compound or drug name",
            value="amoxicillin",
            key="pubchem_name_query",
        )
        lookup_clicked = controls[1].button(
            "Resolve with PubChem",
            type="primary",
            width="stretch",
        )
        normalized_pubchem_query = pubchem_query.strip().casefold()
        if st.session_state.get("pubchem_compound_query") != normalized_pubchem_query:
            st.session_state.pop("pubchem_compound_result", None)
        if lookup_clicked:
            try:
                result = fetch_pubchem_compound_by_name(
                    pubchem_query,
                    policy=policy,
                )
            except (
                ValueError,
                NetworkPolicyError,
                InternetDownloadError,
            ) as exc:
                st.error(str(exc))
            else:
                st.session_state["pubchem_compound_result"] = asdict(result)
                st.session_state["pubchem_compound_query"] = normalized_pubchem_query

        pubchem_result = st.session_state.get("pubchem_compound_result")
        if pubchem_result:
            default_smiles = str(pubchem_result["canonical_smiles"])
            selected_metadata = {
                **pubchem_result,
                "name_type": "pubchem_online_name",
                "source": "PubChem PUG REST",
            }
            source_signature = f"pubchem:{pubchem_result['cid']}:" f"{default_smiles}"
            st.markdown(f"### {pubchem_result['title']} · CID {pubchem_result['cid']}")
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
            if pubchem_result.get("iupac_name"):
                st.caption(f"IUPAC: {pubchem_result['iupac_name']}")
            st.caption(
                "Source: official PubChem PUG REST response. "
                "Internet lookup does not establish approval, safety or efficacy."
            )

    elif source == "Coverage molecule library — 1,000 structures":
        if coverage_molecules.empty:
            st.error("Coverage molecule library is missing.")
        else:
            selected_drug = st.selectbox(
                "Library molecule",
                coverage_molecules["drug_id"].tolist(),
                format_func=lambda value: next(
                    (
                        f"{value} · MW {float(row.molecular_weight):.1f} · "
                        f"LogP {float(row.logp):.2f}"
                        for row in coverage_molecules.itertuples(index=False)
                        if row.drug_id == value
                    ),
                    value,
                ),
            )
            selected_row = coverage_molecules.loc[
                coverage_molecules["drug_id"] == selected_drug
            ].iloc[0]
            default_smiles = str(selected_row["canonical_smiles"])
            selected_metadata = {
                **selected_row.to_dict(),
                "name_type": "coverage_library",
                "source": "BioIntel coverage library",
            }
            source_signature = f"coverage:{selected_drug}:{default_smiles}"

    elif source == "Common examples":
        example = st.selectbox(
            "Example molecule",
            list(examples),
        )
        default_smiles = examples[example]
        selected_metadata = {
            "common_name": example,
            "name_type": "built_in_example",
            "source": "BioIntel example set",
        }
        source_signature = f"example:{example}:{default_smiles}"

    if st.session_state.get("_drug_source_signature") != source_signature:
        st.session_state["drug_smiles_input"] = default_smiles
        st.session_state["_drug_source_signature"] = source_signature

    smiles = st.text_input(
        "Drug SMILES",
        key="drug_smiles_input",
        placeholder="Enter a valid SMILES string",
    )

    with st.expander("Fingerprint settings"):
        radius = st.number_input(
            "Morgan radius",
            min_value=0,
            max_value=5,
            value=2,
        )
        n_bits = st.selectbox(
            "Fingerprint length",
            [256, 512, 1024, 2048, 4096],
            index=3,
        )
        use_chirality = st.checkbox(
            "Use chirality",
            value=True,
        )

if not st.session_state.get("drug_smiles_input", "").strip():
    with analysis_tab:
        insight_callout(
            "Choose a compound to begin",
            (
                "Search the local directory, resolve a name through "
                "PubChem or enter custom SMILES."
            ),
            "⚗️",
        )
    st.stop()

smiles = st.session_state["drug_smiles_input"]
try:
    validation = validate_smiles(smiles)
    mol, standardization = standardize_molecule(smiles)
    descriptors = calculate_descriptors(mol)
    medchem = profile_medicinal_chemistry(mol)
    fingerprint = generate_morgan_fingerprint(
        mol,
        int(radius),
        int(n_bits),
        use_chirality,
    )
except InvalidSmilesError as exc:
    with analysis_tab:
        st.error(str(exc))
    st.stop()
except Exception as exc:
    with analysis_tab:
        st.error(f"Molecular analysis failed: {exc}")
    st.stop()

with analysis_tab:
    command_bar(
        "BioIntel molecular analysis",
        (
            "Canonicalize the selected structure, calculate descriptors "
            "and generate a configurable Morgan fingerprint."
        ),
    )
    left, right = st.columns([1, 1.35])
    with left:
        st.image(
            molecule_png(mol),
            caption=standardization.standardized_smiles,
            width="stretch",
        )
    with right:
        metrics = st.columns(4)
        metrics[0].metric(
            "Molecular weight",
            f"{descriptors['molecular_weight']:.2f}",
        )
        metrics[1].metric(
            "LogP",
            f"{descriptors['logp']:.2f}",
        )
        metrics[2].metric(
            "TPSA",
            f"{descriptors['tpsa']:.2f} Å²",
        )
        metrics[3].metric(
            "Lipinski violations",
            descriptors["lipinski_violations"],
        )
        st.code(
            standardization.standardized_smiles,
            language=None,
        )
        st.write(f"Submitted atoms: **{validation.atom_count}** · Submitted bonds: **{validation.bond_count}**")
        st.caption(f"Standardized InChIKey: {standardization.inchikey or 'Unavailable'}")
        if selected_metadata:
            with st.expander("Compound source and selected-name metadata"):
                smart_json(selected_metadata)

    section_title("Standardized parent structure", "🧼")
    smart_dataframe(
        [
            {"Stage": "Submitted", "SMILES": standardization.original_smiles},
            {"Stage": "Parsed canonical", "SMILES": standardization.parsed_canonical_smiles},
            {"Stage": "Parent fragment", "SMILES": standardization.parent_smiles},
            {"Stage": "Final standardized", "SMILES": standardization.standardized_smiles},
        ],
        height=230,
    )
    st.caption("Transformations: " + " · ".join(standardization.transformations))
    for warning in standardization.warnings:
        st.warning(warning)

    medchem_metrics = st.columns(4)
    medchem_metrics[0].metric("QED", f"{medchem.qed:.3f}")
    medchem_metrics[1].metric("SA complexity heuristic", f"{medchem.synthetic_accessibility_heuristic:.2f}/10")
    medchem_metrics[2].metric("ESOL-style logS", f"{medchem.esol_style_log_s:.2f}")
    medchem_metrics[3].metric("Murcko scaffold", "Present" if medchem.scaffold_smiles else "Acyclic")

    rows = [
        {
            "Descriptor": key,
            "Value": value,
        }
        for key, value in descriptors.items()
        if key not in {"lipinski_rules"}
    ]
    section_title("Molecular descriptors", "◈")
    st.dataframe(
        pd.DataFrame(rows),
        width="stretch",
        hide_index=True,
    )

    rules_df = pd.DataFrame(
        [
            {
                "Rule": item.name,
                "Status": "PASS" if item.passed else "REVIEW",
                "Failed criteria": "; ".join(item.failed_criteria) if item.failed_criteria else "—",
                "Interpretation": item.interpretation,
            }
            for item in medchem.rules
        ]
    )
    section_title("Medicinal-chemistry rule scorecard", "✓")
    smart_dataframe(rules_df, height=430)
    if medchem.alerts:
        section_title("PAINS, Brenk, NIH and ZINC filter matches", "⚠")
        smart_dataframe(
            [
                {
                    "Catalog": item.catalog,
                    "Description": item.description,
                    "Matched atoms": item.atom_indices,
                }
                for item in medchem.alerts
            ],
            height=360,
        )
    else:
        st.success("No PAINS, Brenk, NIH or ZINC catalog match detected.")
    st.warning("Property rules and catalog filters do not establish safety, efficacy, approval or actual bioactivity.")

    section_title("Morgan fingerprint", "◎")
    fp_cols = st.columns(3)
    fp_cols[0].metric("Bits", fingerprint.n_bits)
    fp_cols[1].metric(
        "Active bits",
        fingerprint.on_bits,
    )
    fp_cols[2].metric(
        "Bit density",
        f"{fingerprint.density:.4f}",
    )
    active_indices = [int(index) for index in fingerprint.values.nonzero()[0]]
    active_df = pd.DataFrame({"Active bit index": active_indices})
    if not active_df.empty:
        st.plotly_chart(
            px.histogram(
                active_df,
                x="Active bit index",
                nbins=min(60, int(n_bits) // 8),
                title="Active fingerprint bits",
            ),
            width="stretch",
        )

with compare_tab:
    command_bar(
        "Molecular similarity comparison",
        (
            "Choose a second directory entry or paste SMILES to calculate "
            "Tanimoto similarity using the same fingerprint settings."
        ),
    )
    compare_source = st.radio(
        "Second molecule source",
        [
            "5,000-record directory",
            "Coverage library",
            "Custom SMILES",
        ],
        horizontal=True,
    )
    second_default = ""
    second_label = "Custom molecule"
    if compare_source == "5,000-record directory":
        second_query = st.text_input(
            "Search second compound",
            value="Caffeine",
            key="second_common_name_query",
        )
        second_matches = search_common_compounds(
            compound_directory,
            second_query,
            limit=100,
        )
        if not second_matches.empty:
            labels = {
                f"{row.common_name} · {row.molecular_formula}": row.compound_key
                for row in second_matches.itertuples(index=False)
            }
            second_label = st.selectbox(
                "Second compound",
                list(labels),
            )
            key = labels[second_label]
            second_default = str(
                second_matches.loc[
                    second_matches["compound_key"] == key,
                    "canonical_smiles",
                ].iloc[0]
            )
    elif compare_source == "Coverage library" and not coverage_molecules.empty:
        second_drug = st.selectbox(
            "Second coverage molecule",
            coverage_molecules["drug_id"].tolist(),
        )
        second_label = str(second_drug)
        second_default = str(
            coverage_molecules.loc[
                coverage_molecules["drug_id"] == second_drug,
                "canonical_smiles",
            ].iloc[0]
        )

    second_signature = f"{compare_source}:{second_label}:{second_default}"
    if st.session_state.get("_second_source_signature") != second_signature:
        st.session_state["second_smiles_input"] = second_default
        st.session_state["_second_source_signature"] = second_signature

    second_smiles = st.text_input(
        "Second SMILES",
        key="second_smiles_input",
    )
    if second_smiles.strip():
        try:
            second_mol, second_standardization = standardize_molecule(second_smiles)
            pair = compare_molecules(
                standardization.standardized_smiles,
                second_standardization.standardized_smiles,
                radius=int(radius),
                n_bits=int(n_bits),
            )
            comparison = st.columns([1, 1, 1])
            comparison[0].image(
                molecule_png(mol),
                caption="Primary standardized molecule",
                width="stretch",
            )
            with comparison[1]:
                st.metric("Tanimoto similarity", f"{pair.tanimoto:.4f}")
                st.metric("Same Murcko scaffold", "Yes" if pair.same_scaffold else "No")
                st.metric("MCS atoms", pair.mcs_atoms)
                if pair.timed_out:
                    st.warning("Maximum-common-substructure search timed out.")
            comparison[2].image(
                molecule_png(second_mol),
                caption=f"{second_label} · standardized",
                width="stretch",
            )
            smart_dataframe(
                [
                    {"Metric": "Primary scaffold", "Value": pair.first_scaffold or "Acyclic"},
                    {"Metric": "Second scaffold", "Value": pair.second_scaffold or "Acyclic"},
                    {"Metric": "MCS SMARTS", "Value": pair.mcs_smarts or "Unavailable"},
                    {"Metric": "MCS bonds", "Value": pair.mcs_bonds},
                ],
                height=230,
            )
        except Exception as exc:
            st.error(f"Pair comparison failed: {exc}")

with library_tab:
    command_bar(
        "Batch similarity, scaffold matching and diversity selection",
        "Search the bundled molecular libraries or an uploaded CSV. Structures are standardized before fingerprinting, exact duplicates are labelled and invalid rows are exportable.",
    )
    library_source = st.radio(
        "Search library",
        ["Coverage library — 1,000", "Compound directory — 5,000", "Upload CSV"],
        horizontal=True,
        key="similarity_library_source",
    )
    search_frame = pd.DataFrame()
    search_name_column = "name"
    search_smiles_column = "smiles"
    if library_source == "Coverage library — 1,000":
        if not coverage_molecules.empty:
            search_frame = coverage_molecules.rename(columns={"drug_id": "name", "canonical_smiles": "smiles"})
    elif library_source == "Compound directory — 5,000":
        search_frame = compound_directory.rename(columns={"common_name": "name", "canonical_smiles": "smiles"})
    else:
        similarity_upload = st.file_uploader("Compound table with ID/name and SMILES", type=["csv", "tsv", "xlsx", "xlsm", "zip"], key="similarity_upload")
        render_upload_preflight(similarity_upload, key="similarity_library", allowed_extensions=["csv", "tsv", "xlsx", "xlsm", "zip"], soft_limit_mb=30, hard_limit_mb=250)
        if similarity_upload is not None:
            try:
                search_frame = read_uploaded_table(similarity_upload)
            except Exception as exc:
                st.error(f"Could not read similarity library: {exc}")
        if not search_frame.empty:
            mapping = st.columns(2)
            search_name_column = mapping[0].selectbox("Name/ID column", list(search_frame.columns), key="sim_name_col")
            search_smiles_column = mapping[1].selectbox("SMILES column", list(search_frame.columns), index=min(1, len(search_frame.columns)-1), key="sim_smiles_col")

    if search_frame.empty:
        st.info("Choose a populated library or upload a CSV to run similarity search.")
    else:
        controls = st.columns(3)
        top_n = controls[0].slider("Top matches", 5, 100, 20)
        max_library_rows = controls[1].number_input("Maximum library rows", 1, len(search_frame), min(1000, len(search_frame)))
        diverse_size = controls[2].slider("Diverse subset size", 2, min(50, max(2, int(top_n))), min(10, max(2, int(top_n))))
        if search_name_column == search_smiles_column:
            st.error("Name/ID and SMILES columns must be different.")
        if st.button("Search molecular library", type="primary", width="stretch", disabled=search_name_column == search_smiles_column):
            try:
                prepared = search_frame.head(int(max_library_rows))
                hits, failures = similarity_search(
                    standardization.standardized_smiles,
                    prepared,
                    smiles_column=search_smiles_column,
                    name_column=search_name_column,
                    top_n=int(top_n),
                    radius=int(radius),
                    n_bits=int(n_bits),
                )
                st.session_state["similarity_hits"] = hits
                st.session_state["similarity_failures"] = failures
            except Exception as exc:
                st.error(f"Library search failed: {exc}")

        hits = st.session_state.get("similarity_hits")
        failures = st.session_state.get("similarity_failures")
        if isinstance(hits, pd.DataFrame) and not hits.empty:
            smart_dataframe(hits, height=540)
            st.plotly_chart(
                px.bar(hits.sort_values("tanimoto"), x="tanimoto", y="name", orientation="h", title="Top standardized-structure similarities"),
                width="stretch",
            )
            diverse = greedy_diverse_subset(hits, size=int(diverse_size))
            with st.expander("Greedy diverse subset", expanded=False):
                smart_dataframe(diverse, height=360)
            downloads = st.columns(3)
            downloads[0].download_button("Download similarity hits", hits.to_csv(index=False), "similarity_hits.csv", "text/csv", width="stretch")
            downloads[1].download_button("Download diverse subset", diverse.to_csv(index=False), "diverse_subset.csv", "text/csv", width="stretch")
            if isinstance(failures, pd.DataFrame) and not failures.empty:
                downloads[2].download_button("Download invalid rows", failures.to_csv(index=False), "similarity_failures.csv", "text/csv", width="stretch")
                st.warning(f"{len(failures):,} library row(s) could not be standardized.")
            else:
                downloads[2].success("No invalid library rows.")

export = {
    "selected_source_metadata": selected_metadata,
    "canonical_smiles": standardization.standardized_smiles,
    "atom_count": validation.atom_count,
    "bond_count": validation.bond_count,
    "descriptors": descriptors,
    "standardization": standardization_dict(standardization),
    "medicinal_chemistry": medicinal_chemistry_dict(medchem),
    "fingerprint": {
        "radius": fingerprint.radius,
        "n_bits": fingerprint.n_bits,
        "use_chirality": fingerprint.use_chirality,
        "active_bits": [int(index) for index in fingerprint.values.nonzero()[0]],
    },
}
section_title("Connected discovery handoff", "↗")
handoff = st.columns(3)
if handoff[0].button("Send to ADMET triage", width="stretch"):
    st.session_state["admet_smiles"] = standardization.standardized_smiles
    st.switch_page("pages/62_ADMET_Drug_Discovery.py")
if handoff[1].button("Send to DTI Feature Builder", width="stretch"):
    st.session_state["dti_smiles"] = standardization.standardized_smiles
    st.switch_page("pages/4_DTI_Feature_Builder.py")
if handoff[2].button("Open Discovery Command Center", width="stretch"):
    st.session_state["discovery_smiles"] = standardization.standardized_smiles
    st.switch_page("pages/88_Discovery_Command_Center.py")

section_title("Research export", "📥")
exports = st.columns(2)
exports[0].download_button(
    "Download molecule JSON",
    json.dumps(export, indent=2, default=str),
    "molecule_analysis.json",
    "application/json",
    width="stretch",
)
exports[1].download_button(
    "Download molecule PNG",
    molecule_png(mol),
    "molecule.png",
    "image/png",
    width="stretch",
)
st.caption("Research and educational use only. Experimental validation is required.")

# STEP127_SCIENTIFIC_DEPTH_DRUG_SMILES
from biointel.step127.ui import render_step127_upgrade_panel as _render_step127_upgrade_panel
_render_step127_upgrade_panel('drug_smiles', expanded=False)

# Targeted peak-potential assurance for Genomics, Discovery, Omics, Lab and Translational modules.
from biointel.peak_potential.ui import render_peak_session_footer
render_peak_session_footer(page_key='drug_analyzer', title='Drug SMILES Analyzer', category='Discovery')

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='drug_analyzer', title='Drug SMILES Analyzer', category='Discovery')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
