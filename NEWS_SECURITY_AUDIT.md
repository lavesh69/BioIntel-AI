# BioIntel Science Plus — Security & Protection Audit

## Protections Enforced
- **SSRF & Malicious URLs**: Allowlist of official HTTPS endpoints.
- **XML / JSON Parsing**: Safe defused XML parsing against decompression bombs and XXE.
- **SQL Injection**: 100% parameterized SQLite queries.
- **Secret Redaction**: Zero hardcoded API keys; environment variable resolution only.
