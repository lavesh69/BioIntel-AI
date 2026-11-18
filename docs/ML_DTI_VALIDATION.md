# ML and Drug–Target Validation Policy

BioIntel Step 36 separates **validation implementation readiness** from **scientific evidence quality**.

## Required validation matrix

A model can reach scientific release eligibility only after all of the following pass:

- cold-drug split;
- cold-target split;
- cold-drug-and-target split;
- molecular scaffold split;
- protein sequence-cluster split;
- temporal split;
- independent external validation;
- prospectively frozen predictions evaluated after outcomes are recorded.

Every split must bind to an immutable dataset SHA-256, report overlap counts, include metrics with confidence intervals and satisfy the task-specific thresholds in `config/validation_policy.yaml`. External and prospective evidence requires a reviewer identity and signed evidence manifest.

## Statistical controls

`biointel.validation.rigorous` provides bootstrap confidence intervals, permutation significance tests, classification calibration diagnostics, expected calibration error and subgroup/site robustness. These controls are reusable for internal, external and prospective evaluations.

## Important boundary

The framework is implementation-complete. The bundled models are synthetic demonstrations and do not become scientifically validated merely because the framework exists. Real experimental training data, independent datasets and prospective outcomes must be supplied and pass all gates.
