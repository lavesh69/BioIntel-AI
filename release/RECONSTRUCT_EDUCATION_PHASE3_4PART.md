# Reconstruct and install BioIntel AI Education Phase 3

Place all four `BioIntel-AI-15.6.0-EDUCATION-PHASE3-PartN.zip` archives beside `EXTRACT_INSTALL_RUN_EDUCATION_4PART_WINDOWS.bat`, then run the BAT file.

Manual method:
1. Extract all four archives into the same empty folder.
2. Confirm one `BioIntel-Step220` tree and four `.release_parts/shiro4_partN.ok` markers exist.
3. Run `BioIntel-Step220\INSTALL_WINDOWS.bat`.
4. Run `BioIntel-Step220\RUN_BOTH_WINDOWS.bat`.
5. Run `BioIntel-Step220\VERIFY_EDUCATION_PHASE3_WINDOWS.bat`.

Do not run from inside a ZIP. Runtime data belongs under `%LOCALAPPDATA%\BioIntelAI\UserData` and is excluded from the release.
