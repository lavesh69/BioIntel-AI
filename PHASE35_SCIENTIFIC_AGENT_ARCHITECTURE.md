# Phase 35 Scientific Agent Architecture

## Status

Implemented and locally verified with **10 focused tests passed**. The runtime is
a deterministic local extension of the Phase 24 agent model. It does not call an
external AI provider, scientific database, clinical system, or paid service.

## Runtime

`DiscoveryEcosystem` binds every workspace to one active Phase 34 research project
and tenant. It provides:

- a 12-agent, versioned permission registry;
- institution policy controls and project-bound dataset/compute access;
- registered local evidence, saved searches, citation ranking, stored retraction
  metadata, and explicit live-check boundaries;
- idempotent agent tasks, evidence checksums, Phase 24 parent-task references,
  provenance, uncertainty, novelty state, support references, human review, and
  append-only audit events;
- hypotheses, experiments, novelty screens, claim-evidence graphs, deterministic
  evaluation records, and a 16-step human-supervised discovery workflow.

## Implemented scientific agents

1. Literature Discovery
2. Evidence Synthesis
3. Hypothesis Generation
4. Experimental Design
5. Bioinformatics Workflow
6. Statistical Analysis
7. Systems Biology
8. Biomarker Discovery
9. Drug Target Prioritization
10. Reproducibility
11. Scientific Reviewer
12. Research Integrity

All outputs contain evidence tables, uncertainty, limitations, provenance, a
human-review requirement, and a non-clinical safety boundary. Literature searching
operates over registered local evidence only. Retraction status is stored metadata,
not a live external check.

## Human-supervised discovery workflow

The versioned workflow preserves the sequence from research question through
literature discovery, synthesis, hypothesis drafting, human hypothesis review,
experiment planning, ethics/safety metadata review, workflow drafting, human
execution approval, Research Compute, statistical/systems review,
reproducibility, scientific review, human interpretation, and draft report asset.

Agent steps require a matching completed and human-reviewed task. Human checkpoints
cannot advance without an explicit human approval flag. Every completed step stores
an artifact reference and provenance record.

## Cross-phase bindings

- Phase 24: optional parent task reference and shared permission/approval concepts.
- Phase 33: policy-allowlisted Digital Twin scenario references and non-clinical
  scenario drafts.
- Phase 34: project datasets, approved tools, run results, output checksums,
  reproducibility inspection, and second-human compute execution approval.

## Claim boundary

The system assists research ideation and analysis. It does not claim autonomous
discovery, definitive novelty, patent novelty, freedom to operate, clinical
validity, scientific proof, guaranteed correctness, diagnosis, treatment, ethics
approval, publication, manuscript submission, or misconduct.
