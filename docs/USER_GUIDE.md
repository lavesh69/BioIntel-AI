# BioIntel AI 15.6.0 Step206 User Guide

BioIntel AI is a Windows-first, local-first research platform. The primary workflow is intentionally short:

1. Extract all five matching release ZIPs into the same new empty folder.
2. Run `INSTALL_WINDOWS.bat` and wait for every blocking gate to pass.
3. Run `RUN_BOTH_WINDOWS.bat` or the installed BioIntel AI shortcut.
4. Use `STOP_BIOINTEL_WINDOWS.bat` or `RESTART_BIOINTEL_WINDOWS.bat` for managed lifecycle control.

## Find and open work

Use global search, category filters, favourites, pinned modules and recent history to move between the 269 registered application and scientific pages. Back, forward, Home and breadcrumbs preserve navigation context. Quick Start provides guided entry points; expert controls remain inside each applicable module.

## Start a scientific workflow

1. Create or select a project when the module supports project persistence.
2. Read the module's objective, accepted inputs, dependency status and limitations.
3. Download its input template or labelled sample data when available.
4. Select real upload or demonstration data explicitly; BioIntel never silently substitutes a demo.
5. Resolve input validation and QC findings before analysis.
6. Use background execution for long or engine-backed work.
7. Review uncertainty, applicability, engine/model/reference versions and research-use warnings.
8. Export results together with provenance, parameters, citations and limitations.

## Data and dependency status

The Universal Scientific File Inspector provides bounded previews, format/signature checks, streamed SHA-256 and safe archive handling. Engine Control Center, Model Registry and Reference Database Lifecycle Manager keep software availability separate from qualification. An interface or registry entry does not mean an external executable, model weight, licensed reference or API credential is bundled.

## Reports and reproducibility

The Unified Scientific Report Builder combines selected module outputs into versioned HTML, DOCX and PDF-ready packages. Generated narrative is a draft requiring human scientific review. Provenance records preserve available input/output hashes, parameters, software/module versions and dependency identities.

## Recovery

- Run `DIAGNOSE_WINDOWS.bat /deep` for a sanitized diagnostic report and support bundle.
- Run `SAFE_MODE_WINDOWS.bat` to disable LAN hosting, internet/DNS and optional external engines while applying lower limits.
- Run `REPAIR_WINDOWS.bat` to verify and repair the managed Step206 release without deleting UserData.
- Run `UNINSTALL_BIOINTEL_WINDOWS.bat` only when removal is intended; projects, reports, exports, settings and databases under UserData are preserved.
- Run `RUN_ULTIMATE_ACCEPTANCE_WINDOWS.bat` after installation for target-machine release evidence.

## Scientific boundary

BioIntel AI is research software. Demonstration outputs are labelled. Predictions, rankings, pathways, variants, structures, images and clinical-research summaries require task-specific domain review and, where applicable, qualified engines/databases/models, representative external datasets, orthogonal assays and independent validation. They are not autonomous clinical decisions or regulatory approvals.
