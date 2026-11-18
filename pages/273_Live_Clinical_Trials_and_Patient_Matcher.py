from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.services.clinical_trials_service import ClinicalTrialsService
from biointel.ui.theme import apply_theme, hero

st.set_page_config(page_title="Live Clinical Trials & Patient Matcher · BioIntel AI", page_icon=":material/clinical_notes:", layout="wide")
apply_theme()
hero(
    "Live Clinical Trials & Patient Matcher",
    "Search validated ClinicalTrials.gov API v2 records with explicit live, cached, rate-limited, and offline states.",
    eyebrow="Clinical Research · Integration",
    chips=["ClinicalTrials.gov API v2", "NCT validation", "Pagination", "No fabricated fallback trials"],
)
st.session_state.setdefault("clinical_trials_service", ClinicalTrialsService(ROOT))
service: ClinicalTrialsService = st.session_state["clinical_trials_service"]
with st.form("clinical_trials_search", border=False):
    query = st.text_input(
        "Condition, intervention, sponsor, or NCT ID",
        placeholder="Examples: KRAS G12C · glioblastoma · NCT04280705",
    )
    submitted = st.form_submit_button("Search registry", icon=":material/search:", type="primary")
if submitted:
    try:
        with st.spinner("Requesting ClinicalTrials.gov API v2…"):
            st.session_state["clinical_trial_records"] = service.search_trials(query, limit=25)
            st.session_state["clinical_trial_query"] = query
    except ValueError as exc:
        st.error(str(exc))
        st.session_state["clinical_trial_records"] = []
records = st.session_state.get("clinical_trial_records")
if records is not None:
    if service.last_status == "Live ClinicalTrials.gov":
        st.success(f"{service.last_status} · {len(records)} validated records")
    elif service.last_status == "Cached ClinicalTrials.gov":
        st.warning(f"{service.last_status} · {len(records)} records · retrieved {service.last_retrieved_at}")
    else:
        st.error(service.last_status)
    if service.last_error:
        st.caption(f"Provider note: {service.last_error}")
    if not records:
        st.info("No registry records are available for this search. No synthetic trials were created.")
    else:
        rows = [{
            "NCT ID": trial.nct_id,
            "Status": trial.status,
            "Phase": trial.phase,
            "Sponsor": trial.sponsor,
            "Conditions": ", ".join(trial.conditions),
            "Interventions": ", ".join(trial.interventions),
            "Registry Link": trial.url,
        } for trial in records]
        st.dataframe(
            pd.DataFrame(rows),
            hide_index=True,
            column_config={"Registry Link": st.column_config.LinkColumn("Official registry")},
        )
        for trial in records:
            with st.expander(f"{trial.nct_id} · {trial.title}", on_change="rerun"):
                st.caption(f"Status: {trial.status} · Phase: {trial.phase} · Sponsor: {trial.sponsor}")
                st.write(f"**Conditions:** {', '.join(trial.conditions) or 'Not provided'}")
                st.write(f"**Interventions:** {', '.join(trial.interventions) or 'Not provided'}")
                st.link_button("Open official registry entry", trial.url)
    if service.next_page_token and st.button("Load next registry page", icon=":material/navigate_next:"):
        with st.spinner("Loading the next ClinicalTrials.gov page…"):
            more = service.search_trials(
                st.session_state.get("clinical_trial_query", ""),
                limit=25,
                page_token=service.next_page_token,
            )
        existing = {trial.nct_id: trial for trial in st.session_state.get("clinical_trial_records", [])}
        existing.update({trial.nct_id: trial for trial in more})
        st.session_state["clinical_trial_records"] = list(existing.values())
        st.rerun()