# Step220 API, CLI, and SDK Guide

## API

Base prefix: `/v1/research-platform`

Key groups: projects/stage gates, datasets/samples, workflows/runs, candidates/evidence/hypotheses/recommendations, experiments/validations, reports, models, graphs/activity, synthetic generation, analytics, system health, dependencies, jobs, and instruments.

Errors use a structured payload with code, message, affected operation, partial-result state, remediation, and retryability. OpenAPI request models reject unknown fields.

## CLI

```powershell
biointel research-platform --help
biointel research-platform project-create --title "Study" --question "Question" --objective "Objective"
biointel research-platform project-list
biointel research-platform catalog
biointel research-platform synthetic-generate --module sequencing_quality --scenario high_quality_reads --size small --seed 42
```

Use `--database` and `--artifacts` when a non-default local store is required.

## Python SDK

```python
from biointel.discovery_platform import BioIntelResearchClient

client = BioIntelResearchClient.local(database_path="platform.sqlite3", artifact_root="artifacts")
project = client.create_project(
    title="Study",
    research_question="Question",
    scientific_objective="Objective",
)
projects = client.list_projects()
```

For HTTP mode, initialize with the API base URL and configured authentication headers. Local mode calls the same service layer without network access.
