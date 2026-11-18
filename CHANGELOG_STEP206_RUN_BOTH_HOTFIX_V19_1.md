# Step206 RUN_BOTH Windows Hotfix — V19.1

## Confirmed Windows failure

`RUN_BOTH_WINDOWS.bat` stopped during scientific runtime preflight because `VERSION` declared `15.6.0` while `pyproject.toml` still declared `15.5.0`.

## Fixes

- Aligned current product metadata to BioIntel AI `15.6.0`.
- Corrected Step206 scientific runtime marker detection to require and accept all four parts.
- Added pyproject validation to the Step206 release gate.
- Changed same-release repair logic to compare source manifests, so a stale managed Step206 copy is replaced rather than incorrectly reused.
- Corrected four-part installation wording and added focused regression checks.

## User workflow

Run `INSTALL_WINDOWS.bat` from the newly extracted V19.1 four-part package, then run `RUN_BOTH_WINDOWS.bat`. Existing project data under `%LOCALAPPDATA%\BioIntelAI\UserData` is preserved.
