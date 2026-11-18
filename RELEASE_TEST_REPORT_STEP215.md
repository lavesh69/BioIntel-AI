# BioIntel AI Step215 / Windows V19.6 — Engine Platform Integration Test Report

Generated: 2026-07-18T14:55:09+00:00

## Implemented scope

V19.6 merges the Step 2–12 Engine Platform work into the complete V19.5 release. It includes the Engine Control Center, 76-engine registry, 12 advanced adapters, Windows offline adapter wheelhouse, WSL2 acquisition recipes, integrity-checked engine packs, target-machine qualification evidence and six optional production-service interfaces.

## Automated validation completed before packaging

- Engine audit and platform: **35 passed**.
- Current release and protected contract: **22 passed**.
- BioIntel Live Workspace: **22 passed**.
- Step207/Step208 module regression: **71 passed**.
- Neuro backend: **110 passed**.
- Bioinformatics backend: **70 passed**.
- Discovery and Lab backend: **20 passed**.
- Focused total: **350 passed, 0 failed**.
- Python compile: **1710 checked, 0 errors**.
- Windows CPython 3.11 x64 wheelhouse: **121 wheels, valid**.
- Protected hashes: **17/17 unchanged**.

## Validation boundary

The builder is Linux and did not execute native Windows BAT, WSL2 or GPU workloads. Streamlit AppTest was unavailable in the builder environment. The Windows installer keeps these as target-machine blocking checks where applicable. External engines remain unqualified until exact upstream artifact/licence hashes and target-machine positive/negative smoke evidence pass.
