# Step 19 5X Data and Training Guide

## Recommended usage

Use the 160,000-row pack for scalability testing, full-data
classification benchmarks and grouped holdout validation.

Use smaller packs for rapid experimentation:

- Foundation: fast iteration
- Extended: general local benchmark
- Ultra: medium high-data benchmark
- Double Ultra: intermediate stress test
- 5X Ultra: maximum bundled full-data test

## Split policy

Classification uses `drug_group` to prevent the same molecule from
appearing across training, validation and test groups.

Regression uses `target_group` to prevent the same target from
appearing across groups.

## Performance policy

Pack-v5 tree models use bounded depth and leaf sizes. This avoids
oversized artifacts and impractical laptop rebuild times while still
fitting the complete 160,000-row dataset.

## Rebuild

Run:

```text
BUILD_DATA_AND_MODELS_WINDOWS.bat
```

Existing valid artifacts are reused. Missing pack-v5 artifacts are
trained individually and the benchmark is finalized only after all six
exist.

## Interpretation

ROC-AUC and RMSE values are synthetic held-out benchmark results.
They must not be described as real drug-discovery performance.
