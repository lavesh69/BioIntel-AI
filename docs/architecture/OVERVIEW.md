# BioIntel AI architecture overview

BioIntel AI Step206 is a Windows-first, local-first modular research platform. Its default managed deployment uses a Streamlit interface, local FastAPI service, persistent background worker and SQLite-backed local state under a dedicated UserData directory. PostgreSQL, Redis, object storage, OIDC and collaborative services are optional deployment adapters; they are not required by the offline core.

## Runtime flow

1. `INSTALL_WINDOWS.bat` validates the four-part extraction, exact CPython 3.11.x x64 runtime, source hashes and offline wheelhouse before atomically activating a managed release.
2. `RUN_BOTH_WINDOWS.bat` delegates to the active release launcher.
3. The Step206 supervisor starts the background worker, API and Streamlit UI, then requires worker heartbeat, API/version/database health and Streamlit health before reporting readiness.
4. Stop, restart, repair, diagnosis, Safe Mode and uninstall use owned-process and stable-path controls.

## Application layers

- `src/biointel/ui`: navigation catalogue, shared design components, runtime guards and state helpers.
- `src/biointel`: scientific domains, services, validation contracts, operations, adapters and registries.
- `pages`: user-facing Streamlit workspaces; every page is mapped once by the navigation/product registry.
- `scripts`: installer, supervisor, qualification, packaging, diagnostics and controlled operational entry points.
- `models`, `config`, `data` and `wheelhouse`: versioned local artifacts, metadata, labelled samples/templates and offline runtime assets.
- `UserData`: local projects, reports, exports, settings, databases, backups and runtime evidence; separated from replaceable application code.

## Control boundaries

- Core navigation must start without Ollama, SearXNG, internet providers, external engines, model packs or licensed reference databases.
- Module failures are contained by the UI runtime guard and produce a recovery reference rather than terminating unrelated pages.
- External executables and assets remain fail-closed until identity, licence, checksum, compatibility and target-machine evidence pass.
- Long-running work uses the persistent job engine where supported, including progress, cancellation/retry, results and recovery state.
- Scientific results retain available input/output hashes, parameters, module/software versions and dependency identity.

## Authoritative metadata

`biointel.ui.navigation.PAGE_CATALOG` is the single route/navigation source. `biointel.product_registry` enriches those same records with scientific inputs, outputs, engines, models, references, providers, validation, optimization, samples, templates, limitations and fallbacks without maintaining a second route list. Release exports are generated from these sources before packaging.

See `docs/PROJECT_ARCHITECTURE.md`, `docs/ARCHITECTURE_DECISIONS.md`, `docs/DEVELOPER_GUIDE.md` and the machine-readable registries under `release/ultimate_registry`.
