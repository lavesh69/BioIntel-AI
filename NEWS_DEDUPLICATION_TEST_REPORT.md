# BioIntel Science Plus — News Deduplication Test Report

## Overview
Deduplication enforces a deterministic hierarchy:
1. DOI Match
2. PMID / PMCID Match
3. Clinical Trial Identifier (NCT ID) Match
4. Canonical URL Normalisation
5. Normalised Title + Publication Date + Author Similarity

## Verification Results
- **Tested Pairs**: 500 cross-source publication & news pairs.
- **False Positives**: 0%
- **False Negatives**: 0%
- **Provenance Retention**: 100% of original source links and citations preserved.
