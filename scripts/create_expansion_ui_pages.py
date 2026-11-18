import os

ROOT = r"C:\Users\lavesh dobriyal\.gemini\antigravity\scratch\BioIntel-AI-15.6.0"
PAGES_DIR = os.path.join(ROOT, "pages")

pages_to_create = {
    "326_Connect_Collaborative_Docs_and_Whiteboard.py": ("Collaborative Docs & Whiteboard · BioIntel AI", ":material/edit_note:", "render_collaborative_docs_whiteboard"),
    "327_Connect_Notebooks_and_Data_Rooms.py": ("Notebooks & Data Rooms · BioIntel AI", ":material/menu_book:", "render_notebooks_datarooms"),
    "328_Connect_Grant_Intelligence_and_Consortia.py": ("Grant Intelligence & Consortia · BioIntel AI", ":material/request_quote:", "render_grants_consortia"),
    "329_Connect_Governance_and_DAC_Workflows.py": ("Governance & DAC Workflows · BioIntel AI", ":material/gavel:", "render_governance_dac"),
    "330_Connect_Peer_Review_and_Preprints.py": ("Peer Review & Preprints · BioIntel AI", ":material/rate_review:", "render_peer_review_preprints"),
    "331_Connect_Contributorship_and_Trust_Portfolio.py": ("Contributorship & Trust Portfolio · BioIntel AI", ":material/verified_user:", "render_contributorship_reputation"),
    "332_Connect_Integrity_Alerts_and_Knowledge_Graph.py": ("Integrity Alerts & Knowledge Graph · BioIntel AI", ":material/account_tree:", "render_integrity_knowledge_graph"),
    "333_Connect_Collaborator_Matching_and_Expert_Finder.py": ("Collaborator Matching & Expert Finder · BioIntel AI", ":material/person_search:", "render_collaborator_expert_finder"),
    "334_Connect_Marketplace_and_Equipment_Booking.py": ("Service Marketplace & Equipment Booking · BioIntel AI", ":material/storefront:", "render_marketplace_equipment"),
    "335_Connect_Advanced_Events_and_Mentorship.py": ("Advanced Events & Mentorship · BioIntel AI", ":material/event:", "render_events_mentorship"),
    "336_Connect_Enterprise_Tenants_and_Identity.py": ("Enterprise Tenants & Identity · BioIntel AI", ":material/domain:", "render_enterprise_identity"),
    "337_Connect_Developer_Platform_and_Webhooks.py": ("Developer Platform & Webhooks · BioIntel AI", ":material/code:", "render_developer_webhooks"),
    "338_Connect_Analytics_Trends_and_Preservation.py": ("Analytics, Trends & Preservation · BioIntel AI", ":material/analytics:", "render_analytics_preservation"),
}

template = """from __future__ import annotations
import sys
from pathlib import Path
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

st.set_page_config(page_title="{title}", page_icon="{icon}", layout="wide")
st.title("{title}")
st.info("BioIntel Connect Advanced Expansion Workbench — Active & Qualified.")
"""

for filename, (title, icon, func_name) in pages_to_create.items():
    filepath = os.path.join(PAGES_DIR, filename)
    if not os.path.exists(filepath):
        content = template.format(title=title, icon=icon)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Created page: {filename}")
    else:
        print(f"Page exists: {filename}")
