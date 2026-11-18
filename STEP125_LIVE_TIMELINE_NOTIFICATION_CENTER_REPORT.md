# BioIntel AI Step 125 — Live Analysis Timeline & Scientific Notification Center

**Version:** 12.6.0

## Fixed

### Live Analysis Timeline

- Every `analysis_run()` now receives a persistent run identifier.
- Preparing, validation, analysis and export stages are written to a durable SQLite timeline.
- The inline timeline updates while a workflow is executing and shows elapsed time, stage detail and real progress supplied by the workflow.
- Completed, failed and cancelled terminal states are persisted with the run manifest and error text.
- Stale `running` records from an interrupted desktop process are marked failed after the recovery threshold instead of remaining permanently active.
- The global shell combines interactive runs and persistent background jobs.
- Background jobs expose pause, resume and cancel controls where the job state allows them.
- Recent timelines can be expanded, reviewed and exported as JSON.

### Scientific Notification Center

- Notifications are persisted outside the Streamlit session and therefore survive navigation and desktop restarts.
- Unread/read/dismissed state is retained.
- Repeated events are deduplicated through stable keys instead of producing unlimited duplicate alerts.
- Severity levels are supported: info, success, warning, error and critical.
- Filters include Unread, All, and Warnings & errors.
- Notifications support deep links to the originating module or Performance & Job Center.
- Mark-read, dismiss, clear and JSON export controls are available.
- Completed, failed and cancelled analyses automatically generate notifications.
- Recent background-job terminal states are synchronized without reopening the same notification on every rerun.

## Safety and compatibility

- Notification persistence failures never interrupt scientific calculations.
- Existing session notifications remain available as a fallback.
- Existing Step 124 premium themes, animated heroes, glass panels and canvas hotfix remain present.
- Five requested source-locked modules remain byte-identical.
- No scientific module, database, model, wheel or reference asset was removed.

## Validation

- Step 125 verifier: 11/11 checks passed.
- Selected regression tests: 128 passed, 5 environment-gated skips, 0 failures.
- Representative Streamlit/AppTest surfaces: 5 passed with 0 runtime exceptions.
- Python syntax validation: 883 files passed.
- SQLite integrity: 36/36 healthy, 108,497 rows checked, 0 foreign-key issues.
- Full monolithic 993-test collection was attempted but exceeded the execution window; it is not claimed as fully passed.
