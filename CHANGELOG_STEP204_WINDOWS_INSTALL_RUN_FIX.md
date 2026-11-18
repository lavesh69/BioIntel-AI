# Step204 Windows Install/Run Reliability Changelog

- Repackaged the canonical Step203 source into exactly four balanced ZIP parts.
- Added four-part Step204 extraction markers while retaining historical compatibility markers required by legacy internal checks.
- Enforced 64-bit CPython 3.11.9 exactly in detection, installation, virtual-environment validation, installer, and runtime launchers.
- Removed the fallback that could install an unspecified newer Python 3.11 patch.
- Added a current Step204 release gate and SHA-256 source-manifest validation inside `INSTALL_WINDOWS.bat`.
- Fixed `RUN_BOTH_WINDOWS.bat` marker/version messages, runtime-log directory creation, support-bundle reference, and failure propagation.
- Changed startup verification failure from a warning to an installation failure.
- Stopped the core installer and launcher from automatically installing, downloading, starting, or probing optional Ollama/SearXNG services.
- Hardened Desktop shortcut refresh and scoped stale-shortcut removal to BioIntel launchers only.
- Unified active documentation, installer titles, shortcut metadata, package root, and release record around product version 15.4.0 / Step204 / V17.1.
- Preserved excluded scientific modules without source changes.
