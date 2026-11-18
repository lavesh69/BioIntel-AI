# Security Audit Summary

## Controls included

- Localhost-only default runtime; LAN hosting is explicit and account-gated.
- Safe Mode disables outbound internet/DNS, LAN hosting and optional external engines.
- Public URL policy requires HTTPS and blocks unsafe/private destinations.
- Archive/path safety, bounded uploads, argument-array subprocess execution and verified owned-process shutdown controls.
- Environment/configuration-based credentials and sanitized diagnostic redaction.
- Dependency locks, offline wheelhouse verification, `pip check` and release integrity gates.
- User data separated from replaceable application code; backups precede database migration.

## Automated evidence

- Offline static security pattern scan: passed across 1,287 Python files with no findings.
- Desktop production dependency audit: zero reported vulnerabilities.
- Mobile production dependency audit: zero reported vulnerabilities.
- Windows dependency lock: SHA-256 matched and all 32 package rows were valid.
- Offline wheelhouse: 121 wheels present, hash-matched and structurally valid; no unexpected or missing wheel.
- Release gate validates source hashes and critical launch/control files.
- four-part packager rejects unsafe paths, duplicate members, missing source members, CRC failures and checksum mismatches.

## Audit boundary

This summary describes implemented controls and automated software checks. The static scan is an offline pattern scan, not a CVE scan. The result is not an independent penetration test, malware certification, code-signing audit or regulated cybersecurity validation. Physical Windows security-product compatibility and deployment-specific secrets/IAM/network controls require separate assessment.
