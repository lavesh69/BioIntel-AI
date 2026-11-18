# BioIntel Connect Windows Qualification
Generated: 2026-07-27 05:02:42 UTC
OS Target: Windows 10 / Windows 11 (x64)
Python Runtime: CPython 3.11.9 x64

## Windows Desktop Verification Matrix
| Component | Status | Details |
|---|---|---|
| CPython 3.11.9 x64 | PASSED | Environment verified at `AppData\Local\Programs\Python\Python311` |
| Release Gate Preflight | PASSED | `scripts\step206_release_gate.py` passed with 0 errors |
| Native Windows Smoke Test | PASSED | UI (8501), API (8000), and Worker lifecycle clean shutdown verified |
| Windows Long Paths | PASSED | Native path handling enabled |
| Non-Admin User Execution | PASSED | Runs within LocalAppData without elevated privilege requirements |
| Space-in-Path Compatibility | PASSED | Tested path: `C:\Users\lavesh dobriyal\.gemini...` |
