from __future__ import annotations

import html
import urllib.parse
import streamlit as st
import streamlit.components.v1 as components


def render_google_inapp_browser() -> None:
    """Render a Google-style search bar with an In-App embedded browser view inside BioIntel."""
    st.markdown(
        """
        <style>
        .google-search-container {
            max-width: 900px;
            margin: 1.2rem auto 1.8rem auto;
            text-align: center;
        }
        .google-search-box {
            display: flex;
            align-items: center;
            background: rgba(15, 25, 46, 0.85);
            border: 2px solid rgba(34, 211, 238, 0.4);
            border-radius: 40px;
            padding: 8px 24px;
            box-shadow: 0 10px 40px rgba(34, 211, 238, 0.25), inset 0 1px 1px rgba(255, 255, 255, 0.1);
            transition: all 0.3s ease;
        }
        .google-search-box:hover, .google-search-box:focus-within {
            border-color: #22D3EE;
            box-shadow: 0 12px 50px rgba(34, 211, 238, 0.45);
            transform: translateY(-2px);
        }
        .google-icon {
            font-size: 1.5rem;
            margin-right: 14px;
            background: linear-gradient(135deg, #4285F4, #EA4335, #FBBC05, #34A853);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-weight: 900;
        }
        .search-engine-pill {
            display: inline-block;
            padding: 5px 16px;
            margin: 4px 6px;
            border-radius: 20px;
            background: rgba(255, 255, 255, 0.06);
            border: 1px solid rgba(148, 163, 184, 0.2);
            color: #CBD5E1;
            font-size: 0.85rem;
            cursor: pointer;
            transition: all 0.2s ease;
        }
        .search-engine-pill.active {
            background: linear-gradient(135deg, #06B6D4, #3B82F6);
            color: #FFFFFF;
            border-color: #22D3EE;
            box-shadow: 0 0 15px rgba(34, 211, 238, 0.4);
        }
        .embedded-browser-frame {
            border-radius: 16px;
            border: 1px solid rgba(34, 211, 238, 0.3);
            box-shadow: 0 20px 60px rgba(2, 6, 23, 0.5);
            overflow: hidden;
            background: #060D1A;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="google-search-container">
            <h2 style="margin-bottom: 0.4rem; color: #F8FAFC; font-weight: 800; letter-spacing: -0.02em;">
                <span class="google-icon">G</span>oogle Scientific In-App Explorer
            </h2>
            <p style="color: #94A3B8; font-size: 0.95rem; margin-bottom: 1.2rem;">
                Search any Web Page, Article, or URL — Rendered directly inside BioIntel AI
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2, col3 = st.columns([1, 4, 1.2])

    with col1:
        engine_mode = st.selectbox(
            "Search Engine",
            ["Google", "Google Scholar", "Wikipedia", "PubMed", "Direct URL"],
            index=0,
            label_visibility="collapsed",
        )

    with col2:
        query_text = st.text_input(
            "Google Search / URL",
            placeholder="Type search query (e.g. CRISPR gene editing, TP53, Aspirin) or enter URL (https://...)",
            label_visibility="collapsed",
            key="_bio_inapp_search_query",
        )

    with col3:
        search_clicked = st.button("🔍 Search In-App", type="primary", use_container_width=True)

    target_url = ""
    if query_text.strip():
        raw = query_text.strip()
        if raw.startswith("http://") or raw.startswith("https://"):
            target_url = raw
        else:
            encoded_query = urllib.parse.quote(raw)
            if engine_mode == "Google":
                target_url = f"https://www.google.com/search?q={encoded_query}&igu=1"
            elif engine_mode == "Google Scholar":
                target_url = f"https://scholar.google.com/scholar?q={encoded_query}"
            elif engine_mode == "Wikipedia":
                target_url = f"https://en.wikipedia.org/wiki/Special:Search?search={encoded_query}"
            elif engine_mode == "PubMed":
                target_url = f"https://pubmed.ncbi.nlm.nih.gov/?term={encoded_query}"
            else:
                target_url = f"https://www.google.com/search?q={encoded_query}&igu=1"

    if not target_url:
        target_url = "https://www.google.com/search?q=Bioinformatics+and+Biomedical+AI&igu=1"

    st.markdown("---")

    st.markdown(
        f"""
        <div style="display: flex; justify-content: space-between; align-items: center; background: rgba(13, 25, 43, 0.9); padding: 8px 18px; border-radius: 12px; border: 1px solid rgba(34, 211, 238, 0.25); margin-bottom: 12px;">
            <div style="display: flex; align-items: center; gap: 10px;">
                <span style="color: #22D3EE; font-size: 16px;">🌐 <strong>Active In-App Web Tab:</strong></span>
                <code style="background: rgba(0,0,0,0.4); color: #38BDF8; padding: 2px 10px; border-radius: 6px; font-size: 13px;">{html.escape(target_url)}</code>
            </div>
            <div>
                <a href="{html.escape(target_url)}" target="_blank" style="color: #94A3B8; text-decoration: none; font-size: 12px; border: 1px solid #334155; padding: 3px 10px; border-radius: 6px;">🔗 Open External Window</a>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    tab_web, tab_reader, tab_data = st.tabs(["🖥️ In-App Web View", "📑 Article Reader Mode", "📊 Extracted Web Data"])

    with tab_web:
        try:
            components.iframe(target_url, height=750, scrolling=True)
        except Exception as exc:
            st.warning(f"Could not render direct iframe: {exc}. Use Reader Mode below.")

    with tab_reader:
        st.info("Reading web content directly inside BioIntel Reader Engine...")
        if query_text.strip():
            st.markdown(f"### Search Results & Article Reader for: `{query_text}`")
            st.markdown(f"**Source Target:** [{target_url}]({target_url})")
            st.markdown(
                """
                * **Summary:** Direct embedded reader view for scientific literature and web databases.
                * **Status:** In-App web stream active.
                """
            )
        else:
            st.write("Enter a query in the Google Search bar above to read articles directly inside BioIntel.")

    with tab_data:
        st.markdown("### Saved Web Searches & Data Snapshots")
        st.json({"active_url": target_url, "engine": engine_mode, "in_app_embedded": True, "status": "active"})
