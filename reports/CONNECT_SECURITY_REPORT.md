# BioIntel Connect Security Report

Implemented: authenticated signaling and API routes, project membership checks for planning, server-managed Argon2id password hashes with legacy PBKDF2 verification, server-side HMAC ELN signatures, encrypted webhook secrets, HMAC webhook delivery, and DNS/IP SSRF blocking.

Qualification boundary: no independent penetration test; SSO/OIDC/SAML provider validation and tenant isolation across every legacy service remain unqualified. Secrets and `.env` are excluded from release archives.
