# Science Pulse Windows Qualification

Science Pulse is embedded in `BackgroundJobService`, which launches the single worker with `DETACHED_PROCESS`, `CREATE_NEW_PROCESS_GROUP`, and `CREATE_NO_WINDOW`. Runtime smoke mode sets `BIOINTEL_RUNTIME_SMOKE_TEST=1`, initializes the scheduler/database, and forbids provider network work. Stop files and finally-block lease release provide clean shutdown.

Controls are supplied for start, stop, restart, health, force-safe-sync, diagnostics, and scheduler repair. Paths are passed as argument arrays and tested from a workspace containing spaces. Full real-duration hourly/day-long waiting is represented by deterministic clock/state tests, not a fabricated wall-clock claim.

Actual Windows supervisor smoke result: **PASSED** in 60.4 seconds with hidden worker, API, and Streamlit startup; localhost health checks succeeded and final cleanup completed. The smoke environment forced Science Pulse offline mode.
