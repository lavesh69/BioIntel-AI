# BioIntel AI Step212 — Engine Audit Summary

This is an engineering and redistribution-readiness audit. It does not claim that an engine is installed, licensed for every use, or scientifically qualified.

- Registered engines: **76**
- Audited engines: **76**
- Previously catalogued: **53**
- Newly covered in Step212: **23**
- P1 compulsory engines: **20**
- P2 high-value engines: **21**
- Native-Windows routes: **12**
- WSL2-related routes: **64**
- Engines requiring reference/database assets: **33**
- GPU/model-sensitive engines: **9**
- Eligible only after release hash + smoke qualification: **13**
- Legal review required before bundling: **56**
- Never auto-bundle: **2**

## Mandatory gate before any engine enters an install pack

1. Pin one exact upstream release.
2. Capture the official release URL and SHA-256.
3. Capture and hash the exact licence/notice files.
4. Record redistribution obligations and any user acceptance requirement.
5. Verify Windows-native or WSL2 execution on a clean Windows machine.
6. Run version, positive fixture and negative-control smoke tests.
7. Qualify required databases/model weights separately.
