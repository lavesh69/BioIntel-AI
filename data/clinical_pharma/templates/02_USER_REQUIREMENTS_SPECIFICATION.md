# User Requirements Specification

| Requirement ID | Requirement | Risk | Verification method | Acceptance criterion | Owner |
|---|---|---|---|---|---|
| URS-001 | Intended use is displayed and enforced | High | Inspection/test | Prohibited claims are blocked | |
| URS-002 | Model/data/code/environment hashes are frozen | High | Test | SHA-256 values are immutable | |
| URS-003 | Predictions are locked before outcomes | High | Test | Timestamp and audit proof present | |
| URS-004 | Audit trail is tamper-evident | High | Challenge test | Tampering is detected | |
| URS-005 | Validation dossier is checksum-verifiable | High | Verification | All manifest hashes pass | |
