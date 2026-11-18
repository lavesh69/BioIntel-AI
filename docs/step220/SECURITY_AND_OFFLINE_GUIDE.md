# Step220 Security and Offline Guide

## Security controls

- PBKDF2 password hashing, random salts, lockout, revocable sessions, and RBAC.
- Project/dataset permission records and append-only hash-chained audit events.
- Recursive secret redaction for logs and client metadata.
- Resolved-path containment for artifacts, exports, uploads, and Windows paths.
- ZIP member traversal checks, file hashes, duplicate detection, and corruption checks.
- Windows DPAPI/keyring/environment secret-store selection with explicit fallback states.
- Synthetic/real origin isolation at project, dataset, run, evidence, and validation boundaries.

## Offline operation

SQLite persistence, native Python analyses, UI, API, CLI, SDK, synthetic generation, and report exports work locally. The Dependency Manager records missing executables and setup guidance. Network-dependent literature/database refreshes and enterprise identity are disabled or unavailable until configured; no fabricated replacement response is generated.

## Scientific governance

All reports carry review-required status. Synthetic reports carry visible notices and watermarks. Clinical, diagnostic, publication, and regulatory use require independent qualified validation outside this software.
