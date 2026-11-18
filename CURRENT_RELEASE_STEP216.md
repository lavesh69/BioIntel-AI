# BioIntel AI 15.6.0 - Step216 Release Readiness Upgrade (V19.6.1)

Step216 is the active software-readiness layer for the Windows V19.6 package.
The physical installer remains the verified Step206 four-part release and keeps
the required workflow:

1. `INSTALL_WINDOWS.bat`
2. `RUN_BOTH_WINDOWS.bat`

The upgrade adds a Step216 readiness scanner, Project Status visibility,
refreshed build provenance and a Windows verification launcher:
`VERIFY_STEP216_RELEASE_READINESS_WINDOWS.bat`.

The Step215 Engine Control Center, 76-engine registry, 12 adapter contracts,
offline Windows CPython 3.11 wheelhouse, Live Workspace collaboration layer and
UserData-preserving recovery controls are retained.

External engines remain unqualified until exact upstream artifact, licence,
checksum and target-machine evidence passes. This package is research software,
not clinical, regulatory or wet-lab validation.