# BioIntel AI Step 196 Installer Contract Fix V2

## Reproduced failure

The Step 196 post-install mandatory self-test failed with:

```text
Windows installer contract: FAIL
RuntimeError: installer markers/Python locator missing
```

## Root cause

The active installer correctly checked `step196_part1.ok` through `step196_part4.ok` and used `install_windows_step196.py`, but the historical Step 193 mandatory self-test still required the literal text `step193_part%%P.ok`. It also used an exact Step 193 baseline-version comparison instead of validating compatibility with the current application version.

## Fixes

- Detect the active installer helper from `INSTALL_WINDOWS.bat`.
- Detect the active release marker step dynamically.
- Verify the corresponding `STEP<step>_RELEASE.json`.
- Verify the Python 3.11 locator both exists and is referenced.
- Verify the active installer calls the mandatory self-test and wheelhouse validator.
- Compare the current package version with `VERSION`.
- Treat Step 193 version 15.1.0 as a compatible mandatory baseline for current version 15.3.0.
- Run a contract-only self-test before virtual-environment installation or repair.
- Update path-safe startup and repair launchers to Step 196.
- Add regression tests for the exact failure.

## Expected corrected output

```text
Version compatibility: PASS
Windows installer contract: PASS
Step 196 markers, scripts/install_windows_step196.py and Python locator aligned
```

The normal user flow remains only:

1. `INSTALL_WINDOWS.bat`
2. `RUN_BOTH_WINDOWS.bat`
