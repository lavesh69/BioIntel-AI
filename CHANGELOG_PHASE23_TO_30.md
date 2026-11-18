# Changelog — Education Phases 23–30

## 15.6.0 Education Phase 23–30 Enterprise R1

### Added

- Institution pilots, onboarding, governed CSV/XLSX imports, health and support.
- Eight-agent Shiro ecosystem with approval-controlled tools.
- 23-experiment Virtual Science Laboratory.
- Transparent mastery, recommendations and spaced repetition.
- Research-to-education provenance/review pipeline.
- Portfolios, skills, signed credentials, verification, revocation and career plans.
- Public FastAPI surface, API keys, webhooks, integration registry, plugins and MCP server.
- Durable jobs, managed object storage, deployment/recovery profiles and audit chain.
- Enterprise and Virtual Lab Streamlit pages.
- Windows worker, MCP, diagnostics, load, backup, restore and four-part installer entry points.
- Phase 23–30 tests, reports, handbooks and package verification.

### Changed

- Education and main FastAPI routers now include Phase 23–30 routes.
- Education Home links to the new workspaces.
- Environment example and Step 220 release metadata include safe enterprise defaults.
- Installation recognizes the Phase 23–30 release prefix.

### Compatibility

The migration and routers are additive. Phase 17–22 durable outbox schema is applied idempotently before the Phase 23–30 schema.

### Honest limitations

See `PHASE23_TO_30_KNOWN_LIMITATIONS.md`. No live LMS/SSO/cloud, production capacity, accreditation, formal penetration-test or WCAG certification is claimed.

