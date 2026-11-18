# Reconstruct and install the BioIntel Education Universe four-part Windows release

1. Place all four `BioIntel-AI-15.6.0-EDUCATION-UNIVERSE-PartN.zip` archives in one empty folder.
2. Extract all four archives into that same folder. They overlay into one `BioIntel-Step220` tree.
3. Confirm `.release_parts/shiro4_part1.ok` through `shiro4_part4.ok` exist.
4. Run `BioIntel-Step220\INSTALL_WINDOWS.bat`.
5. Run `BioIntel-Step220\RUN_BOTH_WINDOWS.bat` to start the UI and API.

Do not run from inside a ZIP. Runtime data belongs under `%LOCALAPPDATA%\BioIntelAI\UserData` and is excluded.
