# Step 10 — Shortcomings Fixed

## Dataset provenance

Previously datasets had hashes inside model metadata but no searchable version
registry or parent-child lineage. Step 10 adds a local dataset registry with
version, source, task, parent hash, notes and profile metadata.

## Model clutter

Previously every saved model appeared equally in prediction screens. Step 10
adds candidate, active and archived states plus one default model.

## Large batch reliability

Previously batch prediction ran as one operation. Step 10 adds chunked
processing, CSV checkpoints and resume support.

## Workflow visibility

Previously datasets, experiments, models, diagnostics and storage were spread
across different pages. Step 10 adds a unified Workflow Dashboard.

## Nested generated files

Previously nested batch-job reports were not always visible to cleanup or
workspace backup tools. Step 10 makes report and cache handling recursive.

## Ease of use

Training now registers the cleaned dataset automatically. Saving a model also
creates its lifecycle entry, and the first saved model becomes the default.
