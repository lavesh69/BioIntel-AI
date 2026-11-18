# Architecture Decision Records

## ADR-001 — Dual-score quality model

Implementation readiness and real-world evidence are scored separately. Code cannot convert synthetic data into scientific validation or regulatory certification.

## ADR-002 — Tenant context is mandatory for tenant-created resources

Request context, membership enforcement, resource keys and storage paths include tenant identity. Public reference catalogs remain shared by design.

## ADR-003 — Controlled records are versioned and audit-chained

Regulated records use immutable content hashes, explicit versions, audit events and bound electronic signatures.

## ADR-004 — FAIR and reproducibility are release artifacts

Scientific releases produce machine-actionable FAIR metadata and a checksum-verified reproducibility bundle.

## ADR-005 — Production deployments use declarative infrastructure

Docker Compose supports single-environment deployment. Helm provides Kubernetes security contexts, probes, autoscaling, disruption budgets, network policies, migration hooks and monitoring integration.
