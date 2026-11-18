# FAIR Data and Reproducible Research

## Machine-actionable FAIR profile

The FAIR evaluator implements all 15 operational checks across Findable, Accessible, Interoperable and Reusable dimensions. It checks persistent identifiers, rich and indexed metadata, metadata persistence, standards-based access, authorization documentation, formal knowledge representation, resolvable vocabularies, qualified references, licensing, provenance and community standards.

A FAIR digital object is exported as JSON-LD with file-level SHA-256 checksums, distributions, creators, access terms, provenance and qualified references. Metadata persistence and a tombstone URL are required even if a data object is later withdrawn.

A 10/10 FAIR implementation score means the tooling and checks exist. Each real dataset still needs valid metadata, licenses, persistent identifiers and repository registration.

## Reproducibility bundle

The reproducibility bundle records:

- immutable hashes for inputs, code and artifacts;
- full parameters and random_seed;
- source revision when available;
- command line and environment details;
- direct package versions;
- deterministic archive metadata;
- embedded-file checksums and a verification report.

The bundle verifier fails on missing or modified embedded files. Independent rerun evidence is still required for a genuine reproducibility claim.
