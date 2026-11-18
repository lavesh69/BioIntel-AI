# Reconstruct the four-part release on Windows

1. Put all five `BioIntel-AI-15.6.0-COMPLETE-INTEGRATION-FIXED-5PART-PartN.zip` files in one folder.
2. Extract every ZIP into the same empty destination folder, in any order.
3. Confirm the result contains one `BioIntel-Step220` directory and all five `.release_parts/step220_partN.ok` markers.
4. Run `INSTALL_WINDOWS.bat`; after installation, use `RUN_BOTH_WINDOWS.bat`.

Do not run from inside a ZIP. Runtime data belongs under `%LOCALAPPDATA%\BioIntelAI\UserData`.
