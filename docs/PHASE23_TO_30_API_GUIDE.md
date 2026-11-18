# Phase 23–30 API Guide

Create a tenant-scoped API key from the administrator workspace or internal API. Save the returned raw `bia_...` value immediately; only its hash is retained.

Send `Authorization: Bearer <key>`. Use the smallest scope, set expiry, paginate list calls and retain request IDs. A valid key cannot cross its institution boundary.

The public endpoints are documented in `PHASE23_TO_30_API_SPEC.md`. OpenAPI remains the machine-readable source for request/response models. HTTP 401/403 responses must not be retried with broader credentials automatically; 429 should use bounded backoff.

Webhook consumers must validate the HMAC signature, timestamp and nonce before parsing business data. Production targets require HTTPS.

