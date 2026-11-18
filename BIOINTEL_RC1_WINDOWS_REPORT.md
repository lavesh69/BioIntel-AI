# BioIntel AI 15.6.0 RC1 Windows Desktop Qualification Report

## System Environment
- **OS**: Windows 10 / Windows 11 x64
- **Launcher Scripts Tested**: `INSTALL_WINDOWS.bat`, `REPAIR_INSTALL_WINDOWS.bat`, `RUN_BOTH_WINDOWS.bat`
- **Python Version**: CPython 3.11.x / 3.14.x x64
- **PowerShell Version**: 5.1+

## Qualification Results
- **Clean Installation**: Passed
- **UserData Preservation**: Verified (Databases located in `%LOCALAPPDATA%\BioIntelAI\UserData`)
- **Long Path Strategy**: Explorer long-path mitigation verified
- **Non-Admin Execution**: Passed
