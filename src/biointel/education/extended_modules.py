from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import json
from biointel.education.database import EducationDatabase

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

class ExtendedEducationModules:
    """Question Bank, Student Portfolio, Career Hub, Virtual Lab & Bioinformatics Sandbox backend."""

    def __init__(self, db: EducationDatabase):
        self.db = db

    # 1. Question Bank & Assessment Intelligence
    def add_question(self, question_text: str, options: List[str], correct_answer: str, subject_id: str = "", difficulty: str = "medium", topic: str = "Genomics") -> str:
        q_id = f"qb_{uuid.uuid4().hex[:8]}"
        with self.db.connection() as conn:
            conn.execute(
                "INSERT INTO question_bank VALUES (?, '', ?, ?, ?, ?, ?, ?, 0, ?)",
                (q_id, subject_id, question_text, json.dumps(options), correct_answer, difficulty, topic, now_iso())
            )
        return q_id

    def get_question_bank(self, subject_id: Optional[str] = None, topic: Optional[str] = None) -> List[Dict[str, Any]]:
        with self.db.connection() as conn:
            query = "SELECT * FROM question_bank WHERE 1=1"
            params = []
            if subject_id:
                query += " AND subject_id = ?"
                params.append(subject_id)
            if topic:
                query += " AND topic = ?"
                params.append(topic)
            rows = conn.execute(query, tuple(params)).fetchall()
            res = []
            for r in rows:
                d = dict(r)
                d["options"] = json.loads(d["options_json"] or "[]")
                res.append(d)
            return res

    # 2. Student Portfolio & Verified Credentials
    def add_portfolio_evidence(self, student_id: str, title: str, evidence_type: str, description: str, proof_url: str = "") -> str:
        ev_id = f"ev_{uuid.uuid4().hex[:8]}"
        with self.db.connection() as conn:
            conn.execute(
                "INSERT INTO portfolio_evidence VALUES (?, ?, ?, ?, ?, ?, 'Verified Educator', 0, ?)",
                (ev_id, student_id, title, evidence_type, description, proof_url, now_iso())
            )
        return ev_id

    def get_student_portfolio(self, student_id: str) -> Dict[str, Any]:
        with self.db.connection() as conn:
            evidences = conn.execute("SELECT * FROM portfolio_evidence WHERE student_id = ?", (student_id,)).fetchall()
            certs = conn.execute("SELECT * FROM certificates WHERE student_id = ?", (student_id,)).fetchall()
            
            return {
                "student_id": student_id,
                "verified_credentials_count": len(certs),
                "portfolio_items_count": len(evidences),
                "certificates": [dict(c) for c in certs],
                "evidences": [dict(e) for e in evidences],
                "skill_matrix": {
                    "Bioinformatics": "Advanced",
                    "NGS Analysis": "Intermediate",
                    "Python & R": "Proficient",
                    "Structural Biology": "Beginner"
                }
            }

    # 3. Career, Internship & Scholarship Hub
    def create_career_opportunity(self, title: str, company: str, opp_type: str, description: str, apply_url: str, deadline: str) -> str:
        opp_id = f"opp_{uuid.uuid4().hex[:8]}"
        with self.db.connection() as conn:
            conn.execute(
                "INSERT INTO career_opportunities VALUES (?, '', ?, ?, ?, ?, ?, ?, 0, ?)",
                (opp_id, title, company, opp_type, description, apply_url, deadline, now_iso())
            )
        return opp_id

    def get_career_opportunities(self) -> List[Dict[str, Any]]:
        with self.db.connection() as conn:
            rows = conn.execute("SELECT * FROM career_opportunities ORDER BY created_at DESC").fetchall()
            return [dict(r) for r in rows]

    # 4. Virtual Science Lab & Bioinformatics Sandbox
    def get_virtual_labs(self) -> List[Dict[str, Any]]:
        with self.db.connection() as conn:
            rows = conn.execute("SELECT * FROM virtual_lab_experiments").fetchall()
            if not rows:
                # Default labs
                return [
                    {
                        "id": "vlab_ngs_01",
                        "title": "FASTQ Quality Control & Trimming Simulator",
                        "lab_type": "genomics",
                        "instructions": "Execute adapter trimming and Phred quality score filtering on raw Illumina paired-end reads."
                    },
                    {
                        "id": "vlab_smiles_02",
                        "title": "Small Molecule SMILES & ADMET Predictor",
                        "lab_type": "SMILES_drug_design",
                        "instructions": "Draw or paste SMILES strings to evaluate Lipinski's Rule of 5 and BBB permeability."
                    },
                    {
                        "id": "vlab_protein_03",
                        "title": "AlphaFold Structural pLDDT Confidence Inspector",
                        "lab_type": "proteomics",
                        "instructions": "Inspect 3D coordinates and per-residue pLDDT score distributions for candidate targets."
                    }
                ]
            return [dict(r) for r in rows]

