from __future__ import annotations

import math
from collections import Counter
from typing import Any

from .platform import ADMIN, STUDENT, TEACHER, Denied, EducationError, EducationPlatform

DNA = set("ACGTN")
COMPLEMENT = str.maketrans("ACGTN", "TGCAN")
CODON_TABLE = {
    "TTT":"F","TTC":"F","TTA":"L","TTG":"L","CTT":"L","CTC":"L","CTA":"L","CTG":"L",
    "ATT":"I","ATC":"I","ATA":"I","ATG":"M","GTT":"V","GTC":"V","GTA":"V","GTG":"V",
    "TCT":"S","TCC":"S","TCA":"S","TCG":"S","CCT":"P","CCC":"P","CCA":"P","CCG":"P",
    "ACT":"T","ACC":"T","ACA":"T","ACG":"T","GCT":"A","GCC":"A","GCA":"A","GCG":"A",
    "TAT":"Y","TAC":"Y","TAA":"*","TAG":"*","CAT":"H","CAC":"H","CAA":"Q","CAG":"Q",
    "AAT":"N","AAC":"N","AAA":"K","AAG":"K","GAT":"D","GAC":"D","GAA":"E","GAG":"E",
    "TGT":"C","TGC":"C","TGA":"*","TGG":"W","CGT":"R","CGC":"R","CGA":"R","CGG":"R",
    "AGT":"S","AGC":"S","AGA":"R","AGG":"R","GGT":"G","GGC":"G","GGA":"G","GGG":"G",
}


class EducationModuleEngines:
    """Deterministic, bounded engines behind the highest-value Education Universe modules."""

    def __init__(self, platform: EducationPlatform):
        self.platform = platform

    def _roles(self, actor: str, institution_id: str) -> set[str]:
        return {row["role"] for row in self.platform._require(actor, institution_id)}

    def _student_access(self, actor: str, institution_id: str, student_id: str) -> set[str]:
        roles = self._roles(actor, institution_id)
        if actor != student_id and not roles & TEACHER and not self.platform._guardian_can(actor, institution_id, student_id):
            raise Denied("Student analytics access denied.")
        return roles

    def adaptive_learning_snapshot(self, actor: str, institution_id: str, student_id: str | None = None) -> dict[str, Any]:
        student_id = student_id or actor
        self._student_access(actor, institution_id, student_id)
        subjects = self.platform._all(
            """SELECT s.id,s.code,s.name FROM subjects s JOIN enrollments e ON e.subject_id=s.id
               WHERE s.institution_id=? AND e.student_id=? AND e.state='active' ORDER BY s.code""",
            (institution_id, student_id),
        )
        items: list[dict[str, Any]] = []
        for subject in subjects:
            attendance = self.platform._one(
                """SELECT COUNT(*) total,SUM(CASE WHEN r.status IN ('present','late','online_present','practical_attendance','examination_attendance') THEN 1 ELSE 0 END) attended
                   FROM attendance_records r JOIN attendance_sessions a ON a.id=r.session_id WHERE a.subject_id=? AND r.student_id=?""",
                (subject["id"], student_id),
            ) or {"total": 0, "attended": 0}
            assignments = self.platform._one(
                """SELECT COUNT(*) total,SUM(CASE WHEN sub.state='submitted' THEN 1 ELSE 0 END) submitted,
                   AVG(CASE WHEN g.id IS NOT NULL THEN 100.0*g.marks/a.max_marks END) grade_percent
                   FROM assignments a LEFT JOIN submissions sub ON sub.assignment_id=a.id AND sub.student_id=?
                   LEFT JOIN grades g ON g.submission_id=sub.id WHERE a.subject_id=? AND a.state='published'""",
                (student_id, subject["id"]),
            ) or {"total": 0, "submitted": 0, "grade_percent": None}
            attendance_ratio = (attendance["attended"] or 0) / max(attendance["total"] or 0, 1)
            completion_ratio = (assignments["submitted"] or 0) / max(assignments["total"] or 0, 1)
            grade_ratio = float(assignments["grade_percent"] or 0) / 100.0
            evidence_weights = []
            if attendance["total"]: evidence_weights.append((attendance_ratio, 0.25))
            if assignments["total"]: evidence_weights.append((completion_ratio, 0.30))
            if assignments["grade_percent"] is not None: evidence_weights.append((grade_ratio, 0.45))
            mastery = 100.0 * sum(value * weight for value, weight in evidence_weights) / max(sum(weight for _, weight in evidence_weights), 1)
            confidence = min(1.0, ((attendance["total"] or 0) + (assignments["total"] or 0) * 2) / 12)
            recommendations: list[dict[str, str]] = []
            if attendance["total"] and attendance_ratio < 0.75:
                recommendations.append({"action": "Review missed class material", "reason": f"Attendance evidence is {attendance_ratio:.0%}."})
            if assignments["total"] and completion_ratio < 1:
                recommendations.append({"action": "Complete pending assignments", "reason": f"{int(assignments['total']-assignments['submitted'])} published assignment(s) are not final-submitted."})
            if assignments["grade_percent"] is not None and grade_ratio < 0.60:
                recommendations.append({"action": "Use a guided revision plan", "reason": f"Released assignment performance is {grade_ratio:.0%}."})
            if not recommendations:
                recommendations.append({"action": "Continue the current learning path", "reason": "Available evidence does not show a priority intervention."})
            items.append({
                "subject_id": subject["id"], "subject_code": subject["code"], "subject": subject["name"],
                "mastery_percent": round(mastery, 1), "evidence_confidence": round(confidence, 2),
                "attendance_ratio": round(attendance_ratio, 3), "assignment_completion_ratio": round(completion_ratio, 3),
                "released_grade_percent": None if assignments["grade_percent"] is None else round(float(assignments["grade_percent"]), 1),
                "recommendations": recommendations,
            })
        return {"student_id": student_id, "subjects": items, "explainability": "Mastery uses only persisted attendance, submission and released-grade evidence; it is not a diagnosis."}

    def learning_analytics(self, actor: str, institution_id: str, student_id: str | None = None) -> dict[str, Any]:
        snapshot = self.adaptive_learning_snapshot(actor, institution_id, student_id)
        flags = []
        for subject in snapshot["subjects"]:
            reasons = []
            if subject["attendance_ratio"] < 0.75: reasons.append("attendance below 75%")
            if subject["assignment_completion_ratio"] < 0.80: reasons.append("assignment completion below 80%")
            if subject["released_grade_percent"] is not None and subject["released_grade_percent"] < 60: reasons.append("released assignment performance below 60%")
            if reasons:
                flags.append({"subject_id": subject["subject_id"], "subject": subject["subject"], "level": "support_review", "reasons": reasons, "human_review_required": True})
        return {**snapshot, "support_flags": flags, "metric_definition": "Threshold-based support review; no medical, psychological or permanent learner label is generated."}

    def virtual_lab(self, actor: str, institution_id: str, experiment: str, parameters: dict[str, Any]) -> dict[str, Any]:
        self._roles(actor, institution_id)
        experiment = str(experiment).strip().lower()
        if experiment == "enzyme_kinetics":
            substrate = max(0.0, float(parameters.get("substrate", 1)))
            vmax = max(0.0, float(parameters.get("vmax", 1)))
            km = max(1e-9, float(parameters.get("km", 0.5)))
            velocity = vmax * substrate / (km + substrate)
            result = {"substrate": substrate, "vmax": vmax, "km": km, "velocity": round(velocity, 6)}
        elif experiment == "logistic_population":
            initial = max(0.0, float(parameters.get("initial", 10)))
            rate = max(-2.0, min(2.0, float(parameters.get("rate", 0.2))))
            capacity = max(1.0, float(parameters.get("capacity", 100)))
            steps = max(1, min(200, int(parameters.get("steps", 20))))
            population = initial; series = [round(population, 6)]
            for _ in range(steps):
                population = max(0.0, population + rate * population * (1 - population / capacity));series.append(round(population, 6))
            result = {"initial": initial, "rate": rate, "capacity": capacity, "series": series}
        elif experiment == "mendelian_monohybrid":
            parent_a = str(parameters.get("parent_a", "Aa")); parent_b = str(parameters.get("parent_b", "Aa"))
            if len(parent_a) != 2 or len(parent_b) != 2 or parent_a[0].lower() != parent_a[1].lower() or parent_b[0].lower() != parent_b[1].lower() or parent_a[0].lower() != parent_b[0].lower():
                raise EducationError("Parents must be two-allele genotypes of the same gene, for example Aa and Aa.")
            children = ["".join(sorted((a, b), key=lambda x: x.islower())) for a in parent_a for b in parent_b]
            counts = Counter(children);result = {"offspring_probabilities": {key: value / 4 for key, value in sorted(counts.items())}}
        else:
            raise EducationError("Supported virtual experiments: enzyme_kinetics, logistic_population, mendelian_monohybrid.")
        return {"experiment": experiment, "simulation_only": True, "result": result, "safety_boundary": "Conceptual virtual simulation; it does not authorize a physical or hazardous procedure."}

    def bioinformatics_sandbox(self, actor: str, institution_id: str, operation: str, sequence: str) -> dict[str, Any]:
        self._roles(actor, institution_id)
        if len(sequence.encode("utf-8")) > 2 * 1024 * 1024:
            raise EducationError("Sandbox input exceeds the 2 MiB educational limit.")
        cleaned = "".join(line.strip() for line in str(sequence).splitlines() if not line.startswith(">" )).upper().replace(" ", "")
        if not cleaned or set(cleaned) - DNA:
            raise EducationError("Sandbox accepts a DNA sequence containing only A, C, G, T and N.")
        operation = str(operation).strip().lower()
        if operation == "fasta_stats":
            gc = sum(base in "GC" for base in cleaned)
            result = {"length": len(cleaned), "gc_percent": round(100 * gc / len(cleaned), 3), "ambiguous_bases": cleaned.count("N")}
        elif operation == "reverse_complement":
            result = {"sequence": cleaned.translate(COMPLEMENT)[::-1]}
        elif operation == "translate":
            protein = "".join(CODON_TABLE.get(cleaned[index:index+3], "X") for index in range(0, len(cleaned)-2, 3))
            result = {"frame": 1, "protein": protein, "trailing_bases": len(cleaned) % 3}
        else:
            raise EducationError("Supported sandbox operations: fasta_stats, reverse_complement, translate.")
        return {"operation": operation, "input_sha256": __import__("hashlib").sha256(cleaned.encode()).hexdigest(), "result": result, "resource_boundary": "No shell, network, external executable or unrestricted file access."}

    def assessment_blueprint(self, actor: str, institution_id: str, subject_id: str, outcomes: list[str], total_marks: float, difficulty: dict[str, float] | None = None) -> dict[str, Any]:
        roles = self._roles(actor, institution_id)
        if not roles & TEACHER: raise Denied("Assessment blueprint creation requires an educator role.")
        self.platform._subject(institution_id, subject_id)
        outcomes = [str(item).strip() for item in outcomes if str(item).strip()]
        if not outcomes: raise EducationError("At least one learning outcome is required.")
        total_marks = float(total_marks)
        if total_marks <= 0: raise EducationError("Total marks must be greater than zero.")
        mix = difficulty or {"foundational": 0.30, "application": 0.45, "analysis": 0.25}
        if any(float(value) < 0 for value in mix.values()) or not math.isclose(sum(float(value) for value in mix.values()), 1.0, abs_tol=0.001):
            raise EducationError("Difficulty proportions must be non-negative and sum to 1.0.")
        outcome_marks = total_marks / len(outcomes)
        return {
            "subject_id": subject_id, "total_marks": total_marks,
            "outcomes": [{"learning_outcome": outcome, "target_marks": round(outcome_marks, 2)} for outcome in outcomes],
            "difficulty_distribution": {key: round(total_marks * float(value), 2) for key, value in mix.items()},
            "review_required": True,
            "boundary": "Blueprint support only; protected question content and final approval remain with authorized educators.",
        }

    def reproducibility_check(self, actor: str, institution_id: str, package: dict[str, Any]) -> dict[str, Any]:
        self._roles(actor, institution_id)
        checks = {
            "method": bool(str(package.get("method", "")).strip()),
            "provenance": bool(str(package.get("provenance", "")).strip()),
            "license": bool(str(package.get("license", "")).strip()),
            "software_versions": bool(package.get("software_versions")),
            "parameters": isinstance(package.get("parameters"), dict) and bool(package.get("parameters")),
            "checksums": isinstance(package.get("checksums"), dict) and bool(package.get("checksums")),
            "private_data_removed": package.get("contains_private_data") is False,
        }
        score = round(100 * sum(checks.values()) / len(checks), 1)
        return {"score_percent": score, "checks": checks, "ready_for_review": all(checks.values()), "claim_boundary": "This is an internal reproducibility readiness check, not peer review or accreditation."}
