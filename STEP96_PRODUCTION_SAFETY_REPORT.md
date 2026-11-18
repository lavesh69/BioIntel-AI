# BioIntel AI Step 96 — Production Safety & Real-Asset Upgrade

## Result

Step 96 reaches **10/10 implementation readiness for the software-controlled scope**: transactional installation, full-file UserData safety, rollback, scientific reference-asset management, external model package qualification, instrument export normalization and optional production-service probes.

## Completed upgrades

- Application code and persistent UserData are physically separated.
- Every upgrade uses a staging directory; the active app is not overwritten in place.
- `data`, `reports`, `workspace`, `exports` and `projects` receive a complete SHA-256 backup manifest.
- Failed first installs and failed upgrades restore the exact pre-install UserData state.
- Missing Python 3.11 can be obtained from the official Python Software Foundation Windows installer after Windows Authenticode validation.
- Reference assets support resumable HTTPS download, expected SHA-256, licence acknowledgement, safe ZIP/TAR extraction budgets, version tracking and an SQLite event registry.
- External model packages are inspected without deserializing or executing the model artifact.
- Model card, dataset manifest, metrics and model artifacts must all be covered by the package SHA-256 manifest.
- RDML, QuantStudio, CFX, LightCycler, SoftMax and Gen5 imports preserve original source columns and emit canonical mappings.
- PostgreSQL, Redis and MinIO/S3 probes redact credentials and provide connectivity evidence.
- Advanced-tool storage is standardized at `%LOCALAPPDATA%\BioIntelAI\Tools`.

## Verification

- Focused regression and Step 96 tests: **48 passed**
- New page import smoke checks: **4/4 passed**
- Python compilation: **passed**
- Dependency lock: **32 packages, valid**
- Offline Windows wheelhouse: **102/102 verified**
- SQLite databases: **28/28 healthy**
- Foreign-key violations: **0**
- Database rows checked: **107,472**
- Advanced tools registered: **44**

## Honest remaining external work

A signed EXE/MSIX requires the publisher's code-signing certificate and Store identity. The Windows transaction flow still needs a real clean-machine Windows 10/11 certification run. Large reference databases, licensed packages and GPU weights are installed separately because of size, licence and release constraints. Independent wet-lab outcomes, journal acceptance, regulatory approval and sustained production history cannot be generated inside source code.
