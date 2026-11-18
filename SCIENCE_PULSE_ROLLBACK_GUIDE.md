# Science Pulse Rollback Guide

1. Stop BioIntel and the background worker cleanly.
2. Preserve the current Science Pulse database for audit/export.
3. Restore the timestamped source and database backup.
4. Restore the prior full application package, then run its integrity/startup checks.
5. Do not selectively delete `sp_*` tables from a live database; restore a complete backed-up database instead.
6. Re-enable external sources only after the rolled-back version's compatibility is confirmed.
