# Step 15 — Data and Model Shortcomings Fixed

## Too little bundled data

The workspace previously shipped with only a 96-row demonstration CSV.
Step 15 adds 1,920-row and 5,760-row DTI packs plus a 250-row batch sample.

## Empty module experience

Training, prediction, feature building, batch jobs and data quality now open
with bundled data choices instead of requiring the user to create a CSV first.

## Too few molecular and protein examples

Step 15 includes 240 valid molecular structures and 24 target sequences.

## Too few trained models

Four additional pack-v2 models are bundled, benchmarked and catalogued.

## No model comparison

Classification and regression leaderboards now show held-out metrics,
training pack, row counts and best-model status.

## Slow repeated feature extraction

Drug and protein features are cached by unique entity, preventing thousands of
repeated calculations on Cartesian-pair datasets.

## Dataset registry could be empty

Bundled classification and regression views can be reseeded into the registry
with hashes and parent lineage.

## No easy rebuild

A one-click Windows builder regenerates packs, retrains/reuses models and runs
an integrity smoke test.

## Real-data path was hard to start

Official ChEMBL target recipes now prefill the live builder while retaining
mandatory manual review warnings.

## No corruption detection

Diagnostics verify every bundled data/library file against SHA-256 values stored
in the data-pack manifest.
