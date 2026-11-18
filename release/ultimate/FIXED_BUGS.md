# Fixed Bugs — Ultimate Professional Hardening

- Corrected the current README's stale V19.1 heading and incorrect four-part installer statement.
- Corrected the User Guide's obsolete `RUN_APP_WINDOWS.bat` startup instruction to the supported `RUN_BOTH_WINDOWS.bat` workflow.
- Corrected architecture documentation that described optional PostgreSQL/Redis/object storage services as mandatory default state.
- Replaced the stale V19.5 current-release test report with verified V19.6 evidence and an honest builder boundary.
- Corrected the active Windows repair entry point, which still called Step196 validation and installation instead of Step206.
- Added exact Step206 package-part, source-integrity and managed-environment gates to repair.
- Added canonical diagnostic and safe-mode recovery paths so startup failures no longer depend on legacy support entry points.
- Prevented Safe Mode from enabling Live Workspace LAN hosting and disabled outbound internet, DNS resolution and optional external-engine actions for that session.
- Added safe-mode state to runtime evidence and bounded Streamlit upload/message sizes for recovery sessions.
- Closed release-contract gaps where repair, diagnose, safe mode and uninstall launchers were absent from installer validation and stable launcher creation.
- Consolidated user-facing module metadata into a derived authoritative registry, eliminating drift between navigation and release-status artifacts.
- Added final four-part manifest generation with exact archive names, byte sizes, SHA-256 checksums, extracted-size estimate and install instructions.

The prior professional hardening fixes remain included: raw-read timeout import repair, H5AD legacy observation recovery, deterministic Cox fallback, starter-kit/demo regeneration, UI API migration, safe page links, engine-pack cleanup, mobile lock portability and broad page AppTest coverage.
