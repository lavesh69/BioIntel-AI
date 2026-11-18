# Phase 32 Secure Sync Architecture

BioIntel Sync is optional and local-first. Local database and file operations do not depend on a remote provider.

The implementation separates:

- `PlatformStore`: versioned SQLite schema and durable transactions.
- `SyncEngine`: device trust, policy, consent, journal, conflict, files, status, and recovery-key boundaries.
- `SyncAdapter`: provider-neutral `push` and `pull` protocol.
- `HttpSyncAdapter`: HTTPS transport with standard certificate verification, timeouts, no redirects, and bounded JSON responses.
- `MemorySyncAdapter`: deterministic test/reference adapter; it is not a cloud service.
- Streamlit and FastAPI surfaces: thin service consumers.

The append-only journal survives application closure. Mutable delivery state is stored separately. Remote synchronization is disabled until an endpoint and credentials are explicitly configured.

Implemented and locally verified: two/three-device records, approval/revocation, idempotent queueing, retry persistence, conflicts, authenticated payload encryption, file hashes, chunk plans, quotas, tenant checks, API, and UI.

Requires external validation: interoperability with a deployed institution/self-hosted/cloud endpoint, representative large-file transfer, certificate operations, bandwidth controls, and long-duration multi-device use.
