# Real DTI Dataset Guide

## Minimum classification columns

```text
canonical_smiles,protein_sequence,label
```

Labels must be exactly `0` or `1`.

## Minimum regression columns

```text
canonical_smiles,protein_sequence,p_activity
```

## Strongly recommended columns

```text
drug_id,target_id,activity_type,activity_value,activity_unit,
source,assay_id,document_id,organism
```

## Quality rules

- Use canonicalized valid SMILES.
- Use valid protein amino-acid sequences.
- Keep assay type consistent.
- Do not mix Kd, Ki, IC50 and EC50 by default.
- Standardize concentration units before pActivity conversion.
- Investigate duplicate and conflicting drug–target pairs.
- Record assay and publication provenance.
- Avoid inventing negative pairs without a defensible method.
- Use leakage-resistant splits.
- Keep the final test set untouched until evaluation.
- Report uncertainty, class balance and applicability limits.

## Recommended evaluation hierarchy

1. Random-pair split for software debugging only
2. Drug-group or target-group split
3. Molecular-scaffold split
4. External temporal or independent validation dataset
5. Experimental validation

## Important limitation

A high ROC-AUC, probability or pActivity estimate does not prove binding,
therapeutic effect, safety, selectivity or clinical usefulness.
