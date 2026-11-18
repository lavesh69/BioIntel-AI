# Step 124 Canvas Rendering Hotfix

**Product version:** 12.4.0 (preserved)

## Reported symptom

Genome-track and sequence-feature canvases could appear as concatenated plain text after a Streamlit rerun or after navigating between modules. Track bars, cards and lane spacing were visually absent even though their HTML content was present.

## Root cause

The non-chart visual stylesheet was guarded by a value in `st.session_state`. Streamlit retains session state but rebuilds the page DOM on rerun. After the first render, the guard prevented the stylesheet from being emitted again, so the recreated canvas markup had no local CSS.

## Fix

- Removed the session-level stylesheet guard.
- Emit the compact non-chart canvas stylesheet on every renderer call.
- Added a stable stylesheet identifier.
- Hardened shell, grid, card, lane and segment display rules.
- Added wrapping and minimum-width protections for long scientific labels.
- Preserved all 15 advanced non-chart canvases and all connected modules.
- Added regression tests for consecutive rerenders.

## Functional impact

No scientific algorithm, module, database, model, reference asset or workflow was removed or changed. This is a rendering-consistency hotfix only.


## Validation

- Hotfix verification: **8/8 passed**
- Focused source tests: **9/9 passed**
- Step 124 + canvas regression bundle: **18/18 passed**
- Affected runtime pages: **12/12 passed**
- Opened canvas instances: **17/17**
- Consecutive rerun exceptions: **0**
- Existing project files removed: **0**
- Existing project files changed: **1**
- New hotfix/report/test files: **6**
