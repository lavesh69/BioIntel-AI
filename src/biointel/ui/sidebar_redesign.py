from __future__ import annotations

import streamlit as st
from typing import Dict, List, Any, Optional

CANONICAL_GROUPS = [
    ("Start", "🚀", ["home", "quick_start", "workflow_dashboard"]),
    ("BioIntel Connect", "🌐", ["biointel_connect"]),
    ("Shiro AI", "🤖", ["shiro_ai_studio"]),
    ("Education", "🎓", [
        "biointel_education_home", "biointel_classroom", "biointel_science_pulse",
        "biointel_academy_lecture_studio", "biointel_examination_command", "education_intelligence_hub",
        "adaptive_learning", "virtual_science_lab", "bioinformatics_sandbox", "shiro_tutor",
        "learning_analytics", "digital_library", "student_research_hub", "competition_center",
        "career_hub", "academic_portfolio", "lab_management", "question_bank",
        "lecture_intelligence", "academic_erp", "gamified_learning", "teaching_support",
        "offline_learning", "open_science", "collaboration_network", "safety_moderation"
    ]),
    ("Research", "🔬", [
        "sequence_analyzer", "sequence_comparison", "drug_analyzer", "pangenome_graph",
        "long_read_assembly", "protein_design_lab", "crispr_perturbseq", "pathogen_outbreak",
        "synthetic_biology_designer", "rare_disease_board", "knowledge_graph_copilot",
        "multiomics_biomarker"
    ]),
    ("Studio", "✨", ["biointel_studio", "visual_workflow_builder", "scientific_execution_quality"]),
    ("Administration", "🏛️", ["local_data", "backup_restore", "installation_recovery", "external_model_qualification"]),
    ("Settings", "⚙️", ["diagnostics", "reliability_optimization", "windows_ui_regression_performance"])
]

def apply_sidebar_custom_css():
    st.markdown("""
    <style>
    /* Premium Sidebar Layout and 340px Fixed Width */
    [data-testid="stSidebar"] {
        min-width: 320px !important;
        max-width: 360px !important;
        width: 340px !important;
        background: linear-gradient(180deg, #0d1117 0%, #161b22 100%) !important;
        border-right: 1px solid rgba(255, 255, 255, 0.08) !important;
    }
    
    /* Navigation Group Header Styling */
    .bio-nav-group-header {
        font-size: 13px;
        font-weight: 700;
        letter-spacing: 0.8px;
        text-transform: uppercase;
        color: #8b949e;
        margin-top: 16px;
        margin-bottom: 6px;
        padding-left: 8px;
        display: flex;
        align-items: center;
        gap: 8px;
    }

    /* Module Navigation Button Override */
    [data-testid="stSidebar"] .stButton button {
        width: 100% !important;
        text-align: left !important;
        justify-content: flex-start !important;
        border-radius: 8px !important;
        border: 1px solid transparent !important;
        background: transparent !important;
        color: #c9d1d9 !important;
        padding: 8px 12px !important;
        font-size: 14px !important;
        font-weight: 500 !important;
        transition: all 0.15s ease-in-out !important;
    }

    [data-testid="stSidebar"] .stButton button:hover {
        background: rgba(56, 139, 253, 0.15) !important;
        border-color: rgba(56, 139, 253, 0.4) !important;
        color: #58a6ff !important;
    }

    /* Active Highlight */
    [data-testid="stSidebar"] .bio-nav-active button {
        background: linear-gradient(90deg, #1f6feb 0%, #238636 100%) !important;
        color: #ffffff !important;
        font-weight: 600 !important;
        box-shadow: 0 4px 12px rgba(31, 111, 235, 0.3) !important;
    }

    /* Breadcrumbs Bar */
    .bio-breadcrumb-bar {
        padding: 8px 16px;
        background: rgba(22, 27, 34, 0.8);
        border-bottom: 1px solid rgba(255,255,255,0.05);
        font-size: 13px;
        color: #8b949e;
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 16px;
    }
    .bio-breadcrumb-bar a {
        color: #58a6ff;
        text-decoration: none;
    }
    </style>
    """, unsafe_allow_html=True)

def render_breadcrumbs(current_page_title: str, category_name: str = "Start"):
    st.markdown(f"""
    <div class="bio-breadcrumb-bar">
        <span>🏠 Home</span> &gt;
        <span>{category_name}</span> &gt;
        <strong style="color: #f0f6fc;">{current_page_title}</strong>
    </div>
    """, unsafe_allow_html=True)

def render_sidebar_redesign():
    apply_sidebar_custom_css()
    
    with st.sidebar:
        st.markdown("""
        <div style="padding: 12px 8px 16px 8px; text-align: left; border-bottom: 1px solid rgba(255,255,255,0.08);">
            <div style="font-size: 20px; font-weight: 800; color: #58a6ff; display: flex; align-items: center; gap: 8px;">
                <span>🧬</span> BioIntel AI
            </div>
            <div style="font-size: 11px; color: #8b949e; margin-top: 2px;">
                Step220 V20.5 • Biology, Engineered into Intelligence
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Quick Search Bar
        search_query = st.text_input("🔍 Search modules...", key="sidebar_search_input", label_visibility="collapsed")
        
        if search_query:
            st.caption(f"Search results for '{search_query}':")
        
        current_page = st.session_state.get("_active_page_key", "home")

        for group_name, icon, page_keys in CANONICAL_GROUPS:
            with st.expander(f"{icon} {group_name}", expanded=True):
                for pkey in page_keys:
                    # Render friendly label
                    label = pkey.replace("_", " ").title()
                    is_active = (pkey == current_page)
                    btn_class = "bio-nav-active" if is_active else ""
                    
                    if btn_class:
                        st.markdown(f'<div class="{btn_class}">', unsafe_allow_html=True)
                    
                    if st.button(label, key=f"nav_btn_{pkey}"):
                        st.session_state["_active_page_key"] = pkey
                        st.rerun()

                    if btn_class:
                        st.markdown('</div>', unsafe_allow_html=True)
