# Phase 32 Sync Security Report

Locally verified controls:

- New devices default to pending and require approval before sensitive synchronization.
- Revocation/lost-device response terminates sessions and blocks journal access.
- Device and tenant boundaries fail closed.
- Tokens are encrypted at rest and excluded from API/status/diagnostic responses.
- Secrets, passwords, tokens, API keys, private keys, and restricted configuration are rejected from the journal.
- Payload cache uses Fernet authenticated encryption from the maintained `cryptography` library.
- Remote endpoints must be credential-free HTTPS URLs; HTTP transport uses platform certificate validation.
- Journal checksums, immutable core triggers, authenticated decryption, file SHA-256, bounded extraction/response logic, and support-reference incidents detect tampering.

Encryption claim boundary:

- Transport encrypted: configured HTTPS connections.
- Local encrypted: session tokens and synchronized payload cache.
- End-to-end eligible: opaque payload mode only when approved devices share the account recovery key and the server does not process content.
- Not end-to-end: server-processed institutional records and metadata needed for routing/policy.

No blanket E2EE, cloud certification, penetration-test, or deployed-provider claim is made. Recovery-key handling, endpoint interoperability, certificate operations, and remote infrastructure need external validation.
