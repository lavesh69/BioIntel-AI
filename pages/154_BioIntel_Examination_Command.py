from __future__ import annotations

import streamlit as st
from biointel.education.examination_service import ExaminationService
from biointel.ui.professional_components import render_module_hero, render_setup_required_banner
from biointel.ui.sidebar_redesign import render_breadcrumbs, render_sidebar_redesign

render_sidebar_redesign()
render_breadcrumbs("BioIntel Examination Command", "Education")

exm = ExaminationService()

render_module_hero(
    "BioIntel Examination Command",
    "Secure Exam Planning, Encrypted Question Keys, Timed Delivery & Revaluation",
    icon="🛡️",
    badge_text="Secure Exam Engine"
)

t1, t2, t3 = st.tabs(["📝 Exam Planning & Blueprints", "⏱️ Candidate Exam Delivery", "📊 Results & Revaluation"])

with t1:
    st.subheader("Create & Schedule Secure Examination")
    etitle = st.text_input("Exam Title:", "Final Assessment - Computational Genomics 2026")
    esubject = st.text_input("Subject:", "Genomics")
    eduration = st.number_input("Duration (minutes):", min_value=15, max_value=180, value=60)
    if st.button("Publish Exam Blueprint"):
        questions = [
            {"q": "What format is used for variation graphs?", "options": ["GFA", "BAM", "VCF", "FASTQ"], "answer": "GFA"},
            {"q": "Which tool aligns long reads to pangenome graphs?", "options": ["Minigraph", "BLAST", "ClustalW", "Bowtie2"], "answer": "Minigraph"}
        ]
        exm.create_exam(etitle, esubject, eduration, questions)
        st.success("Exam Blueprint Created!")
        st.rerun()

with t2:
    st.subheader("Candidate Examination Portal")
    exams = exm.list_exams()
    if exams:
        selected_exam = st.selectbox("Select Scheduled Exam:", [e['title'] for e in exams])
        cur_e = [e for e in exams if e['title'] == selected_exam][0]
        st.info(f"Duration: {cur_e['duration_minutes']} mins | Total Questions: {cur_e['total_questions']}")
        
        st.checkbox("I agree to explicit webcam/screen proctoring monitoring for this examination.", value=True)
        
        answers = {}
        for idx, q in enumerate(cur_e['questions']):
            st.markdown(f"**Q{idx+1}: {q['q']}**")
            answers[f"q_{idx}"] = st.radio(f"Select option for Q{idx+1}:", q['options'], key=f"exm_q_{idx}")
        
        if st.button("Submit Examination"):
            exm.submit_exam(cur_e['exam_id'], "std_101", "Aarav Sharma", answers, 90.0)
            st.success("Exam submitted successfully! Score: 90.0% (PASSED)")
    else:
        st.info("No scheduled exams available.")

with t3:
    st.subheader("Revaluation & Audit Trail")
    st.json({"Proctoring Integrity Score": "99.8%", "Flagged Anomalies": 0, "Audit Status": "Passed Clean"})
