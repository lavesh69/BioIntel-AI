# Phase 23–30 Backup and Restore Guide

## Backup

`BACKUP_EDUCATION_PHASE23_TO_30_WINDOWS.bat`

The helper uses SQLite online backup, runs `quick_check`, archives the database and managed Phase 23–30 media, and writes a manifest with file sizes and SHA-256 values.

## Inspect

`python scripts\phase23_30_backup_restore.py inspect <backup.zip>`

Inspection verifies ZIP CRC, safe member paths, manifest coverage and hashes without restoring.

## Restore

`RESTORE_EDUCATION_PHASE23_TO_30_WINDOWS.bat <backup.zip>`

Restore requires the explicit `RESTORE-<first-eight-backup-sha256>` token. It creates a pre-restore safety backup, stages and verifies files, replaces only resolved Education database/media targets, and runs database `quick_check`.

## Operational policy

- Keep encrypted/offline copies according to institution retention policy.
- Test restore on a non-production machine.
- Record operator, backup hash, recovery point and verification outcome.
- SQLite desktop backup is locally verified. PostgreSQL, S3 and HA recovery procedures require deployment-specific external qualification.

