# Phase 31–35 Backup and Restore Guide

## Backup

- Stop the application first.
- Copy `%LOCALAPPDATA%\BioIntelAI\UserData` to a dated, access-controlled backup.
- Retain the installer, production ZIP, SHA-256 file, and package manifest used by that
  deployment.
- Hash the backup and record tenant, operator, time, retention, and encryption details.
- Do not place credentials or decrypted remote-adapter configuration in support bundles.

## Restore

- Verify the backup hash before restoration.
- Install the matching application release to a short path.
- Keep the new empty `UserData` directory as a safety copy.
- Restore the backed-up `UserData` directory while BioIntel AI is stopped.
- Start the app and verify database integrity, migration records, tenant boundaries,
  sync status, representative projects, artifacts, and audit history.

Institutional backups require approved encryption, access control, retention, deletion,
and disaster-recovery procedures. The local qualification is not a substitute for an
externally observed restore drill.
