# Phase 23–30 Migration Guide

## Before upgrade

1. Stop Streamlit, API, MCP and Education workers.
2. Run `BACKUP_EDUCATION_PHASE23_TO_30_WINDOWS.bat`.
3. Keep the reported ZIP and its SHA-256 outside the installation directory.
4. Preserve all four previous release ZIPs as an immutable rollback source.

## Upgrade

1. Place all four matching Phase 23–30 ZIPs beside `EXTRACT_INSTALL_RUN_EDUCATION_PHASE23_TO_30_4PART_WINDOWS.bat`.
2. Run the extractor. It validates all four release markers before installation.
3. The installer creates/updates the Python 3.11 environment and runs diagnostics.
4. Open Education Home, confirm the actor/institution and then open the Enterprise workspace.

Migration `education_phase23_to_30_enterprise_platform_v1` is additive and idempotent. It applies the Phase 17–22 predecessor schema first, then creates 57 Phase 23–30 tables and seeds eight agents, 23 lab experiments and 12 skills.

## Post-upgrade checks

- Run `DIAGNOSE_EDUCATION_PHASE23_TO_30_WINDOWS.bat`.
- Confirm `overall: pass`, database integrity, migration ID and catalog counts.
- Run a controlled pilot import dry-run before commit.
- Configure API/MCP/integrations with least privilege; do not copy example secrets into production.

