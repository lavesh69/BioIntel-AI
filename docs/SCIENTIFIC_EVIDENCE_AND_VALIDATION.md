# Scientific Evidence and Validation — Step 38

## Purpose

Step 38 adds a production-grade scientific evidence architecture. It separates three concepts that must never be conflated:

1. **Provider authenticity** — a record came from an official provider and its response was checksum-bound.
2. **Scientific suitability** — assay context, units, relations, organisms, duplicates, target confidence and provenance passed review.
3. **Release eligibility** — the dataset and model passed independent external validation, calibration, leakage checks, governance review and the required prospective study.

## Official provider layer

The provider hub uses HTTPS host allowlists for ChEMBL, UniProt, PubChem, RCSB PDB, ClinicalTrials.gov, ClinVar, GEO and BindingDB. Responses are cached with SHA-256, retrieval time, URL, ETag and Last-Modified metadata when supplied.

## Evidence lake

`reports/scientific_evidence.sqlite3` stores providers, snapshots, normalized evidence records, validation studies and a tamper-evident event chain. Foreign keys and content hashes are verified by qualification tests.

Bundled official seed records are **reference seeds**, not a substitute for a full provider release. Live sync is performed with:

```bash
python scripts/sync_scientific_evidence.py chembl --limit 1000
python scripts/sync_scientific_evidence.py uniprot --query "reviewed:true" --limit 500
python scripts/sync_scientific_evidence.py clinicaltrials --query oncology --limit 1000
python scripts/sync_scientific_evidence.py rcsb --pdb-id 1CRN
```

## DTI qualification

A full drug–target qualification requires:

- cold-drug, cold-target, cold-both, scaffold and protein-cluster splits;
- temporal and external-provider holdouts;
- explicit inactive records where available rather than treating unknown pairs as negatives;
- bootstrap confidence intervals and permutation tests;
- baseline-beating metrics;
- calibration and uncertainty coverage;
- zero prohibited entity overlap;
- immutable model, dataset and protocol hashes;
- independent external validation;
- pre-registered, blinded prospective outcomes for full qualification.

## Prospective studies

The prospective registry creates immutable protocols before outcomes exist, locks predictions, then accepts blinded outcomes from a named laboratory. An independent review is required for full scientific release.

## Qualification boundary

The repository can reach 10/10 implementation readiness because all controls exist and are tested. Actual scientific evidence does not reach 10/10 until sufficiently large licensed provider datasets, independent external benchmarks and prospective wet-lab outcomes have been completed and reviewed.
