# Step 30 Scientific Data Foundation Guide

## Purpose

Step 30 provides larger, internally consistent reference datasets so that
BioIntel workflows can be demonstrated, tested and benchmarked without empty or
tiny tables. These files are not substitutes for real experimental studies.

## Reload

Run:

```bat
LOAD_SCIENTIFIC_REFERENCE_DATA_WINDOWS.bat
```

The operation is deterministic and idempotent. It regenerates the Step 30
reference files, refreshes their dataset hashes, rebuilds extended scientific
registry tables, expands the feature cache and synchronizes Knowledge/Asset
indexes.

## Verification

Run:

```bat
VERIFY_STEP30_WINDOWS.bat
```

The verifier checks file sizes/counts, dataset release-blocking metadata,
registry depth, evidence replicates, source catalogue, feature cache, 23 model
artifacts and all primary database integrity results.

## Real-data migration

Use the existing importers for real user-supplied data. Real datasets must keep
source licence, release, checksum and evidence information and should not reuse
Step 30 reference identifiers. The scientific release gate remains the final
control before a model is represented as externally validated.
