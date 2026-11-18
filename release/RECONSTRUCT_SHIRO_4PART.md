# Reconstruct and install the Shiro four-part Windows release

Recommended: place all four ZIPs and `EXTRACT_INSTALL_RUN_SHIRO_4PART_WINDOWS.bat` in one folder, then run the BAT file.

Manual method:
1. Extract all four `BioIntel-AI-15.6.0-SHIRO-FULL-WINDOWS-4PART-PartN.zip` archives into the same empty folder.
2. Confirm the result contains `BioIntel-Step220` and `.release_parts/shiro4_part1.ok` through `shiro4_part4.ok`.
3. Run `BioIntel-Step220\INSTALL_WINDOWS.bat`.
4. Run `BioIntel-Step220\RUN_BOTH_WINDOWS.bat` to start the Streamlit UI and local FastAPI service.

The four physical archives preserve the existing Step220 five-marker installer contract for backward compatibility. Do not run from inside a ZIP. Runtime data belongs under `%LOCALAPPDATA%\BioIntelAI\UserData`.
