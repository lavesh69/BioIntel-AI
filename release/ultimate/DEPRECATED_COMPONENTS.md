# Deprecated Components

No module or user feature was removed.

The following historical entry points remain only as compatibility delegates and should not be used in new automation:

- Step196 installer/launcher Python entry points delegate to Step206.
- `REPAIR_BIOINTEL_WINDOWS.bat` delegates to `REPAIR_WINDOWS.bat`.
- Older Step159–205 package markers are compatibility markers only; Step206 parts 1–5 are the physical release contract.
- Legacy support-bundle launchers may remain for compatibility; `DIAGNOSE_WINDOWS.bat` is the canonical diagnostic entry point.

Compatibility delegates must not be interpreted as separate active releases.
