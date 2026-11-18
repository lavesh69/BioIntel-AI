# BioIntel Discovery Platform Pre-Upgrade Audit

Audit date: 2026-07-23
Baseline active release: `15.6.0-Step219.0-WINDOWS-V20.2`
Authoritative inputs: all five user-supplied archive parts, merged into one working source tree before Step220 changes.

## Baseline inventory

- Release tree: 12,000+ distributable files before final exclusions, 1,700+ Python files, 270 existing Streamlit pages, and 250+ test modules.
- Existing foundations: Streamlit desktop UI, FastAPI service, CLI, recommendation modules, offline Windows runtime, and Step219 synthetic generators.
- Existing persistence was spread across feature-specific SQLite and JSON registries. There was no single connected schema for the full research lifecycle.
- The Step219 synthetic generators produced useful fixtures, but most generated table shapes did not directly match the new production scientific engine inputs.

## Critical gaps found

1. No unified 19-stage research lifecycle with persisted stage gates.
2. No connected dataset/sample/file registry spanning lifecycle, runs, candidates, evidence, models, notebooks, reports, review, and operations.
3. No single workflow DAG registry with immutable versions and execution provenance.
4. No connected candidate dossier, evidence contradiction, hypothesis, experiment, validation, and recommendation state model.
5. No model governance registry with artifact hashing, comparison, state, and explanation history.
6. No consolidated API, CLI, or SDK surface for the complete platform.
7. Synthetic fixtures were isolated and watermarked, but needed canonical adapters to run through the production scientific analysis framework.
8. No dedicated Step220 operational UI combining portfolio, data, analysis, discovery, validation, reporting, and system health.

## Risks recorded before upgrade

- The historical project is large and contains many legacy release files; unrelated legacy behavior must be preserved.
- External bioinformatics executables and databases are not bundled in every offline installation.
- Deep format validation depends on optional packages such as `pysam`, `h5py`, `nibabel`, and `pydicom`.
- Scientific output must remain research-only and review-required; synthetic output must never contaminate real evidence.
- Windows paths with spaces, Unicode names, long trees, and local offline operation require explicit verification.

## Upgrade boundary

Step220 adds a connected platform layer without deleting legacy pages, modules, tests, installers, data registries, or historical documentation. Runtime caches, generated databases, bytecode, logs, and temporary verification data are release exclusions, not source removals.
