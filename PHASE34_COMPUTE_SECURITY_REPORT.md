# Phase 34 Compute Security Report

## Implemented controls

- approved/revocable tool registry with source, version, checksum, licence,
  parameter schema, input/output contracts, resource requirements, permission,
  validation, and administrator approval metadata;
- no ordinary-user arbitrary shell, command, or executable fields;
- acyclic workflow validation and format compatibility checks;
- idempotency keys and atomic database claims preventing duplicate run execution;
- tenant/project matching plus per-user resource, queue, and concurrency quotas;
- streaming inspection/hashing, resumable chunked imports, checksum verification,
  disk-space checks, bounded archive inspection, scoped temporary paths, partial
  states, cancellation, and recovery;
- encrypted remote credentials, HTTPS/SSH URI validation, exact host allowlist,
  restricted command templates, bounded resource metadata, redacted status;
- append-only compute audit events and review-gated publication/handoffs.

## Focused negative tests

The test suite rejected malformed signatures, unsupported formats, cross-project
or cross-tenant submission, unapproved tools, arbitrary commands, workflow cycles,
resource over-quota requests, unsupported GPU execution, tampered dataset files,
unauthorized cancellation, unreviewed publication, unsafe remote host selection,
and shell metacharacters.

## External validation boundary

No remote network connection, container daemon, Kubernetes cluster, Slurm
scheduler, SSH target, object store, GPU, production load, penetration test, or
clinical workflow was exercised. All such adapters remain disabled and explicitly
labelled as requiring external validation.
