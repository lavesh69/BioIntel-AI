from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DOCUMENTS: dict[str, str] = {
    "00_READ_ME_FIRST.md": """# Clinical & Pharmaceutical Validation Execution Pack

This pack is intentionally blank and must be completed with authentic sponsor, site,
quality, laboratory and clinical evidence. It does not certify BioIntel AI.

Required execution order:
1. Approve intended use and prohibited uses.
2. Approve the validation master plan, user requirements and risk file.
3. Approve/preregister the protocol before outcomes are available.
4. Qualify independent sites and train personnel.
5. Freeze model, dataset, code, environment and feature specification.
6. Lock blinded predictions before outcomes.
7. Reconcile outcomes, analyze predefined endpoints and report every failure.
8. Resolve deviations/CAPA and obtain independent QA/scientific approval.
9. Sign the validation summary and pass the claim-specific release gate.
""",
    "01_VALIDATION_MASTER_PLAN.md": """# Validation Master Plan

## Document control
- Document ID:
- Version:
- Owner:
- Quality approver:
- Effective date:

## Intended use and decision context

## System boundary and interfaces

## Regulatory/GxP applicability assessment

## Validation strategy
- Installation qualification (IQ):
- Operational qualification (OQ):
- Performance qualification (PQ):
- Scientific/analytical validation:
- Independent external validation:
- Prospective validation:

## Roles and segregation of duties

## Deliverables and acceptance criteria

## Deviations, CAPA and change control

## Release and periodic review
""",
    "02_USER_REQUIREMENTS_SPECIFICATION.md": """# User Requirements Specification

| Requirement ID | Requirement | Risk | Verification method | Acceptance criterion | Owner |
|---|---|---|---|---|---|
| URS-001 | Intended use is displayed and enforced | High | Inspection/test | Prohibited claims are blocked | |
| URS-002 | Model/data/code/environment hashes are frozen | High | Test | SHA-256 values are immutable | |
| URS-003 | Predictions are locked before outcomes | High | Test | Timestamp and audit proof present | |
| URS-004 | Audit trail is tamper-evident | High | Challenge test | Tampering is detected | |
| URS-005 | Validation dossier is checksum-verifiable | High | Verification | All manifest hashes pass | |
""",
    "03_RISK_MANAGEMENT_FILE.md": """# Risk Management File

| Hazard ID | Hazardous situation | Harm | Initial risk | Control | Verification | Residual risk | Acceptance |
|---|---|---|---|---|---|---|---|
| RSK-001 | Unvalidated prediction used for patient care | Incorrect decision | Critical | Research-only default and claim gate | UI/API negative test | | |
| RSK-002 | Data leakage inflates performance | False confidence | High | Entity/scaffold/temporal leakage audits | Independent validation | | |
| RSK-003 | Model changes after protocol approval | Invalid prospective result | High | Immutable model freeze | Hash verification | | |
| RSK-004 | Outcome visible before prediction lock | Biased validation | High | Prediction timestamp and audit chain | Reconciliation test | | |
| RSK-005 | Site or subgroup performance failure hidden | Unequal performance | High | Predefined subgroup analysis | Statistical review | | |
""",
    "04_CLINICAL_EVALUATION_PLAN.md": """# Clinical Evaluation Plan

## Intended use, target population and users
## State of the art and clinical context
## Clinical association / scientific validity
## Analytical and technical performance
## Clinical performance endpoints
## External and prospective validation design
## Subgroup, fairness and site-heterogeneity analyses
## Human factors and workflow integration
## Benefit-risk and limitations
## Post-deployment performance monitoring
""",
    "05_ANALYTICAL_VALIDATION_PROTOCOL.md": """# Analytical Validation Protocol

## Protocol identifiers and approvals
## Frozen model, dataset, code, environment and feature specification hashes
## Primary endpoint and success criterion
## Sample size and power
## Sites, assays, controls, replicates and acceptance criteria
## Blinding, randomization and sample-code management
## Statistical analysis plan
- Confidence intervals
- Calibration
- Sensitivity/specificity or regression error
- Missing data
- Multiple testing
- Subgroup/site analysis
- Drift and out-of-distribution analysis
## Deviations and amendment policy
## Negative-result reporting policy
""",
    "06_IQ_OQ_PQ_PROTOCOL.md": """# IQ / OQ / PQ Protocol

## IQ — Installation Qualification
- Approved hardware/software inventory
- Version and package lock verification
- Database migration verification
- Backup/restore configuration
- Time synchronization
- Security configuration

## OQ — Operational Qualification
- Access and role tests
- Audit-trail challenge test
- Electronic-signature verification
- Input validation and error handling
- Model/data hash enforcement
- Prediction-before-outcome sequencing
- Export/dossier checksum verification

## PQ — Performance Qualification
- Representative end-to-end workflows
- Site/user acceptance
- Load and reliability under intended conditions
- Recovery and business continuity
- Scientific acceptance criteria

## Deviations and final disposition
""",
    "07_TRACEABILITY_MATRIX.csv": "requirement_id,risk_id,design_reference,test_id,test_result,evidence_reference,reviewer,status\n",
    "08_SITE_QUALIFICATION_CHECKLIST.csv": "site_id,organization,independent,accreditation,personnel_qualified,equipment_qualified,sop_alignment,data_transfer_test,qa_approval,status\n",
    "09_PREDICTION_LOCK_MANIFEST.csv": "batch_id,site_id,model_sha256,dataset_sha256,code_sha256,environment_sha256,feature_spec_sha256,predictions_sha256,sample_count,blinded,locked_at,locked_by\n",
    "10_OUTCOME_RECONCILIATION.csv": "prediction_batch_id,outcome_batch_id,endpoint_name,prediction_count,outcome_count,adjudicated,received_at,analysis_included,exclusion_reason\n",
    "11_DEVIATION_CAPA_LOG.csv": "event_id,event_type,severity,title,root_cause,action_plan,owner,due_date,status,effectiveness_verified,qa_approval\n",
    "12_TRAINING_MATRIX.csv": "person_id,role,curriculum_id,assigned_at,completed_at,expires_at,result,evidence_reference\n",
    "13_VALIDATION_SUMMARY_REPORT.md": """# Validation Summary Report

## Executive conclusion
## Intended use and exact validated configuration
## Protocol compliance
## IQ/OQ/PQ results
## Analytical, external and prospective results
## Site and subgroup performance
## Deviations, CAPA and unresolved risks
## Limitations and prohibited uses
## Release recommendation
## Approvals
- Scientific reviewer:
- Quality approver:
- Sponsor authorization:
""",
    "14_POST_DEPLOYMENT_MONITORING_PLAN.md": """# Post-Deployment Monitoring Plan

## Monitored population and use environment
## Performance, calibration and drift indicators
## Site/subgroup surveillance
## Incident, complaint and adverse-impact intake
## Alert thresholds and escalation
## Revalidation triggers
## Periodic review frequency
""",
    "15_EVIDENCE_INTAKE_MANIFEST.csv": "evidence_id,category,evidence_type,reference,source_organization,independent,sha256,status,reviewer,reviewed_at\n",
    "16_DATA_PRIVACY_SECURITY_ASSESSMENT.md": """# Data Privacy & Security Assessment

## Data classification and lawful basis
## Personal/health data inventory and minimization
## De-identification, pseudonymization and re-identification risk
## Access control and segregation of duties
## Encryption, key management and secure transfer
## Retention, deletion and subject-rights workflow
## Threat model, vulnerability management and incident response
## Cross-border transfer and processor/subprocessor assessment
## Approval and residual-risk acceptance
""",
    "17_HUMAN_FACTORS_USABILITY_PROTOCOL.md": """# Human Factors & Usability Validation Protocol

## Intended users, environments and critical tasks
## Use-related risk analysis
## Training assumptions and user-interface controls
## Formative evaluation findings
## Summative validation design
## Representative participants and scenarios
## Critical-task acceptance criteria
## Use errors, close calls and root-cause analysis
## Residual use-related risk and approval
""",
    "18_SUPPLIER_SERVICE_PROVIDER_QUALIFICATION.csv": "supplier_id,service_or_component,criticality,qualification_basis,security_review,quality_agreement,change_notification,sla,periodic_review_date,status,approver\n",
    "19_MODEL_CHANGE_CONTROL_PCCP.md": """# Model Change Control & Predetermined Change Plan

## Approved model/configuration baseline
## Anticipated modifications and boundaries
## Change categories requiring revalidation
## Data acceptance, retraining and leakage controls
## Verification and validation methods
## Performance, calibration, site and subgroup acceptance criteria
## Rollback, versioning and traceability
## Regulatory/quality notification assessment
## Approval before deployment
""",
    "20_SAFETY_INCIDENT_COMPLAINT_LOG.csv": "record_id,record_type,received_at,reporter,site,product_version,event_description,potential_harm,severity,reportability_assessment,containment,investigation,capa_id,status,closed_at,qa_approver\n",
    "21_SITE_SUBGROUP_STATISTICAL_REPORT.md": """# Site & Subgroup Statistical Report

## Frozen protocol and analysis-plan references
## Dataset reconciliation and exclusions
## Primary endpoint with confidence interval
## Per-site performance and heterogeneity
## Predefined demographic/clinical/technical subgroups
## Calibration, missing data and sensitivity analyses
## Multiplicity and exploratory-analysis labelling
## Failures, limitations and negative results
## Independent statistical and quality review
""",
    "22_SOFTWARE_CONFIGURATION_INDEX.csv": "configuration_item,version,sha256,supplier,license,approved_source,validation_reference,known_anomalies,cybersecurity_status,release_status\n",
    "23_DATA_MANAGEMENT_PLAN.md": """# Validation Data Management Plan

## Data sources, ownership and permitted use
## Sample identifiers, blinding and reconciliation
## Collection, transfer, validation and query management
## Dataset/version/hash freeze
## Missing data, exclusions and protocol deviations
## Access, audit, backup, retention and archival
## Statistical dataset derivation and traceability
## Final lock, unlock authorization and disposition
""",
    "24_REGULATORY_APPLICABILITY_ASSESSMENT.md": """# Regulatory & Quality Applicability Assessment

## Intended use, claims and jurisdictions
## Product classification and decision rationale
## Medical-device / clinical-decision-support applicability
## GxP, electronic-record and electronic-signature applicability
## Clinical investigation / ethics applicability
## Privacy, cybersecurity and data-localization applicability
## Required submissions, registrations or authority interactions
## Standards/guidance register and gap assessment
## Quality and regulatory approvals
""",
}


def build_validation_template_pack(
    destination: str | Path, *, metadata: dict[str, Any] | None = None
) -> Path:
    output = Path(destination).resolve()
    output.mkdir(parents=True, exist_ok=True)
    for relative, content in DOCUMENTS.items():
        (output / relative).write_text(content, encoding="utf-8", newline="")
    (output / "template_pack_metadata.json").write_text(
        json.dumps(
            {
                "schema": "biointel.clinical-pharma-template-pack.v1",
                "contains_real_validation_evidence": False,
                "certification_or_approval": False,
                "metadata": metadata or {},
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return output
