# Step 31 Scientific Data and UI Guide

## Scientific Data Readiness

Open **Scientific Data Readiness** from the sidebar or Quick Actions. The screen provides:

- dataset files, samples, QC, column dictionaries, provenance, lineage, aliases and issues;
- experiment artifacts, direct/alias dataset bindings and validation requirements;
- provider profile status and explicit local-record counts;
- project-to-dataset/model/document/evidence links;
- feature-cache schemas and document registry verification;
- an idempotent local repair action.

A readiness score measures registry completeness. It does not override the scientific release gate. Reference and synthetic records remain non-release eligible.

## Navigation

The built-in 71-page list is hidden. Use the shared sidebar to:

1. Search by tool title, description or keyword.
2. Filter by workspace category.
3. Open featured tools when no filter is active.
4. Reopen favourites and recent work.
5. Use Quick Actions for Home, Command Center, Scientific Data Readiness, Diagnostics and Appearance.

Every page shows a breadcrumb, description and position in the catalogue.

## Repair and verification

Run:

```text
REPAIR_STEP31_DATA_UI_WINDOWS.bat
```

to rebuild manifests, dictionaries, QC, provenance, aliases, model-artifact records, source profiles, project links and indexes from local files.

Run:

```text
VERIFY_STEP31_WINDOWS.bat
```

to validate registries, models, databases, APIs and Step 31 tests.

Neither operation downloads remote scientific records or converts demonstration data into real evidence.
