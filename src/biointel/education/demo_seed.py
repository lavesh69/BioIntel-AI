from __future__ import annotations
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
import json
from biointel.education.database import EducationDatabase

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

class EducationDemoSeeder:
    """Deterministic synthetic demonstration workspace seeder for BioIntel AI."""

    def __init__(self, db: EducationDatabase):
        self.db = db

    def reset_demo_workspace(self) -> int:
        """Deletes all demo records marked with is_demo = 1 or data_origin = 'synthetic_demo'."""
        with self.db.connection() as conn:
            deleted = 0
            tables = [
                "memberships", "academic_units", "subjects", "enrollments", "teacher_assignments",
                "guardian_links", "timetable_entries", "attendance_sessions", "attendance_records",
                "attendance_corrections", "materials", "assignments", "submissions", "grades",
                "examinations", "results", "circulars", "courses", "course_modules", "lectures",
                "transcripts", "connect_channels", "connect_messages", "connect_meetings",
                "notifications", "portfolio_evidence", "question_bank", "career_opportunities",
                "virtual_lab_experiments", "institutions", "campuses", "departments", "programmes"
            ]
            for t in tables:
                cur = conn.execute(f"DELETE FROM {t} WHERE is_demo = 1 OR data_origin = 'synthetic_demo'")
                deleted += cur.rowcount
            return deleted

    def seed_demo_workspace(self) -> Dict[str, int]:
        """Seeds complete realistic demonstration data for a School and a University."""
        self.reset_demo_workspace()
        
        counts = {}
        ts = now_iso()
        
        with self.db.connection() as conn:
            # 1. Institutions
            conn.execute("INSERT INTO institutions VALUES ('inst_univ_demo', 'BioIntel Global Science University', 'university', 'BGSU', 'UTC', 'active', 1, 'synthetic_demo', ?, ?)", (ts, ts))
            conn.execute("INSERT INTO institutions VALUES ('inst_school_demo', 'BioIntel Science & STEM Academy School', 'school', 'BSSA', 'UTC', 'active', 1, 'synthetic_demo', ?, ?)", (ts, ts))
            counts["institutions"] = 2

            # 2. Campuses & Departments
            conn.execute("INSERT INTO campuses VALUES ('camp_main', 'inst_univ_demo', 'Main Science Campus', 'MAIN', 'University Hill 101', 'active', 1, 'synthetic_demo', ?, ?)", (ts, ts))
            conn.execute("INSERT INTO departments VALUES ('dept_bioinfo', 'inst_univ_demo', 'camp_main', 'Department of Computational Biology & Bioinformatics', 'BIOINFO', 'prof_lavesh', 'active', 1, 'synthetic_demo', ?, ?)", (ts, ts))
            conn.execute("INSERT INTO departments VALUES ('dept_neuro', 'inst_univ_demo', 'camp_main', 'Department of Neuroscience & CNS Research', 'NEURO', 'prof_sharma', 'active', 1, 'synthetic_demo', ?, ?)", (ts, ts))
            counts["departments"] = 2

            # 3. Programmes
            conn.execute("INSERT INTO programmes VALUES ('prog_bs_bioinfo', 'inst_univ_demo', 'dept_bioinfo', 'B.Sc. Computational Biology & Bioinformatics', 'bachelor', 4, 'active', 1, 'synthetic_demo', ?, ?)", (ts, ts))
            conn.execute("INSERT INTO programmes VALUES ('prog_ms_genomics', 'inst_univ_demo', 'dept_bioinfo', 'M.Sc. High-Throughput Genomics & Precision Medicine', 'master', 2, 'active', 1, 'synthetic_demo', ?, ?)", (ts, ts))
            counts["programmes"] = 2

            # 4. Academic Units (Sections / Batches)
            conn.execute("INSERT INTO academic_units VALUES ('unit_sem5', 'inst_univ_demo', NULL, 'semester', 'Semester 5 (Fall 2026)', '2026-2027', 'active', 1, 'synthetic_demo', ?, ?)", (ts, ts))
            conn.execute("INSERT INTO academic_units VALUES ('unit_secA', 'inst_univ_demo', 'unit_sem5', 'section', 'Section A (Bioinformatics Core)', '2026-2027', 'active', 1, 'synthetic_demo', ?, ?)", (ts, ts))
            counts["academic_units"] = 2

            # 5. Memberships
            users = [
                ("prof_lavesh", "Prof. Lavesh Dobriyal", "professor", "lavesh@biointel.edu"),
                ("dr_sharma", "Dr. Ananya Sharma", "teacher", "ananya@biointel.edu"),
                ("admin_verma", "Rajesh Verma", "inst_admin", "admin@biointel.edu"),
                ("student_aarav", "Aarav Patel", "student", "aarav@student.biointel.edu"),
                ("student_diya", "Diya Sengupta", "student", "diya@student.biointel.edu"),
                ("guardian_patel", "Suresh Patel", "guardian", "suresh@parent.biointel.edu")
            ]
            for u_id, u_name, u_role, u_email in users:
                conn.execute(
                    "INSERT INTO memberships VALUES (?, 'inst_univ_demo', ?, ?, ?, ?, 'active', 1, 'synthetic_demo', ?, ?)",
                    (f"mem_{u_id}", u_id, u_role, u_name, u_email, ts, ts)
                )
            counts["memberships"] = len(users)

            # 6. Subjects & Enrollments
            conn.execute("INSERT INTO subjects VALUES ('sub_ngs301', 'inst_univ_demo', 'unit_secA', 'BIO301', 'Next-Generation Sequencing & Genomics', 'Core course on Illumina & Nanopore sequencing.', 4, 'Syllabus: FastQC, BWA, GATK, SAMtools', 'active', 1, 'synthetic_demo', ?, ?)", (ts, ts))
            conn.execute("INSERT INTO subjects VALUES ('sub_drug302', 'inst_univ_demo', 'unit_secA', 'BIO302', 'Structure-Based Drug Design & SMILES Analytics', 'Small molecule docking and ADMET prediction.', 4, 'Syllabus: RDKit, PyMOL, AutoDock, ChEMBL', 'active', 1, 'synthetic_demo', ?, ?)", (ts, ts))
            counts["subjects"] = 2

            conn.execute("INSERT INTO enrollments VALUES ('enr_aarav_ngs', 'inst_univ_demo', 'sub_ngs301', 'student_aarav', 'Aarav Patel', 'BIO2026-001', 'active', 1, 'synthetic_demo', ?, ?)", (ts, ts))
            conn.execute("INSERT INTO enrollments VALUES ('enr_diya_ngs', 'inst_univ_demo', 'sub_ngs301', 'student_diya', 'Diya Sengupta', 'BIO2026-002', 'active', 1, 'synthetic_demo', ?, ?)", (ts, ts))
            conn.execute("INSERT INTO teacher_assignments VALUES ('ta_lavesh_ngs', 'inst_univ_demo', 'sub_ngs301', 'prof_lavesh', 'Prof. Lavesh Dobriyal', 1, 'active', 1, 'synthetic_demo', ?, ?)", (ts, ts))
            counts["enrollments"] = 2

            # 7. Timetable & Attendance
            conn.execute("INSERT INTO timetable_entries VALUES ('tt_mon_1', 'inst_univ_demo', 'sub_ngs301', 'prof_lavesh', 'Section A', 'Monday', 'Lab 304', 'Bioinformatics Workstation Lab', '09:00', '10:30', 'meet_ngs_01', 'scheduled', 1, 'synthetic_demo', ?, ?)", (ts, ts))
            conn.execute("INSERT INTO attendance_sessions VALUES ('att_sess_01', 'inst_univ_demo', 'sub_ngs301', 'prof_lavesh', '2026-07-28', 'Period 1', 1, ?, 'closed', 1, 'synthetic_demo', ?, ?)", (ts, ts, ts))
            conn.execute("INSERT INTO attendance_records VALUES ('att_rec_aarav', 'inst_univ_demo', 'att_sess_01', 'student_aarav', 'Present', 'Attended on time', 'prof_lavesh', 1, 'synthetic_demo', ?, ?)", (ts, ts))
            conn.execute("INSERT INTO attendance_records VALUES ('att_rec_diya', 'inst_univ_demo', 'att_sess_01', 'student_diya', 'Present', 'Attended on time', 'prof_lavesh', 1, 'synthetic_demo', ?, ?)", (ts, ts))
            counts["attendance_records"] = 2

            # 8. Assignments & Submissions
            conn.execute("INSERT INTO assignments VALUES ('asgn_ngs_1', 'inst_univ_demo', 'sub_ngs301', 'prof_lavesh', 'NGS Quality Control & Variant Calling Pipeline', 'Run FastQC on the provided SRA dataset and generate a filtered VCF file.', 'Understand Read Quality, Phred Scores, and Variant Annotation', '2026-08-05T23:59:59', 100.0, '{\"rubric\": \"Accuracy 50%, Report 30%, Code 20%\"}', '[\"pdf\",\"txt\"]', 'late_penalty_10_pct', 'published', 1, 'synthetic_demo', ?, ?)", (ts, ts))
            conn.execute("INSERT INTO submissions VALUES ('subm_aarav_1', 'inst_univ_demo', 'asgn_ngs_1', 'student_aarav', 'Completed variant calling using BWA-MEM and GATK HaplotypeCaller. Filtered PASS variants = 1,420.', '/data/submissions/aarav_vcf_report.pdf', ?, 'Shiro AI Draft: Excellent methodology. Consider adding DP >= 10 depth filter.', 'submitted', 1, 'synthetic_demo', ?, ?)", (ts, ts, ts))
            counts["assignments"] = 1

            # 9. Circulars
            conn.execute("INSERT INTO circulars VALUES ('circ_01', 'inst_univ_demo', 'admin_verma', 'CIRC-2026-089', 'Annual International Bioinformatics Symposium & Hackathon', 'We are pleased to announce the 2026 International BioIntel Hackathon. Registrations open today for all students and researchers.', '[\"all\"]', 'high', 'published', 'admin_verma', ?, 1, 'synthetic_demo', ?, ?)", (ts, ts, ts))
            counts["circulars"] = 1

            # 10. Courses, Lectures & Transcripts
            conn.execute("INSERT INTO courses VALUES ('crs_ngs_master', 'inst_univ_demo', 'prof_lavesh', 'Prof. Lavesh Dobriyal', 'Masterclass in High-Throughput Genomics & Variant Discovery', 'From raw FASTQ reads to clinical variant interpretation and structural variation graphs.', 'Genomics', 'advanced', 'Basic Molecular Biology & Python', 'Master NGS alignment, GATK pipelines, and pangenome graphs', 'published', 1, 'synthetic_demo', ?, ?)", (ts, ts))
            conn.execute("INSERT INTO course_modules VALUES ('mod_ngs_1', 'crs_ngs_master', 'Module 1: Read QC, Alignment & Trimming', 'Core foundational practices for raw sequencing data.', 1, ?, ?)", (ts, ts))
            conn.execute("INSERT INTO lectures VALUES ('lect_ngs_1', 'inst_univ_demo', 'crs_ngs_master', 'mod_ngs_1', 'prof_lavesh', 'Lecture 1: FastQC Diagnostics & Adapter Removal', 'Detailed walkthrough of Phred quality scores and per-base sequence content.', '/media/lectures/lecture1_ngs.mp4', 1800.0, 'sha256_mock_hash_1', 450000000, 'video/mp4', 'completed', '[{\"start_seconds\":0.0,\"title\":\"Introduction\"},{\"start_seconds\":300.0,\"title\":\"Phred Quality Scores\"}]', 'published', 1, 'synthetic_demo', ?, ?)", (ts, ts))
            conn.execute("INSERT INTO transcripts VALUES ('tr_lect_1', 'lect_ngs_1', 'en', 'Full transcript text for Lecture 1...', 'Summary of FastQC diagnostics and adapter trimming.', 'Detailed explanation of Phred scores Q20 and Q30...', '[\"FastQC\",\"Phred Score\",\"Adapter Trimming\"]', '[{\"question\":\"What is Q30 accuracy?\",\"options\":[\"99.9%\",\"99%\"],\"answer\":\"99.9%\"}]', 'approved', 1, 'synthetic_demo', ?, ?)", (ts, ts))
            counts["courses"] = 1
            counts["lectures"] = 1

            # 11. Connect Channels & Meetings
            conn.execute("INSERT INTO connect_channels VALUES ('chan_bioinfo_301', 'inst_univ_demo', 'BIO301 Class Discussion Channel', 'class', 'Official classroom communication channel for BIO301.', 0, 1, 'synthetic_demo', ?, ?)", (ts, ts))
            conn.execute("INSERT INTO connect_messages VALUES ('msg_01', 'chan_bioinfo_301', 'prof_lavesh', 'Prof. Lavesh Dobriyal', 'Welcome to BIO301! The first lecture slides and SRA dataset are uploaded.', '[]', 1, ?)", (ts,))
            conn.execute("INSERT INTO connect_meetings VALUES ('meet_ngs_01', 'inst_univ_demo', 'prof_lavesh', 'Prof. Lavesh Dobriyal', 'BIO301 Interactive Live Lecture & Lab Q&A', 'classroom', '2026-07-29T10:00:00', '2026-07-29T11:30:00', 'https://connect.biointel.edu/meet/ngs301', 1, 1, 'scheduled', 1, 'synthetic_demo', ?, ?)", (ts, ts))
            counts["connect_meetings"] = 1

            # 12. Notifications & Portfolio & Virtual Labs
            conn.execute("INSERT INTO notifications VALUES ('notif_1', 'inst_univ_demo', 'student_aarav', 'New Assignment Published', 'NGS Quality Control & Variant Calling Pipeline is now assigned.', 'assignment', 'high', '/classroom?tab=assignments', 0, 1, ?)", (ts,))
            conn.execute("INSERT INTO portfolio_evidence VALUES ('ev_1', 'student_aarav', 'High-Throughput Variant Calling Pipeline', 'project', 'Built an end-to-end Snakemake workflow for FASTQ to VCF annotation.', 'biointel://portfolio/student-aarav/high-throughput-variant-calling', 'Prof. Lavesh Dobriyal', 1, ?)", (ts,))
            conn.execute("INSERT INTO certificates VALUES ('cert_aarav_ngs', 'inst_univ_demo', 'crs_ngs_master', 'student_aarav', 'Aarav Patel', 'Masterclass in High-Throughput Genomics', '2026-07-28', 'CERT-BGSU-2026-9842', 'data:image/png;base64,demoqrdata', 1, 'synthetic_demo', ?)", (ts,))
            counts["certificates"] = 1

        return counts

