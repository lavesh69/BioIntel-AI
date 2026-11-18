# BioIntel AI 15.6.0 - Step217 Production Enablement Controls (V20.0)

BioIntel remains a Windows-first, local-first research platform. The required user workflow remains INSTALL_WINDOWS.bat followed by RUN_BOTH_WINDOWS.bat.

Step217 is the active software-control layer on the verified Step206 four-part Windows package. Step216 release-readiness verification and the Step215 Engine Platform are retained.

Step217 adds:

- qualified-engine-only native pipeline execution with raw-input hashes, QC, native command evidence, result validation, parsing, provenance and reports;
- nine priority workflow contracts for VEP, PLINK2, SAIGE, Kraken2, HUMAnN, Vina, GROMACS, Cellpose and OpenSlide;
- strict model candidate and external benchmark policy while preserving synthetic/demo quarantine;
- operational, platform, assurance and internal workspace surfaces;
- Ed25519-signed plugin and update archive verification with safe extraction;
- tenant-scoped PostgreSQL, Redis and S3/MinIO adapters;
- OIDC/JWKS token verification and SCIM user validation contracts;
- FHIR, DICOMweb, REDCap and LIMS connector clients;
- qualification-gated vector retrieval and citation-checked biomedical RAG;
- a Production Enablement Center and Step217 release gate.

Run VERIFY_STEP217_PRODUCTION_ENABLEMENT_WINDOWS.bat to verify installed software controls. A passing software-control gate does not mean production evidence is complete.

Target-machine engines, authentic model weights, enterprise services, hospital credentials, publisher certificates, independent scientific validation, wet-lab confirmation, clinical validation and regulatory approval remain fail-closed external requirements.
