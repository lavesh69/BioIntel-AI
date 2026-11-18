# BioIntel V19.6 Engine Platform — Installation Policy

BioIntel registers and manages 76 specialist engines, 12 advanced format adapters, five offline-pack families and six optional production services.

## Default two-step workflow

1. Run `INSTALL_WINDOWS.bat`.
2. Run `RUN_BOTH_WINDOWS.bat`.

The base installer initializes the Engine Control Center but does not silently download large, restricted or unqualified external tools. Engine installation is performed from integrity-verified offline packs or exact release manifests after licence, SHA-256 and target-machine smoke evidence is complete.

## Fail-closed rules

- Restricted provider downloads are never automated without user authorization.
- Model weights and reference databases are separate qualified assets.
- WSL2 engines remain unavailable when WSL2 is absent.
- A detected executable is marked available but not scientifically qualified.
- Binary scientific formats are not silently approximated.
- Personal Local Mode remains usable without external engines or production services.
