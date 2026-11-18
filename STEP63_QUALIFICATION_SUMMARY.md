# Step 63 Qualification Summary

## Status

**PASSED — BioIntel AI 6.3.0**

## Measured results

- New Step 63 tests: **24/24 passed**
- Legacy focused regressions: **32/32 passed**
- Total focused tests: **56/56 passed**
- Critical Discovery backend branch-aware coverage: **95.23%**
- Streamlit render and scientific-gate scenarios: **5/5 passed**
- Discovery API cases: **9/9 passed**
- Databases: **22/22 healthy**
- Rows checked: **106,782**
- Foreign-key violations: **0**
- Secret scan: **1,128 files, 0 findings**
- Discovery routes: **8/8 correctly grouped**
- Molecular benchmark: **200/200 successful**
- Store-release internal failures: **0**

## Core release guarantees

- Missing ranking values are never rewarded.
- Persistent Discovery projects preserve evidence, identities, rankings and checksums.
- Compound duplicates are controlled through exact and connectivity-layer identity.
- Multi-component ChEMBL targets are blocked unless explicitly resolved.
- Activity replicates and conflicts are visible and aggregatable.
- Synthetic DTI models remain exploratory and release-blocked.
- Unqualified ADMET endpoints remain not assessed.
- Docking cannot be represented as qualified without protocol evidence.
- Patent evidence is not represented as legal FTO clearance.
- Reproducibility bundles include versioned project content and file hashes.

## Evidence boundary

All **23** bundled DTI models are currently synthetic demonstrations and **0** are scientific-release eligible. Step 63 improves the software, governance and qualification architecture but does not fabricate external model validation, wet-lab evidence, patent opinions or regulatory outcomes.

## Verification commands

Linux/macOS:

```bash
./VERIFY_STEP63_DISCOVERY_LINUX.sh
```

Windows:

```text
VERIFY_STEP63_DISCOVERY_WINDOWS.bat
```

Machine-readable evidence:

```text
reports/step63_discovery_qualification.json
reports/step63_discovery_core_coverage.json
reports/step63_store_release_verification.json
```
