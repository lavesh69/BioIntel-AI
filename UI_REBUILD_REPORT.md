# BioIntel AI UI Rebuild Report

## What was rebuilt

- Added a new clean command-home page: `pages/70_BioIntel_Studio.py`.
- Added `BioIntel Studio` into the navigation catalogue as a featured primary workspace.
- Reorganized navigation categories into clean software-style groups:
  - Start
  - Data
  - AI Lab
  - Bioinformatics
  - Discovery
  - Lab Analytics
  - Documents/Governance/Intelligence/Operations/Settings where applicable
- Added a persistent Workflow Dock in the sidebar so users see the most important actions before the full 72-screen list.
- Kept all legacy/advanced tools available through Advanced Search so no functionality is lost.
- Updated Home hero chips to avoid overstating synthetic demo assets as production science.
- Added Studio launch buttons to Home.
- Added consistent `bio-card-kicker` styling for professional step cards.
- Improved sidebar status wording and structure.

## Scientific honesty improvements

- Studio clearly separates software readiness from scientific release readiness.
- Demo/reference assets are labelled in the primary workflow.
- Priority fix board explains real evidence, validation and navigation status.
- Home no longer advertises the DTI pack as if it were real scientific coverage.

## Production improvements also added

- `docker-compose.production.yml` now includes a dedicated `worker` service for queued/background jobs.
- Production API client config is now required through `BIOINTEL_API_CLIENTS_JSON` instead of silently defaulting to empty.
- MinIO image tag is pinned instead of using `latest`.

## Verification completed

- `python -m compileall -q app.py pages src/biointel/ui` passed.
- Navigation import verified.
- `BioIntel Studio` path verified.
- Workflow dock groups verified with no missing page keys.

## Remaining real scientific work

- Import real ChEMBL/BindingDB/UniProt evidence.
- Train validated non-synthetic models.
- Add true external/scaffold/temporal validation.
- Connect application repositories fully to Postgres/Redis/MinIO if full distributed production mode is required.
