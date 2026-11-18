# BioIntel AI Step 193 — Mandatory Module Completion and Installation Repair

## Scope

Step 193 completes last-mile mandatory software controls for all 80 logical major modules and repairs the verified Windows installation flow.

## Module additions

- Intended-use and prohibited-use boundaries
- Input schema, sample identity and cross-module consistency
- Data classification, consent, permission, licence, retention and deletion policies
- Autosave, atomic snapshots, checkpoint resume and stale-state recovery
- Session isolation, concurrency locks and bounded resource budgets
- Dependency, engine and reference health contracts
- Confidence, uncertainty, limitations, abstention and fail-closed release
- Signed exports, SHA-256 integrity and tamper-evident provenance
- Review states, separation of duties and change-control records
- Feature flags, deprecation, schema migration, rollback and disaster recovery
- Accessibility, Unicode path support, security redaction and diagnostics
- SLO monitoring, alert ownership and category-specific mandatory capabilities

## Installation error repaired

The previous installation helper invoked the self-test with `--allow-degraded`, while the self-test command-line parser did not accept that argument. This caused an immediate argument error and could trigger an unnecessary second environment rebuild before installation failed. Step 193 aligns the command contract and adds a regression test for it.

The installer also now discovers a valid Python 3.11 x64 installation across the Python launcher, Windows registry, standard installation folders and PATH. When Python is absent and Winget is available, a per-user Python 3.11 installation is attempted automatically.

## Honest boundary

Internal software and demo-operational completion is 10/10. Authentic wet-lab, clinical, instrument, licensed-data, independent-site and regulatory evidence remains externally required.
