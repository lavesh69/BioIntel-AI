# Risk Management File

| Hazard ID | Hazardous situation | Harm | Initial risk | Control | Verification | Residual risk | Acceptance |
|---|---|---|---|---|---|---|---|
| RSK-001 | Unvalidated prediction used for patient care | Incorrect decision | Critical | Research-only default and claim gate | UI/API negative test | | |
| RSK-002 | Data leakage inflates performance | False confidence | High | Entity/scaffold/temporal leakage audits | Independent validation | | |
| RSK-003 | Model changes after protocol approval | Invalid prospective result | High | Immutable model freeze | Hash verification | | |
| RSK-004 | Outcome visible before prediction lock | Biased validation | High | Prediction timestamp and audit chain | Reconciliation test | | |
| RSK-005 | Site or subgroup performance failure hidden | Unequal performance | High | Predefined subgroup analysis | Statistical review | | |
