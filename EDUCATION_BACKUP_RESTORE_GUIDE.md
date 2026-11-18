# Education Backup and Restore Guide

## Back up

Use the existing Phase 11 Education backup service or its UI while logged in as an
institution administrator.

Before a manual filesystem backup:

1. Stop the Education worker and application.
2. Confirm no `education.sqlite3-wal` write activity remains.
3. Copy the complete `%LOCALAPPDATA%\BioIntelAI\UserData\education` directory.
4. Copy Connect and Shiro data if cross-module messages and knowledge indexes are required.
5. Store the SHA-256 and timestamp with the backup.

Never copy only the SQLite main file while a writer is active.

## Restore

1. Stop all BioIntel processes.
2. Preserve the current UserData directory as a rollback copy.
3. Restore to a staging directory first.
4. Run SQLite `PRAGMA integrity_check` and verify the backup manifest.
5. Replace only the intended application data directory.
6. Start BioIntel; migrations run additively.
7. Run `DIAGNOSE_EDUCATION_PHASE17_TO_22_WINDOWS.bat`.
8. Verify an Education Home snapshot, one Shiro citation and one Connect notification.

## Scope

Database backups do not automatically contain external TURN, SMTP, Ollama or provider
configuration. Restore those through the deployment secret/configuration system, never by
placing secrets in the source package.

