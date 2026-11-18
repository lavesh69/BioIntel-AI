# Science Pulse Database Schema

Migration: `science_pulse_mega_v1`

Canonical tables:

- `sp_schema_migrations`, `sp_sources`, `sp_sync_runs`, `sp_worker_leases`
- `sp_items`, `sp_item_sources`, `sp_duplicate_clusters`, optional `sp_items_fts`
- `sp_bookmarks`, `sp_user_preferences`, `sp_alert_rules`, `sp_notifications`
- `sp_digests`, `sp_digest_items`, `sp_summaries`, `sp_search_history`
- `sp_integrations`, `sp_trust_events`, `sp_audit_log`

SQLite foreign keys, WAL, busy timeout, indexes, idempotency uniqueness, and tenant-scoped access are enabled. Existing `pulse_articles` rows are migrated without deletion.
