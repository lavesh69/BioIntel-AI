# Changelog — Education Phases 17–22

## Added

- Unified Education OS resource registry and scoped canonical RBAC.
- Durable cross-module workflow, outbox and idempotency services.
- Course/classroom Shiro scopes, ACLs, approved documents and reviewed artifacts.
- Education-to-Connect identity bridge and persisted notification delivery.
- Explainable rule-based interventions with minimum-data and mandatory human review.
- Persistent BioIntel Studio versions, assets, citations, review, publication and structured export.
- Science Pulse DOI/PMID/title canonicalization.
- bioRxiv and medRxiv Science Pulse adapters.
- Feature flags, component health and release qualification evidence.
- Seventeen `/api/v1/education/os` routes.
- Windows worker, diagnostics, installer wrapper and four-part extractor.
- Pinned bundled Windows FFmpeg wheel and local resolver.
- Phase 17–22 migration/integration/security/Windows tests and documentation.

## Changed

- Legacy Connect/Education routes delegate to canonical persistent UIs.
- Education Studio page exposes the persistent Studio workspace.
- Streamlit target modules use the current width API.
- Unknown compatibility identities are guests instead of implicit students.
- Windows llama.cpp verification supports `.cmd`/`.bat` executables and paths with spaces.
- Windows installer recognizes the Phase 17–22 four-part release name.
- Environment example documents local storage, FFmpeg and optional TURN configuration.

## Preserved

- Existing scientific modules, datasets, reports, templates and compatibility layers.
- Existing Phase 2–16 Education migrations and services.
- Existing Connect messaging/media/WebRTC state implementation.
- Existing Shiro local-first provider and optional Ollama abstraction.
- SQLite zero-configuration default and optional deployment adapter boundaries.

## Qualification boundary

Public TURN, live external provider availability, external AI credentials, formal
security/accessibility review and Studio rendered formats require external qualification.

