# BioIntel AI Step 196 · V15 Permanent Runtime Handover Fix

## Fixed

- Removes the false hard block: “A different extracted BioIntel release is already running.”
- `RUN_BOTH_WINDOWS.bat` now automatically hands over from a verified older BioIntel UI/API/worker to the current extracted release.
- Checks each PID's command line and recorded extraction root before it can be terminated.
- Discards stale, corrupt or PID-reused runtime records without touching an unrelated Windows process.
- Records the outcome in the local runtime reconciliation report.

## Data safety

The fix changes only runtime processes, the shared runtime-state record and local logs. It does not delete or overwrite project data, reports, workspaces, exports, projects or databases.

## Windows flow

1. Extract all five matching V15 ZIP files into one new empty folder.
2. Run `INSTALL_WINDOWS.bat`.
3. Run `RUN_BOTH_WINDOWS.bat`.

No manual shutdown of an older BioIntel window is required for the normal same-user case.
