# Step 14 Governance & Reproducibility Guide

## Recommended controlled workflow

```text
Project Portfolio
→ Governance Hub
→ Model/Data evidence
→ Release Readiness & Lineage
→ Evidence Package Studio
→ Independent review
```

## Milestones

A strong milestone includes:

- Specific deliverable
- Named owner/team label
- Due date
- Objective acceptance criteria
- Evidence reference

Use `Blocked` only when progress cannot continue without intervention.

## Decision log

Decision records are intentionally append-only. To change direction:

- Record a new decision
- Use `Superseded` for the old approach
- Use `Reversed` when a prior decision is formally undone
- Reference supporting experiments or reports

## Approval gates

Recommended sequence:

1. Data readiness
2. Model validation
3. External validation
4. Reproducibility
5. Release approval

A release should not be treated as controlled while a required gate is rejected
or conditional without documented closure.

## Readiness score

The score is a transparent operational indicator, not scientific proof.
A high score means required evidence has been recorded; it does not prove that
a model or drug candidate is biologically valid.

## Evidence package

Default package mode includes metadata and reports only.

Enable model-file inclusion only for trusted recipients because serialized
model artifacts must be loaded in a trusted local environment.

## Audit integrity

New project and governance events are linked through:

```text
prev_hash → event_hash
```

Legacy unchained events remain readable and are reported separately.

## Controlled project exchange

Exported project JSON can be imported under a new unique code. Dataset and model
references are preserved, but missing local evidence appears as a readiness gap.
