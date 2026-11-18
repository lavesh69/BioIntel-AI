from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from ..platform import Conflict, Denied, EducationError, Missing, ident, now
from .base import STAFF_ROLES, Phase30Base, decode_json, encode_json, normalized_key

MASTERY_STATES = (
    "not_introduced",
    "introduced",
    "developing",
    "practising",
    "proficient",
    "mastered",
    "at_risk_of_decay",
    "needs_reassessment",
)
EVIDENCE_TYPES = {
    "exposure",
    "practice",
    "assignment",
    "quiz",
    "examination",
    "virtual_lab",
    "teacher_feedback",
    "self_assessment",
}


class MasteryMixin(Phase30Base):
    def ensure_mastery_policy(
        self,
        actor: str,
        institution_id: str,
        *,
        name: str = "explainable-rule-mastery",
        version: str = "1.0.0",
        minimum_evidence: int = 3,
        configuration: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._require(actor, institution_id, "staff")
        if minimum_evidence < 1 or minimum_evidence > 100:
            raise EducationError("Minimum evidence must be between 1 and 100.")
        policy_id = ident("masterypolicy")
        timestamp = now()
        config = configuration or {
            "correctness_weight": 0.55,
            "confidence_weight": 0.10,
            "difficulty_weight": 0.15,
            "practical_weight": 0.10,
            "examination_weight": 0.10,
            "hint_penalty": 0.05,
            "decay_days": 90,
            "validated_ai_model": False,
        }
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_p30_mastery_policies
                VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(institution_id,name,version) DO UPDATE SET
                minimum_evidence=excluded.minimum_evidence,
                configuration_json=excluded.configuration_json,state='active'""",
                (
                    policy_id,
                    institution_id,
                    normalized_key(name),
                    "explainable_rule_based",
                    version,
                    int(minimum_evidence),
                    encode_json(config),
                    "active",
                    actor,
                    timestamp,
                ),
            )
        return self._one(
            """SELECT * FROM education_p30_mastery_policies
            WHERE institution_id=? AND name=? AND version=?""",
            (institution_id, normalized_key(name), version),
        ) or {}

    def create_concept(
        self,
        actor: str,
        institution_id: str,
        *,
        key: str,
        name: str,
        subject_id: str = "",
        description: str = "",
        learning_outcomes: list[str] | None = None,
        skill_keys: list[str] | None = None,
    ) -> dict[str, Any]:
        self._require(actor, institution_id, "staff")
        concept_key = normalized_key(key)
        if subject_id:
            subject = self._one(
                "SELECT institution_id FROM subjects WHERE id=?",
                (subject_id,),
            )
            if not subject or subject["institution_id"] != institution_id:
                raise Denied("Concept subject must belong to the same institution.")
        concept_id = ident("concept")
        timestamp = now()
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_p30_concepts
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(institution_id,key) DO UPDATE SET
                name=excluded.name,description=excluded.description,
                subject_id=excluded.subject_id,
                learning_outcomes_json=excluded.learning_outcomes_json,
                skill_keys_json=excluded.skill_keys_json,state='active',
                updated_at=excluded.updated_at""",
                (
                    concept_id,
                    institution_id,
                    subject_id,
                    concept_key,
                    name.strip(),
                    description,
                    encode_json(learning_outcomes or []),
                    encode_json(skill_keys or []),
                    "active",
                    actor,
                    timestamp,
                    timestamp,
                ),
            )
        self._audit(actor, institution_id, "concept_saved", "concept", concept_key)
        return self._one(
            "SELECT * FROM education_p30_concepts WHERE institution_id=? AND key=?",
            (institution_id, concept_key),
        ) or {}

    def _concept_graph(self, institution_id: str) -> dict[str, set[str]]:
        graph: dict[str, set[str]] = {}
        for row in self._all(
            """SELECT source_concept_id,target_concept_id FROM education_p30_concept_edges
            WHERE institution_id=? AND relation='prerequisite'""",
            (institution_id,),
        ):
            graph.setdefault(str(row["source_concept_id"]), set()).add(
                str(row["target_concept_id"])
            )
        return graph

    @staticmethod
    def _reachable(graph: dict[str, set[str]], start: str, target: str) -> bool:
        stack = [start]
        visited: set[str] = set()
        while stack:
            current = stack.pop()
            if current == target:
                return True
            if current in visited:
                continue
            visited.add(current)
            stack.extend(graph.get(current, ()))
        return False

    def link_concepts(
        self,
        actor: str,
        institution_id: str,
        source_concept_id: str,
        target_concept_id: str,
        *,
        relation: str = "prerequisite",
        weight: float = 1.0,
        policy_version: str = "1.0.0",
    ) -> dict[str, Any]:
        self._require(actor, institution_id, "staff")
        source = self._tenant_row(
            "education_p30_concepts",
            source_concept_id,
            institution_id,
        )
        target = self._tenant_row(
            "education_p30_concepts",
            target_concept_id,
            institution_id,
        )
        if source["id"] == target["id"]:
            raise Conflict("A concept cannot depend on itself.")
        relation_key = normalized_key(relation)
        if relation_key not in {"prerequisite", "subconcept", "related", "mastery_dependency"}:
            raise EducationError("Unsupported concept relationship.")
        if relation_key == "prerequisite":
            graph = self._concept_graph(institution_id)
            graph.setdefault(source_concept_id, set()).add(target_concept_id)
            if self._reachable(graph, target_concept_id, source_concept_id):
                raise Conflict("Concept relationship would create a prerequisite cycle.")
        edge_id = ident("conceptedge")
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_p30_concept_edges
                VALUES(?,?,?,?,?,?,?,?,?)
                ON CONFLICT(source_concept_id,target_concept_id,relation,policy_version)
                DO UPDATE SET weight=excluded.weight,created_by=excluded.created_by""",
                (
                    edge_id,
                    institution_id,
                    source_concept_id,
                    target_concept_id,
                    relation_key,
                    max(0.0, min(10.0, float(weight))),
                    policy_version,
                    actor,
                    now(),
                ),
            )
        return self._one(
            """SELECT * FROM education_p30_concept_edges
            WHERE source_concept_id=? AND target_concept_id=?
            AND relation=? AND policy_version=?""",
            (source_concept_id, target_concept_id, relation_key, policy_version),
        ) or {}

    def map_concept_resource(
        self,
        actor: str,
        institution_id: str,
        concept_id: str,
        *,
        resource_type: str,
        resource_id: str,
        weight: float = 1.0,
        verified: bool = False,
    ) -> dict[str, Any]:
        self._require(actor, institution_id, "staff")
        self._tenant_row("education_p30_concepts", concept_id, institution_id)
        allowed = {
            "course",
            "lecture",
            "question",
            "assignment",
            "virtual_lab",
            "scientific_paper",
            "skill",
        }
        resource = normalized_key(resource_type)
        if resource not in allowed:
            raise EducationError("Unsupported concept resource type.")
        mapping_id = ident("conceptmap")
        timestamp = now()
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_p30_concept_mappings
                VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(concept_id,resource_type,resource_id) DO UPDATE SET
                weight=excluded.weight,verified=excluded.verified,
                verified_by=excluded.verified_by,updated_at=excluded.updated_at""",
                (
                    mapping_id,
                    institution_id,
                    concept_id,
                    resource,
                    str(resource_id),
                    max(0.0, min(10.0, float(weight))),
                    int(verified),
                    actor if verified else "",
                    timestamp,
                    timestamp,
                ),
            )
        return self._one(
            """SELECT * FROM education_p30_concept_mappings
            WHERE concept_id=? AND resource_type=? AND resource_id=?""",
            (concept_id, resource, str(resource_id)),
        ) or {}

    def record_mastery_evidence(
        self,
        actor: str,
        institution_id: str,
        student_id: str,
        concept_id: str,
        *,
        evidence_type: str,
        correctness: float,
        confidence: float = 0,
        difficulty: float = 0.5,
        hint_use: int = 0,
        time_seconds: float = 0,
        practical_score: float | None = None,
        examination_score: float | None = None,
        self_assessment: float | None = None,
        source_id: str = "",
        occurred_at: str = "",
    ) -> dict[str, Any]:
        roles = self._require(actor, institution_id, "member")
        if actor != student_id and not roles.intersection(STAFF_ROLES):
            raise Denied("Mastery evidence access denied.")
        self._tenant_row("education_p30_concepts", concept_id, institution_id)
        kind = normalized_key(evidence_type)
        if kind not in EVIDENCE_TYPES:
            raise EducationError("Unsupported mastery evidence type.")
        values = [correctness, confidence, difficulty]
        if any(float(value) < 0 or float(value) > 1 for value in values):
            raise EducationError("Correctness, confidence and difficulty must be 0–1.")
        event_id = ident("masteryevent")
        timestamp = occurred_at or now()
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_p30_mastery_events
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    event_id,
                    institution_id,
                    student_id,
                    concept_id,
                    kind,
                    float(correctness),
                    float(confidence),
                    float(difficulty),
                    max(0, int(hint_use)),
                    max(0.0, float(time_seconds)),
                    practical_score,
                    examination_score,
                    self_assessment,
                    source_id,
                    timestamp,
                    actor,
                ),
            )
        self.recompute_mastery(actor, institution_id, student_id, concept_id)
        return self._one(
            "SELECT * FROM education_p30_mastery_events WHERE id=?",
            (event_id,),
        ) or {}

    def recompute_mastery(
        self,
        actor: str,
        institution_id: str,
        student_id: str,
        concept_id: str,
        *,
        policy_name: str = "explainable-rule-mastery",
        policy_version: str = "1.0.0",
    ) -> dict[str, Any]:
        roles = self._require(actor, institution_id, "member")
        if actor != student_id and not roles.intersection(STAFF_ROLES):
            raise Denied("Mastery record access denied.")
        policy = self._one(
            """SELECT * FROM education_p30_mastery_policies
            WHERE institution_id=? AND name=? AND version=? AND state='active'""",
            (institution_id, normalized_key(policy_name), policy_version),
        )
        if not policy:
            if not roles.intersection(STAFF_ROLES):
                raise Missing("Mastery policy has not been configured.")
            policy = self.ensure_mastery_policy(
                actor,
                institution_id,
                name=policy_name,
                version=policy_version,
            )
        events = self._all(
            """SELECT * FROM education_p30_mastery_events
            WHERE institution_id=? AND student_id=? AND concept_id=?
            ORDER BY occurred_at""",
            (institution_id, student_id, concept_id),
        )
        config = decode_json(policy["configuration_json"], {})
        count = len(events)
        explanation = ["RULE_BASED_NOT_VALIDATED_AI"]
        if not count:
            score = 0.0
            state = "not_introduced"
            last_at = now()
            explanation.append("NO_EVIDENCE")
        else:
            weighted = []
            for index, event in enumerate(events, start=1):
                recency_weight = 0.5 + 0.5 * index / count
                value = (
                    float(event["correctness"]) * float(config.get("correctness_weight", 0.55))
                    + float(event["confidence"]) * float(config.get("confidence_weight", 0.10))
                    + float(event["difficulty"]) * float(config.get("difficulty_weight", 0.15))
                )
                if event["practical_score"] is not None:
                    value += (
                        float(event["practical_score"])
                        / 100
                        * float(config.get("practical_weight", 0.10))
                    )
                if event["examination_score"] is not None:
                    value += (
                        float(event["examination_score"])
                        / 100
                        * float(config.get("examination_weight", 0.10))
                    )
                value -= min(0.25, int(event["hint_use"]) * float(config.get("hint_penalty", 0.05)))
                weighted.append((max(0.0, min(1.0, value)), recency_weight))
            score = round(
                sum(value * weight for value, weight in weighted)
                / sum(weight for _, weight in weighted),
                4,
            )
            last_at = str(events[-1]["occurred_at"])
            minimum = int(policy["minimum_evidence"])
            if count < minimum:
                state = "introduced" if count == 1 else "developing"
                explanation.append("MINIMUM_EVIDENCE_NOT_MET")
            elif score < 0.45:
                state = "needs_reassessment"
                explanation.append("LOW_WEIGHTED_EVIDENCE")
            elif score < 0.60:
                state = "practising"
                explanation.append("PRACTICE_RECOMMENDED")
            elif score < 0.78:
                state = "proficient"
                explanation.append("PROFICIENT_THRESHOLD")
            else:
                state = "mastered"
                explanation.append("MASTERY_THRESHOLD")
            try:
                last_dt = datetime.fromisoformat(last_at.replace("Z", "+00:00"))
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=timezone.utc)
                age_days = (datetime.now(timezone.utc) - last_dt).days
            except ValueError:
                age_days = 0
            if (
                state == "mastered"
                and age_days >= int(config.get("decay_days", 90))
            ):
                state = "at_risk_of_decay"
                explanation.append("EVIDENCE_DECAY_WINDOW")
        existing = self._one(
            """SELECT * FROM education_p30_mastery_records
            WHERE student_id=? AND concept_id=? AND policy_id=?""",
            (student_id, concept_id, policy["id"]),
        )
        record_id = str(existing["id"]) if existing else ident("mastery")
        version = int(existing["version"]) + 1 if existing else 1
        timestamp = now()
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_p30_mastery_records
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(student_id,concept_id,policy_id) DO UPDATE SET
                score=excluded.score,state=excluded.state,
                evidence_count=excluded.evidence_count,
                last_evidence_at=excluded.last_evidence_at,
                explanation_codes_json=excluded.explanation_codes_json,
                version=excluded.version,updated_at=excluded.updated_at""",
                (
                    record_id,
                    institution_id,
                    student_id,
                    concept_id,
                    policy["id"],
                    score,
                    state,
                    count,
                    last_at,
                    encode_json(explanation),
                    str((existing or {}).get("teacher_override", "")),
                    str((existing or {}).get("student_feedback", "")),
                    int((existing or {}).get("opted_out", 0)),
                    version,
                    str((existing or {}).get("created_at", timestamp)),
                    timestamp,
                ),
            )
        return self._one(
            """SELECT * FROM education_p30_mastery_records
            WHERE student_id=? AND concept_id=? AND policy_id=?""",
            (student_id, concept_id, policy["id"]),
        ) or {}

    def recommend_next(
        self,
        actor: str,
        institution_id: str,
        student_id: str,
        concept_id: str,
    ) -> dict[str, Any]:
        roles = self._require(actor, institution_id, "member")
        if actor != student_id and not roles.intersection(STAFF_ROLES):
            raise Denied("Adaptive recommendation access denied.")
        mastery = self._one(
            """SELECT r.*,p.name policy_name,p.version policy_version,
            p.minimum_evidence FROM education_p30_mastery_records r
            JOIN education_p30_mastery_policies p ON p.id=r.policy_id
            WHERE r.institution_id=? AND r.student_id=? AND r.concept_id=?
            ORDER BY r.updated_at DESC LIMIT 1""",
            (institution_id, student_id, concept_id),
        )
        if not mastery:
            raise Missing("Mastery evidence must be recorded before recommendation.")
        if mastery["opted_out"]:
            raise Denied("Student opted out of adaptive recommendations.")
        mappings = self._all(
            """SELECT * FROM education_p30_concept_mappings
            WHERE concept_id=? ORDER BY verified DESC,weight DESC LIMIT 20""",
            (concept_id,),
        )
        if int(mastery["evidence_count"]) < int(mastery["minimum_evidence"]):
            recommendation_type = "diagnostic_assessment"
            codes = ["MINIMUM_EVIDENCE_NOT_MET", "DIAGNOSTIC_REQUIRED"]
        elif mastery["state"] in {"needs_reassessment", "developing", "practising"}:
            recommendation_type = "remediation"
            codes = ["MASTERY_BELOW_PROFICIENT", "PREREQUISITE_RECOVERY"]
        elif mastery["state"] == "at_risk_of_decay":
            recommendation_type = "spaced_revision"
            codes = ["EVIDENCE_DECAY_WINDOW", "REASSESSMENT_DUE"]
        else:
            recommendation_type = "enrichment"
            codes = ["MASTERY_THRESHOLD_MET", "NEXT_CONCEPT_READY"]
        selected = mappings[0] if mappings else {}
        explanation = (
            f"Rule policy {mastery['policy_name']} {mastery['policy_version']} "
            f"selected {recommendation_type} from {mastery['evidence_count']} evidence events "
            f"and mastery score {float(mastery['score']):.3f}."
        )
        recommendation_id = ident("recommendation")
        timestamp = now()
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_p30_adaptive_recommendations
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    recommendation_id,
                    institution_id,
                    student_id,
                    concept_id,
                    recommendation_type,
                    str(selected.get("resource_type", "")),
                    str(selected.get("resource_id", "")),
                    encode_json(codes),
                    explanation,
                    encode_json(
                        {
                            "score": mastery["score"],
                            "state": mastery["state"],
                            "evidence_count": mastery["evidence_count"],
                        }
                    ),
                    mastery["policy_name"],
                    mastery["policy_version"],
                    "active",
                    "pending",
                    "",
                    "",
                    None,
                    timestamp,
                    timestamp,
                ),
            )
        return self._tenant_row(
            "education_p30_adaptive_recommendations",
            recommendation_id,
            institution_id,
        )

    def review_recommendation(
        self,
        actor: str,
        recommendation_id: str,
        *,
        decision: str,
        student_feedback: str = "",
    ) -> dict[str, Any]:
        row = self._tenant_row(
            "education_p30_adaptive_recommendations",
            recommendation_id,
        )
        institution_id = str(row["institution_id"])
        self._require(actor, institution_id, "staff")
        if decision not in {"approved", "corrected", "dismissed"}:
            raise EducationError("Unsupported recommendation review decision.")
        with self.db.connection() as db:
            db.execute(
                """UPDATE education_p30_adaptive_recommendations
                SET teacher_review_state=?,teacher_id=?,student_feedback=?,
                state=CASE WHEN ?='dismissed' THEN 'dismissed' ELSE state END,
                updated_at=? WHERE id=?""",
                (
                    decision,
                    actor,
                    student_feedback,
                    decision,
                    now(),
                    recommendation_id,
                ),
            )
        return self._tenant_row(
            "education_p30_adaptive_recommendations",
            recommendation_id,
            institution_id,
        )

    def schedule_review(
        self,
        actor: str,
        institution_id: str,
        student_id: str,
        concept_id: str,
        *,
        algorithm: str = "sm2",
        quality: int = 3,
    ) -> dict[str, Any]:
        roles = self._require(actor, institution_id, "member")
        if actor != student_id and not roles.intersection(STAFF_ROLES):
            raise Denied("Review scheduling access denied.")
        algorithm_key = normalized_key(algorithm)
        if algorithm_key not in {"basic_interval", "sm2", "mastery_adjusted"}:
            raise EducationError("Unsupported spaced-repetition algorithm.")
        if quality < 0 or quality > 5:
            raise EducationError("Review quality must be 0–5.")
        previous = self._one(
            """SELECT * FROM education_p30_review_schedule
            WHERE student_id=? AND concept_id=? AND algorithm=? AND algorithm_version='1.0'""",
            (student_id, concept_id, algorithm_key),
        )
        repetitions = int((previous or {}).get("repetitions", 0))
        easiness = float((previous or {}).get("easiness", 2.5))
        if algorithm_key == "basic_interval":
            interval = [1, 3, 7, 14, 30][min(repetitions, 4)]
        else:
            if quality < 3:
                repetitions = 0
                interval = 1
            else:
                repetitions += 1
                interval = 1 if repetitions == 1 else 6 if repetitions == 2 else round(
                    float((previous or {}).get("interval_days", 6)) * easiness
                )
            easiness = max(
                1.3,
                easiness + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)),
            )
            if algorithm_key == "mastery_adjusted":
                mastery = self._one(
                    """SELECT score FROM education_p30_mastery_records
                    WHERE student_id=? AND concept_id=? ORDER BY updated_at DESC LIMIT 1""",
                    (student_id, concept_id),
                )
                if mastery:
                    interval = max(1, round(interval * (0.75 + float(mastery["score"]))))
        next_at = (datetime.now(timezone.utc) + timedelta(days=interval)).isoformat()
        schedule_id = str((previous or {}).get("id") or ident("review"))
        timestamp = now()
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_p30_review_schedule
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(student_id,concept_id,algorithm,algorithm_version)
                DO UPDATE SET interval_days=excluded.interval_days,
                easiness=excluded.easiness,repetitions=excluded.repetitions,
                next_review_at=excluded.next_review_at,state='scheduled',
                updated_at=excluded.updated_at""",
                (
                    schedule_id,
                    institution_id,
                    student_id,
                    concept_id,
                    algorithm_key,
                    "1.0",
                    interval,
                    round(easiness, 4),
                    repetitions,
                    next_at,
                    "scheduled",
                    str((previous or {}).get("created_at", timestamp)),
                    timestamp,
                ),
            )
        return self._one(
            """SELECT * FROM education_p30_review_schedule
            WHERE student_id=? AND concept_id=? AND algorithm=? AND algorithm_version='1.0'""",
            (student_id, concept_id, algorithm_key),
        ) or {}
