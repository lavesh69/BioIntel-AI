# BioIntel AI Step 196 V9 — Test Report

## Source checks completed before packaging

| Check | Result |
| --- | --- |
| Changed Python syntax (`py_compile`) | Pass |
| V9 release JSON parse | Pass |
| Weak-module installation-plan smoke test | Pass: 25 modules, 34 public targeted engines, 5 manual/provider engines, 7 small public references (1.8 GB) |
| Raw `st.json` scan in pages/UI renderers | Pass: only static regression/scoring text matches remain; no direct UI JSON wall call |
| Protected-module changes | No protected page edited in V9 |
| Windows-specific runtime execution | Not run on this Linux build host; V9 records a Windows/WSL2 availability state rather than claiming it ran |

## Behaviour covered by source changes

- Core installation releases its lock before the scientific-runtime worker starts, so unavailable WSL2, provider/network outages and large references cannot break the offline app.
- Small public reference downloads now retain resumable partial files, recognise a completed local target, enforce the configured size policy and return a friendly optional-service-unavailable state instead of raising an unhandled failure.
- Downloaded references and installed engines are visible as awaiting qualification; they are not counted as qualified or controlled-release evidence.

## Final release validation

| Check | Result |
| --- | --- |
| Source manifest deep hashes | Pass: 25,125 entries checked, 0 mismatches |
| Four-part package membership | Pass: 25,127 source files packaged, 0 missing, 0 extra, 0 duplicate |
| ZIP CRC and unsafe paths | Pass: 0 CRC errors, 0 unsafe members |
| Release markers | Pass: exactly `step196_part1.ok` through `step196_part4.ok` |
| Current release/preinstall contracts | Pass |

The package build regenerates the source hashes and writes the package checksum/integrity manifests alongside the four final ZIP parts.
