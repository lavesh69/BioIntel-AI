# Phase 31–35 Windows Report

## Native source qualification

The canonical app started through a hidden Windows process using CPython 3.11.9 and
Streamlit 1.58.0, returned `200 ok` at `/_stcore/health`, used a spaced/Unicode isolated
user-data path, and stopped with both the PID and endpoint gone.

## Production and installer qualification

- Production ZIP: protected application plus bundled CPython 3.11 runtime.
- Installed protected AppTest: 0 exceptions.
- Upgrade test: passed; a seeded previous release was moved to the rollback area.
- Launcher and runtime presence: passed.
- Native launcher: returned `200 ok`.
- Stop control: supervisor PID gone, backend PID gone, endpoint gone.
- Visible terminal: none; VBS, `pythonw.exe`, and Windows `winexe` are used.
- Actual installer executable dependency check: passed with exit code 2 when its
  adjacent production ZIP was deliberately absent.
- Installer engine full extraction/upgrade test: passed in an isolated target.
- Administrator rights: not required for the default per-user LocalAppData target.

The sandbox could not create the OneDrive desktop shortcut during isolated testing.
The installer treated this as non-fatal and the application launcher remained present.

## Path qualification

Canonical source and user-data paths included spaces and Unicode. An exceptionally deep
build-staging path exceeded the native RDKit DLL loader's practical Windows path limit.
The same package passed at the normal installed path. Installation under
`%LOCALAPPDATA%\BioIntelAI\current` or another short root is required.

## Platform scope

Validated on the attached Windows x64 environment. Clean-machine Windows 10/11,
enterprise policy, antivirus/SmartScreen, code-signing reputation, OneDrive Desktop,
and institutional endpoint-management variants require external qualification.
