# Step 21 Professional Database Guide

## Database files

```text
reports/datasets.sqlite3
reports/experiments.sqlite3
reports/projects.sqlite3
reports/knowledge.sqlite3
reports/analytics.sqlite3
reports/assets.sqlite3
```

## Recommended entry point

Open **Data Intelligence Hub** from the Home screen or sidebar.

## Search workflow

1. Enter a term such as `extra trees`, `dataset`, `sequence` or `governance`.
2. Review Knowledge, Assets and Analytics result tabs.
3. Open a specialist warehouse for deeper filters and details.

## Knowledge Warehouse

Use entity type and status filters to search compounds, targets, interactions,
models, datasets, projects, modules and external identifiers. Relationship
Explorer shows incoming and outgoing graph links. Protocol Library provides
controlled workflow templates.

## Analytics & Observability

Use the executive trend view for 14–180 day histories. Module Performance
shows run counts, success, latency, processed rows and memory. Quality,
System and Alert tabs provide additional operational evidence.

## Research Assets

Filter assets by type, collection and favourite state. Select an asset to
inspect tags, collections, metadata and notes. Files up to 25 MB can be
downloaded directly; large files remain lazy to protect UI memory.

## Maintenance

Run:

```text
SEED_PROFESSIONAL_DATABASES_WINDOWS.bat
```

or:

```powershell
python -m biointel database-optimize
python -m biointel database-status
```

Use VACUUM only when compaction is needed:

```powershell
python -m biointel database-optimize --vacuum
```

## Backups and exports

The Data Intelligence Hub creates safe SQLite backups and portable JSON
exports under `reports/database_backups` and `reports/database_exports`.

## Privacy

All databases are local. No login, cloud profile, external telemetry or
advertiser access is used.
