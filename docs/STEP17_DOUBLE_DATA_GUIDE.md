# Step 17 Double-Data Guide

## Pack dimensions

```text
640 molecules × 50 protein targets = 32,000 pairs
```

The pack is balanced around its generated median activity score and supports
both classification (`label`) and regression (`p_activity`).

## Recommended use

- Stress-test local ML pipelines
- Compare tree and regularised linear models
- Validate grouped splitting and cache performance
- Test batch prediction and registry lineage
- Learn the complete data-to-model workflow

## Recommended splits

- Classification: `drug_group`
- Regression: `target_group`
- Real chemical data: scaffold-aware split

## Interpreting results

More rows can make grouped generalisation harder when they introduce new
molecules and targets. A lower metric on the Double Ultra pack does not mean the
training failed; it can indicate a more diverse and difficult test set.

## Real-data progression

1. Use Double Ultra to verify software behaviour.
2. Build reviewed ChEMBL data.
3. Register dataset provenance.
4. Compare multiple algorithms.
5. Use scaffold/target-group splits.
6. Validate on an independent external dataset.
