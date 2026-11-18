# Step220 Administrator Guide

## Storage

Set `BIOINTEL_USER_DATA` to place local databases and artifacts outside the application directory. Default platform files are under `UserData/reports` and `UserData/discovery_platform_artifacts`.

## Accounts and roles

Local accounts use PBKDF2-HMAC-SHA256 with 600,000 iterations, random salts, lockout, revocable sessions, and sliding expiry. Assign the least-privileged role needed. Project and dataset grants are audited.

## Health and dependencies

Use Operations -> System health or the API dependency endpoint. Missing external tools include setup instructions and compatible modules. Never mark an unavailable dependency as installed without a successful executable/version check.

## Backup

Use the store backup operation for an online SQLite backup and SHA-256 manifest. Also back up the complete `UserData` directory. Verify `quick_check`, foreign keys, schema version, and audit chain before and after maintenance.

## Retention and cleanup

Configure retention policies before deleting artifacts. Cleanup functions target registered cache/log/temporary roots. Project deletion cascades relational records and is audited; export required evidence first.

## Synthetic reset

Only synthetic projects can be reset, and the exact project identifier is required as confirmation. Real project data is not eligible for the synthetic reset path.
