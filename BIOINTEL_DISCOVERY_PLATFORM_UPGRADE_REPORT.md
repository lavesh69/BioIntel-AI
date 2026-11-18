# BioIntel Discovery Platform Upgrade Report

Release: `15.6.0-Step220.0-WINDOWS-V20.3`
Status: research platform upgrade implemented and locally verified.

## Delivered

- Unified SQLite schema version 220 covering projects, 19 lifecycle stages and gates, datasets, files, samples, workflows, immutable workflow versions, runs, artifacts, candidates, evidence, hypotheses, recommendations, experiments, validations, graphs, models, explanations, notebooks, reports, review, permissions, jobs, instruments, audit events, retention controls, and synthetic manifests.
- Streaming scientific ingestion with format detection, integrity checks, schema checks, duplicate detection, safe archive handling, resumable progress hooks, and optional deep validators.
- Versioned DAG orchestration with cycle detection, topological ordering, templates, run cloning/freezing, dependency health, provenance, and reproducibility manifests.
- Eighteen production scientific analysis engines and canonical Step220 synthetic adapters for all eighteen generator modules.
- Candidate ranking/dossiers, evidence management and contradiction detection, knowledge graphs, hypotheses, experiment planning, validation feedback, recommendations, model registry, notebooks, collaboration, and audit history.
- Report generation in PDF, DOCX, HTML, XLSX, CSV, JSON, and reproducibility ZIP.
- FastAPI platform router with 59 dedicated routes under `/v1/research-platform`, a local/HTTP Python SDK, and `biointel research-platform` CLI commands.
- Streamlit Discovery Lab Platform page with portfolio, data, analysis, discovery, evidence/validation, reports, and operations views.
- Local authentication with PBKDF2-HMAC-SHA256 (600,000 iterations), session lockout/revocation, RBAC, secret redaction, Windows secret storage fallbacks, path traversal guards, and hash-chained audits.
- Deterministic synthetic generation, manifests, origin boundaries, production-engine execution, expected failure capture, watermarks, contamination checks, and reset controls.

## Compatibility and preservation

No legacy feature source was intentionally removed. Step220 is additive except for active release metadata and the root CLI delegation needed to expose the new command group. Historical Step219 documents remain intact. Packaging excludes only transient runtime content such as `__pycache__`, `.pyc`, caches, logs, local databases, temporary verification folders, and virtual environments.

## Scientific status

All outputs remain research decision support and require qualified review. No result is represented as clinical, diagnostic, regulatory, or publication-ready by default. External databases and command-line tools are detected and reported; unavailable dependencies produce actionable partial/dependency states instead of fabricated results.
