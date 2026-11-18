# Phase 35 Agent Evaluation Report

## Test evidence

Command:

`python -m pytest -q tests/test_education_phase35_discovery.py`

Result: **10 passed in 12.53 seconds**.

The deterministic benchmark built a tenant-bound synthetic research workspace,
registered two local evidence fixtures, executed and human-reviewed agent tasks,
ran a checksummed Phase 34 compute fixture, registered a falsifiable hypothesis,
created a controlled experiment plan, persisted an unsafe-action refusal, and then
called the production evaluation service.

Measured evaluation result: **15 passed, 0 failed** for:

1. citation precision;
2. source existence as a registered local record;
3. evidence completeness;
4. unsupported-claim rate;
5. hypothesis testability;
6. methodology quality;
7. confounder identification;
8. statistical appropriateness;
9. approved-tool selection correctness;
10. data-permission compliance;
11. tenant isolation;
12. reproducibility;
13. unsafe-request refusal;
14. overclaim detection;
15. research-integrity behavior.

The evaluation record includes the fixture-manifest SHA-256, measured values for
every metric, pass/fail counts, suite version, and timestamp. Results are produced
from stored benchmark artifacts; `fabricated_results` and `external_services_used`
are both false.

## Limitations

This is deterministic internal fixture validation. It does not measure performance
on the live scientific literature, expert-level scientific judgment, production
loads, real patient data, clinical validity, external novelty, or misconduct.
