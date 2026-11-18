# Step 10 Workflow Guide

## 1. Register a dataset

Open **Dataset Registry & Lineage**, upload a CSV and review:

- Missing values
- Duplicates
- Numeric outliers
- Memory size
- Classification imbalance

Register the dataset with a name, version, source and optional parent dataset.

## 2. Train a model

Open **Model Training**. The cleaned training dataset is automatically
registered, and the experiment is saved when the model artifact is saved.

## 3. Promote a model

Open **Model Lifecycle**:

- `candidate`: under review
- `active`: approved for current research workflow
- `archived`: retained but hidden from prediction pages
- `default`: preselected in prediction and batch-job screens

## 4. Run prediction

Use **DTI Predictor** for individual or small batch jobs.

Use **Resumable Batch Prediction Jobs** for larger CSVs. Keep the same job name
to resume its checkpoint after interruption.

## 5. Review the workspace

Open **Workflow Dashboard** to see datasets, model states, experiments,
diagnostics and storage in one place.

## 6. Back up

Use **Workspace Backup & Restore**. Nested batch checkpoints and registries are
included in Step 10 backups.
