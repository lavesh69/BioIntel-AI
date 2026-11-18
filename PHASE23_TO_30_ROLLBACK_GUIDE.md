# Phase 23–30 Rollback Guide

Rollback is a database-and-installation recovery operation, not a down-migration that deletes new tables.

1. Stop all BioIntel processes.
2. Preserve a copy of the current user-data directory for investigation.
3. Inspect the pre-upgrade backup:

   `python scripts\phase23_30_backup_restore.py inspect <backup.zip>`

4. Run restore once without confirmation to obtain the required `RESTORE-xxxxxxxx` token.
5. Repeat with that exact token. The restore tool creates a pre-restore backup and rejects unsafe ZIP paths or hash mismatches.
6. Reinstall/extract the previous four-part release into a separate clean application directory.
7. Run the previous release diagnostics and verify representative institution records.

Do not manually delete `education_p30_*` tables. External systems may have received webhook/outbox events; reconcile those systems separately after rollback.

