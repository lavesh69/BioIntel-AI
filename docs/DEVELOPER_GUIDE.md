# BioIntel AI Developer Guide

## Architecture boundaries

`src/biointel` contains reusable domain, platform, security, storage and UI services. `app.py` and `pages/` are Streamlit composition surfaces. `biointel.api.main` is the FastAPI boundary. Long-running work belongs in the persistent background-job service, not a Streamlit rerun. Windows install and runtime contracts live in `scripts/*step206.py` and root batch entry points.

The authoritative page list is `biointel.ui.navigation.PAGE_CATALOG`. `biointel.product_registry` enriches that list from existing next-generation and scientific-depth catalogs; it must not become a second hand-maintained navigation list. Run `scripts/export_ultimate_registries.py` after changing pages, module contracts, engines, models or reference templates.

## Development setup

Use the locked dependency routes in `requirements.lock`, `constraints.txt` and the platform-specific lock files. On Windows release paths, exact CPython 3.11.x x64 is mandatory. Keep generated caches, virtual environments, runtime SQLite files and `node_modules` out of release archives.

## Engineering rules

- Validate uploaded names, sizes, content signatures and archive extraction paths.
- Use argument arrays for subprocesses; do not construct shell commands from user input.
- Keep credentials in environment/configuration stores and redact diagnostics.
- Isolate optional imports and external services so core startup remains offline-capable.
- Preserve raw inputs, normalized data, parameters, random seeds, tool/model/reference versions and output hashes in scientific provenance.
- Label synthetic/demo outputs and exploratory calculations. Do not convert software test success into scientific or clinical validation claims.
- Add regression tests with every critical fix.

## Verification

Run targeted tests first, then the current Step206 suite, page static/AppTest gates, security checks, dependency verification, registry export and release gate. Build final archives only with `scripts/step206_package_professional.py`; it regenerates the source manifest, registry artifacts, four-part integrity report, SHA-256 sums and external final release manifest.

Native Windows installer/start/stop/restart behaviour must be physically tested on supported Windows hardware before public distribution. Linux CI can validate source contracts but cannot replace that evidence.
