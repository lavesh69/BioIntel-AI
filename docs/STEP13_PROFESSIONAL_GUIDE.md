# Step 13 Professional Operations Guide

## Executive Overview

Use Executive Overview for:

- Workspace maturity
- Portfolio health
- Risk counts
- Readiness gaps
- Priority project review

## Project Portfolio

Recommended status flow:

```text
Planning → Active → Validation → Completed
```

Use `Paused` for temporarily blocked work and `Archived` for retained history.

Priority guidance:

- Critical: immediate leadership attention
- High: current-cycle priority
- Medium: planned standard work
- Low: exploratory or backlog

## Activity & Risk Center

Alerts are generated locally from current workspace evidence. Dismissing an
alert hides that exact alert identifier until restored.

State file:

```text
reports/activity_state.json
```

## Project evidence linkage

Link projects to:

- Dataset registry SHA-256
- Trusted model filename

This improves provenance and increases the executive maturity score.

## Local privacy

Project records, alert state and reports remain in the local project folder.
They are included in workspace backup and visible in Local Data Manager.
