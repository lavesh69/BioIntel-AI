# Phase 31–35 Test Report

## Final focused regression

Command:

```text
python -m pytest -q tests/test_phase31_stabilization.py
  tests/test_education_phase32_sync.py
  tests/test_education_phase33_digital_twin.py
  tests/test_education_phase34_compute.py
  tests/test_education_phase35_discovery.py
  tests/test_phase31_35_cross_phase_workflows.py
  tests/test_phase31_35_security.py
  --disable-warnings --maxfail=1
```

Result: `48 passed, 0 failed, 0 skipped` in 19.13 seconds.

Breakdown:

- Phase 31 stabilization: 3 passed.
- Phase 32 secure sync: 7 passed.
- Phase 33 Digital Twin: 8 passed.
- Phase 34 Research Compute: 10 passed.
- Phase 35 Scientific Discovery: 10 passed.
- Cross-phase workflows: 5 passed.
- Focused security: 5 passed.

## Streamlit and package checks

- Canonical home AppTest after removal of three obsolete duplicate page aliases:
  0 exceptions.
- Installed protected production AppTest: 0 exceptions.
- Protected Phase 32 and Phase 33 page AppTests: passed with isolated user-data roots.
- Protected-runtime import gate: passed for Phase 32–35 services.

## Phase 31 full historical suite

Baseline: 1,931 passed, 279 failed, 28 skipped, 3 errors in 697.96 seconds.

Post-fix: 1,943 passed, 273 failed, 28 skipped, 0 errors in 683.97 seconds.

The historical suite is therefore `NOT_GREEN`. The 273 retained failures are older
release-contract/version/hash assertions and other accumulated platform debt; they are
not relabeled or hidden. No second costly full-suite run was performed after the final
launcher-only packaging corrections because the user set a 25-credit cap and the
application implementation did not change.

## Cross-phase evidence

The five workflows cover migration/restart persistence; multi-device conflict,
merge/checksum/revocation; Digital Twin learning/mastery/portfolio review; Research
Compute review/report/bundle; and Discovery/Twin/human-review integration.
