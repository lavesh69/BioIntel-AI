from __future__ import annotations

from typing import Any

from ..platform import Denied, now
from .agents import AgentMixin
from .integration import IntegrationMixin
from .labs import LabMixin
from .mastery import MasteryMixin
from .pilot import PilotMixin
from .portfolio import PortfolioMixin
from .research import ResearchMixin
from .schema import MIGRATION_ID


class EducationEnterprisePlatform(
    PilotMixin,
    AgentMixin,
    LabMixin,
    MasteryMixin,
    ResearchMixin,
    PortfolioMixin,
    IntegrationMixin,
):
    """Connected Phase 23–30 services over the canonical Education database."""

    def __init__(self, platform: Any, *, root: str) -> None:
        super().__init__(platform, root=root)
        self.seed_agent_registry()
        self.seed_virtual_labs()
        self.seed_skills()

    def platform_snapshot(
        self,
        actor: str,
        institution_id: str,
    ) -> dict[str, Any]:
        roles = self._require(actor, institution_id, "member")
        student_view = not roles.intersection(
            {
                "platform_administrator",
                "institution_administrator",
                "principal",
                "dean",
                "registrar",
                "department_head",
                "subject_teacher",
                "class_teacher",
                "lecturer",
                "professor",
                "laboratory_instructor",
            }
        )
        mastery = self._all(
            """SELECT concept_id,score,state,evidence_count,updated_at
            FROM education_p30_mastery_records
            WHERE institution_id=? AND student_id=?
            ORDER BY updated_at DESC LIMIT 20""",
            (institution_id, actor),
        )
        recommendations = self._all(
            """SELECT id,concept_id,recommendation_type,explanation,state,created_at
            FROM education_p30_adaptive_recommendations
            WHERE institution_id=? AND student_id=? AND state='active'
            ORDER BY created_at DESC LIMIT 20""",
            (institution_id, actor),
        )
        labs = self._all(
            """SELECT id,experiment_id,state,current_step,updated_at
            FROM education_p30_lab_attempts
            WHERE institution_id=? AND student_id=?
            ORDER BY updated_at DESC LIMIT 20""",
            (institution_id, actor),
        )
        credentials = self._all(
            """SELECT id,credential_type,title,issued_at,expires_at,state
            FROM education_p30_credentials
            WHERE institution_id=? AND owner_id=?
            ORDER BY issued_at DESC LIMIT 20""",
            (institution_id, actor),
        )
        snapshot: dict[str, Any] = {
            "institution_id": institution_id,
            "actor": actor,
            "roles": sorted(roles),
            "mastery": mastery,
            "recommendations": recommendations,
            "virtual_labs": labs,
            "credentials": credentials,
            "generated_at": now(),
        }
        if not student_view:
            snapshot.update(
                {
                    "pilots": self._all(
                        """SELECT id,name,status,onboarding_percent,health_score,
                        blocker_count,readiness_decision,updated_at
                        FROM education_p30_pilots WHERE institution_id=?
                        ORDER BY updated_at DESC LIMIT 20""",
                        (institution_id,),
                    ),
                    "agent_tasks": self._all(
                        """SELECT id,agent_key,state,approval_state,requested_by,updated_at
                        FROM education_p30_agent_tasks WHERE institution_id=?
                        ORDER BY updated_at DESC LIMIT 20""",
                        (institution_id,),
                    ),
                    "support_tickets": self._all(
                        """SELECT id,module,severity,title,state,assigned_to,updated_at
                        FROM education_p30_support_tickets WHERE institution_id=?
                        ORDER BY updated_at DESC LIMIT 20""",
                        (institution_id,),
                    ),
                    "jobs": self._all(
                        """SELECT id,job_type,state,progress,retry_count,updated_at
                        FROM education_p30_jobs WHERE institution_id=?
                        ORDER BY updated_at DESC LIMIT 20""",
                        (institution_id,),
                    ),
                }
            )
        return snapshot

    def database_inventory(self) -> dict[str, Any]:
        with self.db.connection() as db:
            tables = [
                row[0]
                for row in db.execute(
                    """SELECT name FROM sqlite_master
                    WHERE type='table' AND name LIKE 'education_p30_%' ORDER BY name"""
                ).fetchall()
            ]
            indexes = [
                row[0]
                for row in db.execute(
                    """SELECT name FROM sqlite_master
                    WHERE type='index' AND name LIKE 'idx_p30_%' ORDER BY name"""
                ).fetchall()
            ]
            migrations = [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM education_migrations ORDER BY applied_at,id"
                ).fetchall()
            ]
        return {
            "migration": MIGRATION_ID,
            "tables": tables,
            "table_count": len(tables),
            "indexes": indexes,
            "index_count": len(indexes),
            "migrations": migrations,
        }

    def capability_matrix(self) -> dict[str, dict[str, Any]]:
        implemented = "IMPLEMENTED_AND_VERIFIED"
        external = "IMPLEMENTED_REQUIRES_EXTERNAL_VALIDATION"
        partial = "PARTIALLY_IMPLEMENTED"
        blocked = "BLOCKED_WITH_REASON"
        return {
            "phase23_pilot_lifecycle": {
                "status": implemented,
                "evidence": "Persistent lifecycle with guarded transitions, consent, onboarding and exports.",
            },
            "phase23_csv_xlsx_import": {
                "status": implemented,
                "evidence": "Templates, dry-run, row validation, digest confirmation and transactional commit.",
            },
            "phase23_observability_support": {
                "status": implemented,
                "evidence": "Structured health samples, diagnostics, audit-chain and persisted tickets.",
            },
            "phase23_real_500_5000_user_capacity": {
                "status": blocked,
                "reason": "Requires representative institution infrastructure and users; only scripts/profiles are local.",
            },
            "phase24_agent_runtime": {
                "status": implemented,
                "evidence": "Eight agents, tool allowlists, depth limits, approval checkpoints, evidence and audit.",
            },
            "phase24_external_ai_providers": {
                "status": external,
                "evidence": "Provider-independent task records exist; live provider credentials were not supplied.",
            },
            "phase25_virtual_lab": {
                "status": implemented,
                "evidence": "23 versioned experiments, attempts, validated steps, notebook, assessment and PDF export.",
            },
            "phase25_physical_accuracy": {
                "status": partial,
                "reason": "Selected exercises are calculation simulations; others are explicitly guided workflows.",
            },
            "phase26_mastery_adaptive_learning": {
                "status": implemented,
                "evidence": "Versioned rule policy, minimum evidence, explanations, teacher review and SM-2 scheduling.",
            },
            "phase26_validated_ai_mastery": {
                "status": blocked,
                "reason": "The implemented mastery model is explicitly rule-based and not a validated AI model.",
            },
            "phase27_research_to_education": {
                "status": implemented,
                "evidence": "Identifier-preserving papers, claims, citations, review, retraction warning and outbox publication.",
            },
            "phase27_live_metadata_providers": {
                "status": external,
                "evidence": "Crossref/PubMed/Europe PMC adapter contracts require real network credentials/validation.",
            },
            "phase28_portfolio_skills_credentials": {
                "status": implemented,
                "evidence": "Private portfolios, skill evidence, signed PDF credentials, verification, revocation and shares.",
            },
            "phase28_accreditation": {
                "status": blocked,
                "reason": "No national or international accreditation approval was supplied.",
            },
            "phase29_public_api_webhooks": {
                "status": implemented,
                "evidence": "Scoped API keys, rate limits, audit usage, HMAC signing, replay window and retries schema.",
            },
            "phase29_plugins_mcp": {
                "status": implemented,
                "evidence": "Declared permission grants, no unrestricted access, MCP read-only default and write approval.",
            },
            "phase29_live_lms_sso_storage": {
                "status": external,
                "evidence": "Adapters expose truthful configuration/live state and need real endpoints.",
            },
            "phase30_local_desktop": {
                "status": implemented,
                "evidence": "SQLite, local storage, local agent provider and zero mandatory cloud services.",
            },
            "phase30_institution_server": {
                "status": partial,
                "reason": "Configuration/validation profile exists; PostgreSQL, Redis and S3 drivers/infrastructure are optional.",
            },
            "phase30_enterprise_cluster": {
                "status": external,
                "evidence": "HA reference profile requires deployment infrastructure for validation.",
            },
            "phase30_formal_security_test": {
                "status": blocked,
                "reason": "Automated security controls are not a formal penetration test.",
            },
            "phase30_wcag_certification": {
                "status": blocked,
                "reason": "Accessible implementation checks do not constitute third-party WCAG certification.",
            },
            "institutional_pilot_acceptance": {
                "status": external,
                "evidence": "Pilot workflow exists; real institution sign-off is necessarily external.",
            },
        }

    def release_qualification(
        self,
        actor: str,
        institution_id: str,
    ) -> dict[str, Any]:
        self._require(actor, institution_id, "admin")
        inventory = self.database_inventory()
        audit = self.verify_audit_chain(institution_id)
        health = self.health_snapshot(actor, institution_id)
        matrix = self.capability_matrix()
        return {
            "migration": MIGRATION_ID,
            "database_quick_check": self.db.quick_check(),
            "phase30_tables": inventory["table_count"],
            "phase30_indexes": inventory["index_count"],
            "audit_chain": audit,
            "health": health,
            "capability_counts": {
                status: sum(
                    item["status"] == status for item in matrix.values()
                )
                for status in {
                    "IMPLEMENTED_AND_VERIFIED",
                    "IMPLEMENTED_REQUIRES_EXTERNAL_VALIDATION",
                    "PARTIALLY_IMPLEMENTED",
                    "BLOCKED_WITH_REASON",
                    "NOT_IMPLEMENTED",
                }
            },
            "capabilities": matrix,
            "qualified_at": now(),
        }

    def workflow_virtual_lab_to_credential(
        self,
        actor: str,
        attempt_id: str,
        *,
        concept_id: str,
        skill_key: str,
        credential_title: str,
    ) -> dict[str, Any]:
        attempt = self._tenant_row("education_p30_lab_attempts", attempt_id)
        institution_id = str(attempt["institution_id"])
        self._require(actor, institution_id, "staff")
        assessment = self._one(
            "SELECT * FROM education_p30_lab_assessments WHERE attempt_id=?",
            (attempt_id,),
        )
        if not assessment or float(assessment["total_score"]) < 60:
            raise Denied("A passing, instructor-reviewed practical assessment is required.")
        student_id = str(attempt["student_id"])
        evidence = self.record_mastery_evidence(
            actor,
            institution_id,
            student_id,
            concept_id,
            evidence_type="virtual_lab",
            correctness=float(assessment["total_score"]) / 100,
            confidence=0.8,
            difficulty=0.7,
            practical_score=float(assessment["total_score"]),
            source_id=attempt_id,
        )
        skill = self.add_skill_evidence(
            actor,
            institution_id,
            student_id,
            skill_key=skill_key,
            evidence_type="virtual_lab",
            evidence_id=attempt_id,
            proficiency="proficient",
            verify=True,
        )
        credential = self.issue_credential(
            actor,
            institution_id,
            student_id,
            credential_type="virtual_lab_micro_credential",
            title=credential_title,
            criteria={
                "minimum_practical_score": 60,
                "experiment_id": attempt["experiment_id"],
                "human_assessment_required": True,
            },
            evidence=[
                {
                    "type": "virtual_lab_assessment",
                    "id": assessment["id"],
                    "score": assessment["total_score"],
                    "verification_state": "assessed",
                },
                {
                    "type": "skill_evidence",
                    "id": skill["id"],
                    "verification_state": skill["verification_state"],
                },
            ],
        )
        portfolio = self.get_or_create_portfolio(
            student_id,
            institution_id,
        )
        portfolio_item = self.add_portfolio_item(
            student_id,
            str(portfolio["id"]),
            item_type="credential",
            title=credential_title,
            evidence_type="credential",
            evidence_id=str(credential["id"]),
        )
        return {
            "attempt": attempt,
            "assessment": assessment,
            "mastery_evidence": evidence,
            "skill_evidence": skill,
            "credential": credential,
            "portfolio_item": portfolio_item,
        }
