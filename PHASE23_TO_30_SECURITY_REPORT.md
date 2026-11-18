# Phase 23–30 Security Report

## Implemented controls

- Institution membership and role checks on tenant-owned services.
- Object lookup that verifies `institution_id`, limiting insecure direct object reference exposure.
- Parameterized SQLite statements; injection-shaped identifiers are treated as values.
- Managed storage paths resolved beneath the Phase 23–30 tenant root; traversal fragments are normalized.
- File-size and suffix allowlists; executable/script uploads rejected.
- API keys hashed at rest, scoped, expirable and locally rate-limited.
- Integration and webhook secrets encrypted at rest.
- HMAC webhook signatures, HTTPS enforcement outside loopback and replay-window validation.
- Plugin permission allowlist; unrestricted filesystem, network, SQL and shell capabilities rejected.
- MCP policy filter, read-only default and human approval for writes.
- Agent tool allowlists, depth cap, protected decisions and independent approval records.
- Hash-linked audit chain and privacy-minimized diagnostics.
- Backup manifest, per-file SHA-256, safe ZIP member inspection and explicit restore confirmation.

## Automated evidence

Tests exercise tenant isolation/IDOR, SQL-injection-shaped input, path traversal, blocked executable upload, API scope and rate limit, webhook signature/replay/HTTPS, plugin permissions, MCP approval, agent safety, import rollback, credential revocation and backup inspection.

## Not certified

This work is **not** an authorized professional penetration test, red-team assessment, privacy-law opinion, WCAG certification or institutional security acceptance. Live reverse proxies, SSO providers, key-management systems, object storage and network controls require deployment-specific review.

