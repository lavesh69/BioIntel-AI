# Phase 34 Reproducibility Report

## Captured for each run

- workflow ID/version and canonical specification SHA-256;
- approved tool IDs, versions, and deterministic definition checksums;
- parameters, seed, user, tenant, institution, priority, and retry policy;
- input manifest SHA-256 and output artifact SHA-256 values;
- operating system, Python version/implementation, local execution mode, and
  configured resource envelope;
- start/end timestamps, step state, checkpoints, logs, warnings, and support
  reference;
- dataset → workflow → run → artifact provenance graph.

## Verified behavior

The Phase 34 focused suite verified deterministic fixture execution, idempotent
submission, duplicate-execution prevention, checkpoint retention, retry after an
integrity failure, cancellation, output hashing, run comparison, export, safe
inspection, and reference-only import. The run-bundle importer never executes
imported content.

Test result: **10 passed in 7.90 seconds**.

## Limitations

The environment lock is a captured runtime/tool identity record, not a bundled
third-party container. Reproduction still depends on compatible BioIntel code and
Python dependencies. Scientific equivalence, real-world dataset reproducibility,
external compute reproducibility, and production-scale performance were not
validated.
