# Reconstruct and install the Education, Science Pulse and Academy four-part Windows release

Recommended: place all four ZIPs and `EXTRACT_INSTALL_RUN_EDUCATION_4PART_WINDOWS.bat` in one folder, then run the BAT file.

Manual method:
1. Extract all four `BioIntel-AI-15.6.0-EDUCATION-SCIENCE-ACADEMY-PartN.zip` archives into the same empty folder.
2. Confirm the result contains one `BioIntel-Step220` tree and four compatibility markers.
3. Run `BioIntel-Step220\INSTALL_WINDOWS.bat`.
4. Run `BioIntel-Step220\RUN_BOTH_WINDOWS.bat` to start the UI and API.

Do not run from inside a ZIP. Runtime data belongs under `%LOCALAPPDATA%\BioIntelAI\UserData` and is not packaged.
