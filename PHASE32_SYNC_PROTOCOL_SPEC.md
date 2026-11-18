# Phase 32 Sync Protocol Specification

Each change carries `change_id`, `idempotency_key`, tenant, entity type and ID, operation, monotonic entity version, device, actor, UTC timestamp, SHA-256, tombstone, authenticated ciphertext, and key version.

Supported operations are `CREATE`, `UPDATE`, `DELETE`, `RESTORE`, `ARCHIVE`, `ATTACH_FILE`, and `REMOVE_FILE`.

Adapter contract:

1. `push(tenant_id, changes)` returns acknowledged change IDs.
2. `pull(tenant_id, cursor, limit)` returns changes and a resumable cursor.
3. Duplicate change IDs and idempotency keys produce no duplicate entity operation.
4. Tenant mismatch, untrusted/revoked device, missing fields, decryption failure, or checksum mismatch fails closed.
5. Network failure leaves the durable journal queued, increments retry evidence, records a safe support reference, and schedules backoff.

HTTP routes expected from a compatible endpoint are `/v1/sync/push` and `/v1/sync/pull`. Transport requires HTTPS with normal platform certificate validation. Provider-specific APIs must be implemented through adapters.

Files are identified by tenant, entity identity, SHA-256, and version—not filename. Local staging is atomic and verified. Chunk state supports resumable transfer; the current HTTP reference adapter does not yet transmit file chunks.
