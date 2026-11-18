# Step 24 Scientific Performance Guide

## Curate a real activity export

```powershell
python scripts/curate_real_dataset.py input.csv reports/generated/curated_activity.csv --source-database bindingdb
```

Review the generated error rows, duplicate conflicts, activity relations and assay-quality scores before training.

## Run performance qualification

```powershell
python scripts/performance_qualification.py
```

Or run `PERFORMANCE_QUALIFICATION_WINDOWS.bat`.

## Enable optional API-key mode

Set `BIOINTEL_API_KEY` in `.env`, then send it through the `X-API-Key` header. Leaving the value empty preserves localhost-first no-login mode.

## Enable model preload

Set:

```text
BIOINTEL_PRELOAD_MODELS=1
BIOINTEL_PRELOAD_MODEL_LIMIT=6
```

## Install optional features

```powershell
pip install -r requirements-advanced.txt
```

Deep-learning support uses a separate profile because PyTorch must match the machine's CPU/GPU environment:

```powershell
pip install -r requirements-deep-learning.txt
```

## Scientific release rule

A model marked `synthetic_demo=True` is suitable for software validation and demonstrations, not for experimental or clinical claims. Import real evidence, retrain, perform leakage-safe external validation and pass the Scientific Release Gate before presenting a model as scientifically validated.
