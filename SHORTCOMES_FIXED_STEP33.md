# Shortcomings Fixed in Step 33

- Added persistent role-aware API clients, hashed keys, request audit, security events, rate windows and idempotency storage.
- Enforced request size on both Content-Length and streamed request bodies.
- Added JSON structured logging with request IDs.
- Added staged jobs, dependencies, events, artifacts, worker heartbeat, cancellation and retry history.
- Added native parent-integrity triggers to legacy dataset, experiment, evidence, project and document tables.
- Added optional PostgreSQL, Redis, MinIO, Celery and telemetry production topology.
- Added official bounded ChEMBL and UniProt synchronization with checksums and scientific-scope labels.
- Added FASTQ.gz, paired-end synchronization and synchronized trimming.
- Added VCF.gz, parsed INFO fields, sample call rates and genotype matrices.
- Unified all 71 pages on premium headers and removed raw JSON result rendering.
- Added profile-scoped UI preferences and improved high-use table/workflow presentation.
