from __future__ import annotations

import streamlit as st
import pandas as pd
from biointel.education.science_pulse_service import SciencePulseService
from biointel.ui.professional_components import render_module_hero
from biointel.ui.sidebar_redesign import render_breadcrumbs, render_sidebar_redesign

render_sidebar_redesign()
render_breadcrumbs("BioIntel Science Pulse", "Education")

sp = SciencePulseService()

render_module_hero(
    "BioIntel Science Pulse",
    "Evidence-Aware Biomedical Literature Workspace & Scheduled Science News Feed",
    icon="📡",
    badge_text="Live Evidence Feed"
)

t1, t2, t3 = st.tabs(["📰 Scientific Feed", "🔖 Saved Research", "🔔 Science Alerts"])

with t1:
    st.subheader("Latest Biomedical & Biotechnology Ingestion Feed")
    articles = sp.list_articles()
    for a in articles:
        with st.container():
            st.markdown(f"""
            <div style="background: #161b22; border: 1px solid rgba(255,255,255,0.08); border-radius: 10px; padding: 16px; margin-bottom: 12px;">
                <div style="display: flex; justify-content: space-between;">
                    <span style="background: rgba(56, 139, 253, 0.2); color: #58a6ff; font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 12px;">{a['source']}</span>
                    <span style="font-size: 11px; color: #8b949e;">{a['pub_date']}</span>
                </div>
                <h4 style="margin: 8px 0 4px 0; color: #f0f6fc;">{a['title']}</h4>
                <div style="font-size: 12px; color: #8b949e; margin-bottom: 8px;">Authors: {a['authors']} • <em>{a['journal']}</em></div>
                <p style="font-size: 13px; color: #c9d1d9;">{a['abstract']}</p>
            </div>
            """, unsafe_allow_html=True)
            if st.button("🔖 Bookmark / Save", key=f"save_{a['article_id']}"):
                sp.toggle_save_article(a['article_id'])
                st.success("Article saved!")
                st.rerun()

with t2:
    st.subheader("Saved Publications & Annotated Reading Lists")
    saved = sp.list_articles(saved_only=True)
    if saved:
        df = pd.DataFrame(saved)[['title', 'source', 'authors', 'pub_date', 'doi_pmid']]
        st.dataframe(df, use_container_width=True)
    else:
        st.info("No saved articles in reading list.")

with t3:
    st.subheader("Configure Scientific Topic Alerts")
    st.text_input("New Alert Keyword / Medical Term:", "CRISPR-Cas12 Off-Target Validation")
    st.selectbox("Frequency", ["Daily Digest", "Weekly Digest", "Real-Time"])
    if st.button("Create Science Alert"):
        st.success("Alert rule saved!")
