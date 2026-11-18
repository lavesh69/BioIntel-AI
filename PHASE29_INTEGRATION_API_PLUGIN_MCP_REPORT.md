# Phase 29 — Integrations, Public API, Plugins and MCP

Status: **IMPLEMENTED_AND_VERIFIED locally** for policy enforcement and protocol behavior.

## Delivered

- Integration registry for Moodle, Canvas, Google Classroom, LTI, OneRoster, ORCID, Crossref, PubMed, Europe PMC, SMTP, calendar, S3, OAuth/OIDC and SAML.
- Truthful `configured`, `requires_credentials` and `requires_live_validation` states; no connector is marked live without a successful external test.
- Versioned FastAPI routes, scoped hashed API keys, expiry, local per-minute rate enforcement, usage audit and tenant checks.
- HMAC-SHA256 webhooks, HTTPS requirement except loopback development, timestamp replay window, delivery records and retry schema.
- Constrained plugin manifests with declared permissions and administrator grants; unrestricted filesystem/network/SQL/shell permissions are rejected.
- JSON-RPC stdio MCP server with initialize, tools/list and tools/call; scoped API authentication; policy-filtered tools; read-only default; human approval for writes.
- Durable idempotent background jobs, leases, attempts, retry/dead-letter state and managed object storage.

## Classification

- Local API, webhook verification, plugins and MCP controls: **IMPLEMENTED_AND_VERIFIED**
- Live LMS, SSO, scientific-provider, SMTP, calendar and S3 interoperability: **IMPLEMENTED_REQUIRES_EXTERNAL_VALIDATION**
- Arbitrary third-party plugin execution: **NOT_IMPLEMENTED** for security.

