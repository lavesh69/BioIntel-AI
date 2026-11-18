# Phase 31–35 Database Schema

Migration ID: `education_phase31_to_35_research_platform_v1`

The migration is idempotent, transactional, restart-safe, and recorded in
`education_p35_migrations`. It creates 63 tables with tenant, owner, project, status,
timestamp, audit, and integrity fields as appropriate.

## Phase 32: secure synchronization

Fifteen tables cover trusted devices, revocable sessions, policies, consent, encrypted
endpoints, key versions, append-only journals, delivery state, entity state, conflicts,
file versions/chunks, and incidents.

Important integrity controls include unique idempotency keys, unique device/session
identifiers, foreign keys, explicit device states, encrypted token/configuration
storage, checksums, and conflict persistence.

## Phase 33: Biomedical Digital Twin

Fourteen tables cover projects, collaborators, data sources, observations, synthetic
generations, models, parameters, scenarios, simulations, validation, integrations,
learning activities, reviewed submissions, and audit events.

Simulation and validation records are immutable result evidence. Learning outcomes
remain pending until teacher/human review.

## Phase 34: Research Compute

Nineteen tables cover projects/members/assets, datasets/files/import history and
resumable sessions, approved tools, workflows/runs/quotas/steps/artifacts, reviews,
notes, handoffs, imported bundles, remote adapter configuration, and compute audit.

Workflow execution references approved tool identifiers rather than caller-supplied
commands. Run steps, checkpoints, artifacts, checksums, provenance, and review state
are persisted.

## Phase 35: scientific agents and discovery

Fifteen tables cover research workspaces, evidence, saved searches, agent definitions,
tasks, approvals, hypotheses, experiments, novelty searches, claim/evidence nodes and
edges, discovery workflows/steps, evaluations, and integrity audit.

Consequential actions require persisted approval. Hypothesis state transitions and
claim-evidence links remain auditable.

## Migration verification

Migration creation, repeated application, restart persistence, and cross-phase data
continuity passed the focused Phase 31–35 regression and cross-phase workflow suite.
The migration does not drop or rewrite pre-existing Phase 1–30 tables.
