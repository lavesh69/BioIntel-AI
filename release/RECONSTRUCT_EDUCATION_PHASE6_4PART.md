# Reconstruct BioIntel AI Education Phase 6

Place all four matching Phase 6 ZIP archives and `EXTRACT_INSTALL_RUN_EDUCATION_4PART_WINDOWS.bat` in the same empty folder.

## Automatic method

Run `EXTRACT_INSTALL_RUN_EDUCATION_4PART_WINDOWS.bat`.

## Manual method

1. Extract all four archives into one empty folder.
2. Confirm that all files merge into one `BioIntel-Step220` directory.
3. Confirm `.release_parts/shiro4_part1.ok` through `shiro4_part4.ok` exist.
4. Run `BioIntel-Step220/INSTALL_WINDOWS.bat`.
5. Run `BioIntel-Step220/RUN_BOTH_WINDOWS.bat`.
6. Run `BioIntel-Step220/VERIFY_EDUCATION_PHASE6_WINDOWS.bat`.

Do not combine files from different Education phases. Runtime/user data is stored separately under `%LOCALAPPDATA%/BioIntelAI/UserData` and is excluded from release archives.
