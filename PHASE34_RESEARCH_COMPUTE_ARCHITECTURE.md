# Phase 34 Research Compute Architecture

## Status

Implemented and locally verified on Windows with Python 3.11.9 and Streamlit 1.58.
The focused Phase 34 suite reports **10 passed**. This is internal technical
validation, not production-capacity, external-cluster, clinical, or scientific
validation.

## Local-first architecture

- `ResearchCompute` owns a SQLite-backed project, dataset, workflow, run, review,
  quota, audit, adapter, and reproducibility model.
- Research files and run artifacts are stored below the configured BioIntel user
  data directory. Database rows retain content hashes and relative artifact names.
- The native worker executes only an approved in-process handler selected by an
  immutable tool ID. Ordinary workflow definitions cannot contain command, shell,
  or executable fields.
- FastAPI routes live under `/phase34`; the Streamlit surface is
  `pages/350_Bioinformatics_Research_Compute.py`.

## Research workspace

Projects contain owner/institution identity, members, hypotheses, objectives,
milestones, issues, datasets, workflows, and runs. A governed project-asset
registry represents sample sheets, analyses, notebooks, reports, references,
approvals, publications, exports, issues, and milestones with versions and archive
state. Completed runs require reviewer approval before they can be published as a
project report.

## Dataset and large-file safety

- 22 research format classes are registered. Signature validation is bounded to
  4 KiB; hashing and native QC use streaming reads.
- DICOM handling is metadata/container identification only and performs no
  diagnostic interpretation.
- Imports use checksums, a 2 TiB per-file registration bound, unique storage
  identities, copy verification, support references, and import history.
- Resumable import sessions use encrypted source requests, 4 MiB chunks, partial
  files, byte budgets, checksum verification, pause/resume/cancel states, and
  scoped cleanup.
- ZIP run-bundle inspection rejects traversal, excessive entry count, excessive
  expanded size, oversized members, unsafe compression ratios, and CRC failure.

## Orchestration and governance

Run states cover queued, preparing, running, paused, retrying, completed, failed,
cancelled, partially completed, blocked, and awaiting-resources states. The local
worker enforces idempotency keys, atomic claims, resource/quota checks, format/tool
compatibility, cancellation, timeouts, retry limits, and verified checkpoint
recovery. Fairness is bounded through FIFO ordering within priority and per-user
queued/concurrent quotas.

GPU requests are recorded but rejected by the local worker because no GPU path was
validated. Remote adapter records are encrypted, allowlisted, template-restricted,
disabled by default, and labelled “Configured - External Validation Required.”
No Docker, Kubernetes, Slurm, SSH cluster, object storage, or institution worker
was contacted or validated.

## Scientific boundary

Results are research-support artifacts requiring human scientific review. They are
not diagnostic interpretations, clinical advice, verified novelty, or guaranteed
scientific conclusions. Studio, Shiro, and Discovery Agent handoffs are stored as
`review_required`; this phase does not automatically transmit or publish them.
