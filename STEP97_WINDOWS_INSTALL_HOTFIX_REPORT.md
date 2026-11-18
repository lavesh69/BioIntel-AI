# BioIntel AI Step 97 Windows Installation Hotfix

## Confirmed recurring causes

- Absolute application paths were passed through nested CMD/Python quoting. A malformed trailing quote produced paths such as `BioIntel-AI"\requirements.lock`, causing Windows `OSError 22` and `GetFullPath` illegal-character failures.
- The legacy dual launcher opened the browser after a fixed two-second delay, before Streamlit was guaranteed to be ready, producing `127.0.0.1 refused to connect`.
- Partial or incompatible `.venv` folders could be reused instead of rebuilt.
- Several repair/install commands repeated `--root "%CD%"`, preserving the same quoting risk.

## Repairs

- The two public BAT files are now minimal wrappers around path-safe PowerShell helpers.
- Helpers derive the application folder from `$PSScriptRoot`; no absolute app-root argument crosses CMD/Python boundaries.
- Dependency, wheelhouse, self-test and preflight checks use working-directory `--root .`.
- Python verifiers sanitize accidental leading/trailing quote characters and report missing files clearly.
- Incomplete or incompatible `.venv` folders are automatically rebuilt once.
- UI and API launch on free localhost ports, write separate logs, wait up to 120 seconds for HTTP readiness, and only then open the browser.
- A second launch reopens an already healthy session rather than creating duplicate servers.

## Boundary

The package was statically verified and archive-tested in the build environment. A physical Windows double-click cannot be executed in this Linux build environment; therefore the package includes target-machine preflight, dependency checks, self-test, HTTP readiness checks and actionable logs.
