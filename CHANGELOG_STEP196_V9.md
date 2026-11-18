# BioIntel AI Step 196 V9 — Changelog

Version 15.3.0 · Windows-first local release · four ZIP parts.

## Integrated scientific runtime preparation

- `INSTALL_WINDOWS.bat` still performs verified offline core installation first, then starts the scientific-runtime worker in the background. The user-facing workflow remains exactly `INSTALL_WINDOWS.bat` → `RUN_BOTH_WINDOWS.bat`.
- The worker reads the actual Step 173 ratings and targets the 25 modules at or below 5.32/10 practical readiness: 34 public automatic engines, 5 provider/manual engines, 7 small public reference releases (about 1.8 GB), and the remaining larger/authorised references.
- On a suitable Windows system it uses the existing grouped, resumable WSL2/micromamba workflow for all 48 public automatic specialist engines. A 250 GB free-space gate prevents an unsafe full engine attempt on an undersized drive.
- If WSL2/Ubuntu is absent, the worker requests the normal Windows WSL setup and records a restart/approval-required state rather than failing the core app or showing a traceback.

## Honest installed and qualified states

- The specialist runtime registry now separates **installed** engines and **downloaded** references from scientifically **qualified** assets.
- Small public reference acquisition is resumable, recognises an existing completed download, records an unqualified local registration, and reports remote/provider failures as a calm optional-service-unavailable state.
- The Specialist Runtime & Reference Qualification page now shows the installer state, installed/downloaded counts and a workflow canvas instead of directing users to extra batch files.

## Scientific boundary

- V9 does not invent the five provider/manual engines, 2.8+ TB of target references, model/cohort qualification, wet-lab evidence, independent confirmation, expert sign-off or controlled-release approval.
- The 25 modules remain internally 10/10 in the existing software/qualification framework. Their practical ratings are recalculated only from real installed-and-qualified assets and authentic external evidence.

## Protected modules

These pages remain untouched:

- DTI Predictor
- DTI Validation Evidence Center
- LIMS / ELN / Sample Chain of Custody
- Lab Instrument Import Center
- Instrument Integration Hub
