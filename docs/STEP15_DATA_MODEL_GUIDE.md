# Step 15 Data & Model Guide

## Which pack to use

### Quick demo

Use for:

- Fast UI checks
- Learning the workflow
- Low-resource machines

### Foundation pack

Use for:

- Faster local training
- Batch and quality testing
- Model parameter experiments

### Extended pack

Use for:

- Main software benchmark
- Classification training
- Larger feature/cache testing
- Model comparison

## Pack columns

```text
drug_id
canonical_smiles
target_id
protein_sequence
target_family
activity_type
p_activity
label
classification_threshold_p_activity
source
data_pack_version
```

## Pretrained model interpretation

Classification RF and Logistic Regression perform strongly on the bundled
synthetic generator. Regression models are intentionally reported honestly and
show more modest performance.

Do not interpret these metrics as real biological generalisation.

## Rebuilding

Run:

```text
BUILD_DATA_AND_MODELS_WINDOWS.bat
```

The process is deterministic and resume-aware. Existing valid pack-v2 artifacts
are reused rather than trained again.

## Real-data progression

1. Open ChEMBL Dataset Builder.
2. Choose a starter target.
3. Fetch live official records.
4. Review assays, units, relations and target components.
5. Register the cleaned dataset.
6. Train using group/scaffold splits.
7. Perform external validation.
8. Compare against the synthetic software benchmark only as a pipeline check.
