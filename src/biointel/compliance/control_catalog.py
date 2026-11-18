from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable


@dataclass(frozen=True)
class ControlDefinition:
    control_id: str
    domain: str
    title: str
    description: str
    standards: tuple[str, ...]
    required_evidence: tuple[str, ...]


CONTROL_CATALOG: tuple[ControlDefinition, ...] = (
    ControlDefinition(
        "REG-001",
        "Regulatory governance",
        "Intended use and regulatory scope",
        "Document the intended use, users, decisions supported, prohibited uses and applicable jurisdictions.",
        ("FDA Part 11 scope and application", "EU GxP computerized systems"),
        ("approved_intended_use", "regulatory_scope_assessment", "prohibited_use_statement"),
    ),
    ControlDefinition(
        "REG-002",
        "Regulatory governance",
        "Risk management",
        "Maintain traceable risks, controls, residual-risk acceptance and periodic review.",
        ("Quality risk management",),
        ("risk_register", "control_mapping", "residual_risk_approval"),
    ),
    ControlDefinition(
        "REG-003",
        "Validation lifecycle",
        "Requirements and traceability",
        "Trace user requirements to design, implementation, verification, release and change records.",
        ("Computerized-system validation",),
        ("urs", "traceability_matrix", "verification_results"),
    ),
    ControlDefinition(
        "REG-004",
        "Validation lifecycle",
        "Validated release",
        "Require approved validation evidence, known limitations and release authorization before regulated use.",
        ("Computerized-system validation", "FDA Part 11"),
        ("validation_plan", "validation_summary_report", "release_approval"),
    ),
    ControlDefinition(
        "REG-005",
        "Quality system",
        "Change control",
        "Assess, approve, test, deploy and review changes through a controlled lifecycle.",
        ("GxP change control",),
        ("change_request", "impact_assessment", "test_evidence", "deployment_approval"),
    ),
    ControlDefinition(
        "REG-006",
        "Quality system",
        "Deviation and CAPA",
        "Record deviations, root cause, corrective actions, preventive actions and effectiveness checks.",
        ("GxP quality system",),
        ("deviation", "root_cause", "capa", "effectiveness_check"),
    ),
    ControlDefinition(
        "REG-007",
        "Records management",
        "Retention and legal hold",
        "Apply record-class retention, disposition approval, legal hold and metadata persistence.",
        ("Electronic records", "Data retention"),
        ("retention_policy", "disposition_log", "legal_hold_procedure"),
    ),
    ControlDefinition(
        "REG-008",
        "Security and privacy",
        "Access, privacy and security",
        "Use least privilege, tenant isolation, encryption, auditability and documented incident response.",
        ("FDA Part 11 access controls", "Privacy and security governance"),
        ("access_review", "security_assessment", "incident_response_test"),
    ),
    ControlDefinition(
        "GXP-001",
        "Data integrity",
        "ALCOA+ records",
        "Ensure records are attributable, legible, contemporaneous, original, accurate, complete, consistent, enduring and available.",
        ("GxP data integrity",),
        ("record_owner", "timestamp", "source_hash", "version_history", "availability_test"),
    ),
    ControlDefinition(
        "GXP-002",
        "Data integrity",
        "Computer-generated audit trail",
        "Maintain a secure, time-ordered, tamper-evident audit trail for creation, change, review and deletion actions.",
        ("21 CFR 11.10(e)", "EU GxP data integrity"),
        ("audit_chain_verification", "audit_review", "clock_control"),
    ),
    ControlDefinition(
        "GXP-003",
        "Electronic signatures",
        "Electronic signature binding",
        "Bind signer identity, meaning, reason, timestamp and exact record version using a verifiable signature.",
        ("21 CFR Part 11 electronic signatures",),
        ("signature_policy", "signature_verification", "identity_proofing"),
    ),
    ControlDefinition(
        "GXP-004",
        "Procedures",
        "Controlled SOPs",
        "Version, approve, distribute and periodically review operating procedures.",
        ("GxP document control",),
        ("approved_sop", "distribution_record", "periodic_review"),
    ),
    ControlDefinition(
        "GXP-005",
        "People",
        "Role-based training",
        "Require effective training before personnel perform controlled tasks.",
        ("GxP training",),
        ("training_assignment", "completion_record", "effectiveness_assessment"),
    ),
    ControlDefinition(
        "GXP-006",
        "Operations",
        "Backup, restore and continuity",
        "Test backup integrity, restore procedures, recovery objectives and continuity plans.",
        ("GxP business continuity",),
        ("backup_log", "restore_test", "rto_rpo_approval", "continuity_exercise"),
    ),
    ControlDefinition(
        "GXP-007",
        "Suppliers",
        "Supplier qualification",
        "Assess critical providers, contracts, data responsibilities and ongoing performance.",
        ("GxP supplier management",),
        ("supplier_assessment", "quality_agreement", "supplier_review"),
    ),
    ControlDefinition(
        "GXP-008",
        "Operations",
        "Periodic system review",
        "Periodically reassess intended use, incidents, changes, access, performance, validation and obsolescence.",
        ("Computerized-system lifecycle",),
        ("periodic_review_report", "access_recertification", "validation_status_review"),
    ),
)


def controls(domain: str | None = None) -> list[dict[str, object]]:
    selected: Iterable[ControlDefinition] = CONTROL_CATALOG
    if domain:
        selected = (item for item in CONTROL_CATALOG if item.domain == domain)
    return [asdict(item) for item in selected]


def control_ids() -> tuple[str, ...]:
    return tuple(item.control_id for item in CONTROL_CATALOG)
