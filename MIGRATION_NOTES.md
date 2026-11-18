# Migration Notes

## From Step219 to Step220

1. Keep the complete application directory together; do not merge only selected ZIP parts.
2. On first platform use, schema version 220 is created in `UserData/reports/discovery_platform.sqlite3` unless `BIOINTEL_USER_DATA` points elsewhere.
3. The migration is additive and idempotent. Existing legacy SQLite/JSON registries are not deleted or overwritten.
4. Use the platform legacy import operation only after making a backup. Imported records retain their original identifiers in provenance fields where available.
5. Synthetic projects and real projects are separate. A dataset origin must match the project boundary, and synthetic records cannot be promoted to real scientific evidence.
6. The active CLI group is `biointel research-platform`. Existing CLI commands remain available.
7. The Python SDK is `biointel.discovery_platform.BioIntelResearchClient`; it can use an in-process service or the HTTP API.
8. External tools are optional and are discovered through the dependency manager. Missing tools do not silently produce replacement results.

## Backup and rollback

- Back up the complete `UserData` directory before migration.
- The store provides a SQLite online backup plus SHA-256 manifest.
- To roll back the application, restore the prior application directory and its matching `UserData` backup.
- Do not edit `PRAGMA user_version` manually.

## Release packaging

four ZIP parts are a partition of one release tree. Each relative file appears in exactly one part. Extract all five into the same destination before running the application.
