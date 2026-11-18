# New Modules Windows Guide

Keep all four matching `EDUCATION-SCIENCE-ACADEMY` ZIPs together. Run the one-click extractor from Part 1, or extract all overlays into one folder so `BioIntel-Step220` merges exactly once. Run `INSTALL_WINDOWS.bat`; then use `RUN_BOTH_WINDOWS.bat` (UI + API). The installer targets a short managed LocalAppData path, requires CPython 3.11.x x64 and preserves UserData across upgrades. Use `STOP_BIOINTEL_WINDOWS.bat` for clean shutdown. External network services are disabled until configured.
