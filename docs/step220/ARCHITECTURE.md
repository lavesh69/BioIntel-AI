# Step220 Architecture

The Discovery Platform is an additive local-first layer inside BioIntel AI.

## Layers

1. Streamlit page `270_Discovery_Lab_Platform.py` provides operational views.
2. FastAPI routers expose `/v1/research-platform` contracts.
3. `DiscoveryPlatformService` composes lifecycle, research, workspace, analysis, operations, security, reporting, ingestion, workflow, provenance, and synthetic services.
4. `DiscoveryPlatformStore` owns schema version 220, transactions, JSON encoding, migrations, integrity, backup, and hash-chained audits.
5. Artifacts live under the configured `UserData/discovery_platform_artifacts` root with resolved-path guards and SHA-256 provenance.

## Core invariants

- Every dataset belongs to one project and matches its real/synthetic origin boundary.
- Workflow definitions are immutable versions; runs reference exact versions and inputs.
- Scientific outputs carry origin, parameters, hashes, software/environment metadata, warnings, and limitations.
- Candidates, evidence, hypotheses, recommendations, experiments, and validations remain traceable to projects and source runs.
- Synthetic generation is deterministic by seed and passes through canonical adapters into the same production analysis registry.
- External tools are optional dependencies with recorded versions and health states.

## Data flow

Project -> Dataset/Samples/Files -> Workflow/Run -> Artifacts -> Candidates/Evidence -> Hypotheses/Recommendations -> Experiments/Validation -> Reports/Reproducibility Archive.
