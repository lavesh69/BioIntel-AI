# Phase 35 Research Safety Report

## Enforced boundaries

- Project, tenant, dataset, compute-run, Digital Twin, evidence, and scientific-tool
  permissions are checked before a task is stored.
- Unsafe clinical, autonomous, shell, ethics, publication, IP, permission-change,
  deletion, paid-compute, and external-communication requests are persistently
  refused and audited.
- Every agent draft requires a second authorized human review. The requester cannot
  self-approve.
- Hypotheses cannot enter “Approved for Testing” without a second human and cannot
  ever enter a “scientifically proven” state.
- Experiment plans cannot grant ethics approval. They preserve specialist-review
  flags and may only link an existing Phase 34 approval-record asset as
  `external_record_linked_not_verified_by_biointel`.
- Workflow-agent plans do not execute compute. A reviewed task, a separate
  run-specific approval, and a second human decision are required before the local
  approved worker can be called.
- Biomarker and drug-target outputs explicitly avoid clinical biomarker claims and
  therapeutic recommendations.
- Research-integrity output creates metadata flags and explicitly never accuses
  misconduct; human investigation is required.

## Verified negative cases

Focused tests verified unsafe-treatment refusal, cross-tenant evidence rejection,
self-approval rejection, scientifically-proven state rejection, BioIntel ethics
approval rejection, compute denial before explicit approval, overclaim detection,
and non-accusatory integrity behavior.

## Unvalidated areas

No live literature/retraction service, patent database, external AI model, cloud
provider, paid compute, clinical system, real patient data, institutional ethics
board, manuscript system, email, or external communication channel was used.
Consequently no external source completeness, legal novelty, clinical validity,
security certification, scientific correctness, or production readiness claim is
made by this report.
