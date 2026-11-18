import os

pages_dir = r"C:\Users\lavesh dobriyal\.gemini\antigravity\scratch\BioIntel-Step220\pages"

modules = [
    ('160_Adaptive_Learning_Engine.py', 'Adaptive Learning Engine', 'adaptive_learning', '🧠', 'Personalised Study Tracks, Skill Gap Analysis & Micro-Learning Pathways'),
    ('161_Virtual_Science_Lab.py', 'Virtual Science Lab', 'virtual_lab', '🧪', 'Interactive In-Silico PCR, Gel Electrophoresis & Assay Simulations'),
    ('162_Bioinformatics_Learning_Sandbox.py', 'Bioinformatics Learning Sandbox', 'bioinformatics_sandbox', '💻', 'Guided FASTA, RNA-seq, BLAST & Variant Calling Code Sandbox'),
    ('163_Shiro_AI_Tutor.py', 'Shiro AI Tutor', 'shiro_tutor', '🤖', 'Multilingual 1-on-1 AI Tutoring, Quiz Generator & Concept Explanation'),
    ('164_Learning_Analytics.py', 'Learning Analytics', 'learning_analytics', '📊', 'Cohort Skill Mastery, Time-on-Task & Engagement Metrics'),
    ('165_Digital_Scientific_Library.py', 'Digital Scientific Library', 'digital_library', '📖', 'Open Access Textbooks, Reference Manuals & Scientific Protocols'),
    ('166_Student_Research_Innovation_Hub.py', 'Student Research & Innovation Hub', 'student_research_hub', '🚀', 'Student Grant Submissions, Project Incubation & Mentorship'),
    ('167_Competition_Hackathon_Center.py', 'Competition & Hackathon Center', 'competition_center', '🏆', 'BioHackathons, Kaggle-Style Leaderboards & Code Challenges'),
    ('168_Career_Internship_Scholarship_Hub.py', 'Career, Internship & Scholarship Hub', 'career_hub', '💼', 'Global Fellowships, Postdoc Positions & Industry Internships'),
    ('169_Academic_Portfolio_Credentials.py', 'Academic Portfolio & Credentials', 'academic_portfolio', '📜', 'Verified Micro-Credentials, Digital Badges & Transcript Exports'),
    ('170_Practical_Laboratory_Management.py', 'Practical Laboratory Management', 'lab_management', '🔬', 'Equipment Booking, Buffer Inventory & Chemical Safety Logs'),
    ('171_Question_Bank_Assessment_Intelligence.py', 'Question Bank & Assessment Intelligence', 'question_bank', '❓', 'Peer-Reviewed Item Bank, Difficulty Indexing & Question Tagging'),
    ('172_Multilingual_Lecture_Intelligence.py', 'Multilingual Lecture Intelligence', 'lecture_intelligence', '🎙️', 'Real-Time Multi-Language Translation, Captions & Note Summaries'),
    ('173_Academic_ERP.py', 'Academic ERP', 'academic_erp', '🏫', 'Fee Management, Course Registration & Institutional Compliance'),
    ('174_Gamified_Learning.py', 'Gamified Learning', 'gamified_learning', '🎮', 'BioQuest Badges, Leaderboards & XP Points Rewards'),
    ('175_Teaching_Quality_Support.py', 'Teaching Quality Support', 'teaching_support', '👩‍🏫', 'Peer Teaching Evaluations, Student Feedback & Pedagogy Tools'),
    ('176_Offline_Learning.py', 'Offline Learning', 'offline_learning', '📦', 'Cached Course Packs, Offline Sync & Low-Bandwidth Mode'),
    ('177_Open_Science.py', 'Open Science', 'open_science', '🌐', 'FAIR Data Repositories, Micro-Attribution & Open Access Publishing'),
    ('178_Collaboration_Network.py', 'Collaboration Network', 'collaboration_network', '🤝', 'Inter-Institutional Project Rooms & Shared Research Compute'),
    ('179_Safety_Moderation.py', 'Safety & Moderation', 'safety_moderation', '🛡️', 'Content Integrity, Minor Protection & Ethical AI Governance')
]

template = """from __future__ import annotations

import streamlit as st
import pandas as pd
from biointel.education.universe_workspaces_service import UniverseWorkspacesService
from biointel.ui.professional_components import render_module_hero, render_empty_state
from biointel.ui.sidebar_redesign import render_breadcrumbs, render_sidebar_redesign

render_sidebar_redesign()
render_breadcrumbs("{title}", "Education")

uv = UniverseWorkspacesService()
module_key = "{mod_key}"

render_module_hero(
    "{title}",
    "{desc}",
    icon="{icon}",
    badge_text="Education Universe"
)

records = uv.list_records(module_key)

t1, t2 = st.tabs(["📋 Active Workspaces", "➕ Create New Workspace Entry"])

with t1:
    st.subheader("Saved {title} Records")
    if not records:
        render_empty_state("No {title} Records Found", "Click 'Create New Workspace Entry' or Reseed Demo Data to populate.")
    else:
        for r in records:
            with st.expander(f"{icon} {{r['title']}}"):
                st.json(r['payload'])
                if st.button("🗑️ Delete Record", key=f"del_{{r['record_id']}}"):
                    uv.delete_record(r['record_id'])
                    st.success("Record deleted!")
                    st.rerun()

with t2:
    st.subheader("Add New {title} Workspace Entry")
    w_title = st.text_input("Workspace Title:", f"New {title} Record")
    w_note = st.text_area("Notes / Configuration JSON:", '{{\"status\": \"active\", \"priority\": \"high\"}}')
    if st.button("Save Entry to Database"):
        uv.save_record(module_key, w_title, {{"notes": w_note}})
        st.success("Workspace entry saved!")
        st.rerun()
"""

for fname, title, mod_key, icon, desc in modules:
    path = os.path.join(pages_dir, fname)
    content = template.format(title=title, mod_key=mod_key, icon=icon, desc=desc)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)

print(f"Successfully generated all {len(modules)} Education Universe pages!")
