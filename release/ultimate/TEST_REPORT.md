# Ultimate Professional Release Test Report

Release date: 2026-07-19

## Current hardening-change verification

- Python source compilation: passed.
- Step173 static qualification: passed for 1,723 Python files and 268 page files.
- SQLite qualification: 52/52 databases healthy, 120,020 rows inspected and zero foreign-key violations.
- Central registry integrity: 269/269 application and page entries mapped with no duplicate, missing or undeclared page.
- Exported registries: 269 modules, 76 engine definitions, 25 model artifacts and 18 reference templates.
- Targeted lifecycle, installer, safe-mode, registry, packaging and acceptance regression checks: 31/31 passed.
- Step206 quick source release gate: passed.
- Windows diagnostic quick gate and uninstall dry-run: passed.
- Dependency lock: valid, 32 locked packages, expected lock SHA-256 matched.
- Offline Windows wheelhouse: 121/121 files present, hashed and structurally valid.
- Mobile clean install, TypeScript compilation and Vite production build: passed.
- Desktop main-process JavaScript syntax check: passed.
- Desktop and mobile production dependency audits: zero reported vulnerabilities.

## Preserved verified baseline

The reconstructed professional baseline shipped its own successful evidence for 321 backend/API/scientific/module/Windows/workspace/engine/neuro tests, 269/269 UI static page checks, 538/538 UI static/runtime AppTest checks with zero page exceptions, 47/47 starter kits and 80/80 demo bundles. The current changes preserve that baseline and add focused regression gates for the new controls.

## Final package gate

The release packager regenerates the source manifest and then verifies all five archives for CRC integrity, exact source coverage, duplicate absence, safe paths, matching archive roots, part markers and SHA-256 hashes. Exact results are written to `STEP206_PACKAGE_INTEGRITY.json`, `BIOINTEL_FINAL_RELEASE_MANIFEST.json` and `SHA256SUMS.txt` outside the archives.

## Honest execution boundary

This Linux builder does not contain the release's full Streamlit/RDKit scientific runtime and is not native Windows hardware, so the complete inherited AppTest suite, RDKit benchmark and physical Windows install/start/stop/restart/uninstall workflow were not re-executed here. Native Windows lifecycle, security-product compatibility, optional GPU/instrument integration and external scientific assets remain explicit deployment gates; none is inferred from container checks.
