# Education Migration and Rollback Guide

## Upgrade

Migration ID: `education_phase17_to_22_unified_os_v1`

1. Create and verify a full Education/Connect/Shiro backup.
2. Install all four matching release parts.
3. Start the application or diagnostic tool.
4. The migration creates new tables and indexes with `IF NOT EXISTS`.
5. Verify both `education_os_migrations` and `education_migrations`.
6. Run the diagnostic and target qualification tests.

Normal startup never deletes or recreates the user database.

## Application rollback

The safest rollback is application-level:

1. Stop workers and servers.
2. Retain the upgraded UserData backup.
3. Reactivate the previous managed application release.
4. The previous code ignores the additive Phase 17–22 tables.

## Data rollback

SQLite does not provide a universal automatic down migration for user-generated data.
For a full data rollback, restore the verified pre-upgrade backup. Do not drop Phase
17–22 tables from a live production database; they may contain Connect deliveries,
submission idempotency records and Studio history.

## Failure recovery

If migration or integrity verification fails, keep the original database untouched,
record the diagnostic report and restore the pre-upgrade backup. Never “repair” a user
database by deleting it or reseeding demo data.

