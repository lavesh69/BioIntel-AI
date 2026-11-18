# BioIntel AI Step 196 V7 — Historical Module and Function Improvement Audit

> Superseded by the current Step 196 V8 audit. Retained for release provenance only.

This is a factual source audit, not a claim that every module has external scientific validation. The active source contains 262 Streamlit page files, 263 catalogue entries including Home, 80 major contextual research profiles, 55 themes and 11 font options.

## Improvements completed in this release

| Area | What changed | User outcome |
| --- | --- | --- |
| Windows delivery | Four-part packaging, regenerated manifests, installer preflight and exact Python contract | Fewer mixed-part, stale-manifest and wrong-runtime failures |
| Current-release launch | Desktop shortcut refresh, current runtime shims and cross-release process guard | An old shortcut/runtime state cannot silently open another extracted release |
| Navigation | Explicit metadata for every page; history Back/Forward plus category movement | Module/category selection persists instead of falling back to Home or `Unclassified` |
| Global module discovery | Branded vector icons on catalogue and command cards; complete searchable page catalogue | Professional visual identity without hiding modules |
| Local recovery | Guarded stop control and friendly runtime diagnostics | Users can stop the current local UI/API/worker without killing a different release |
| Optional online services | Existing optional-service isolation remains intact; core installation and offline workflows do not wait for Ollama/SearXNG | Missing online service is an unavailable state, not a core-install failure |

## Remaining improvement areas by module family

| Priority | Scope observed in source | Practical next improvement | Scientific/operational boundary |
| --- | --- | --- | --- |
| P0 | 20 expansion workbenches (pages 112–132) | For the 19 non-protected workbenches, replace shared exploratory ranking shortcuts with per-domain native-adapter execution, input schema fixtures and output acceptance tests | Their deterministic demo data are labelled; exploratory scores are not validated clinical, wet-lab or production findings |
| P0 | 78 embedded module-experience canvases | Bind every canvas to real run artifacts and add semantic visual tests for axes, units, empty states and export consistency | A polished canvas alone is not a scientific result |
| P0 | 52 page-level upload controls | Build a per-module upload acceptance matrix: supported formats, malformed-file handling, 100 MB staged path and 1 GB boundary recovery | Large files must be staged; interactive parsing should remain memory-bounded |
| P0 | 126 download/export controls | Define versioned export schemas, provenance fields, checksums and round-trip import tests for every report family | Exported results inherit their input/data-source limitations |
| P1 | 43 next-generation module surfaces | Connect each visual shell to a documented local engine/adapter, expose dependency readiness and provide an explicit no-engine fallback | Never display a simulated specialist result as if an external engine ran |
| P1 | 80 contextual online research profiles / 61 top-website profiles | Move online retrieval to cancellable background jobs with local cache/provenance, request size guards and source availability tests | Public websites, Ollama and SearXNG remain optional; do not submit sensitive data without approved infrastructure |
| P1 | Research planning, workflow builder, evidence and reference lifecycle | Add cross-module project handoff tests: input → job → evidence package → report → restore | Preserve existing planning modules; do not duplicate their workspaces |
| P1 | Charts/tables across enhanced pages | Add screenshot/semantic regression tests for non-empty, empty, failed and large-data conditions | Visual correctness must be checked against the underlying table/run artifact |
| P2 | Themes and typography | Keep all 55 themes and 11 fonts; add representative desktop accessibility snapshots for each experience family | No theme/font removal is needed for this release |
| P2 | Optional production adapters | Add configuration wizards that validate local PostgreSQL/Redis/object-storage endpoints without storing secrets in reports | Docker, cloud accounts and paid APIs must remain optional |

## Platform-wide quality work still needed

1. Windows acceptance testing on a clean Windows 10/11 machine with CPython 3.11.9 x64, Desktop/OneDrive Desktop redirection and extraction paths containing spaces.
2. Full Streamlit AppTest coverage for every changed page and representative screens from each module family.
3. End-to-end tests for 1 GB staged ingestion using disposable test data, without loading large uploads into the Streamlit process.
4. Report/export round-trip tests with checksum and provenance verification.
5. Independent scientific review for any module intended to influence experimental, clinical or regulated decisions.

## Protected modules deliberately excluded from changes

- DTI Predictor
- DTI Validation Evidence Center
- LIMS / ELN / Sample Chain of Custody
- Lab Instrument Import Center
- Instrument Integration Hub

Their source hashes were compared against the uploaded canonical ZIPs during this release audit.
