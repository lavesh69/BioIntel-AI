# BioIntel AI Step 196 V7 — Historical Test Report

> Superseded by the current Step 196 V8 four-part release. Retained for release provenance only.

## Source-level checks completed before packaging

| Check | Result |
| --- | --- |
| Uploaded four-part source archive CRC test | Pass for every uploaded part; 25,197 archive entries, no duplicate member paths and no unsafe paths |
| Canonical source extraction | Pass; 25,197 files extracted |
| Python syntax audit | Pass; 1,556 Python files parsed, 0 syntax failures |
| Navigation catalogue | Pass; 262 page files, 263 catalogue entries including Home, 0 missing pages, 0 auto-discovered pages, 0 missing category metadata |
| Installer preinstall contract | Pass; standard-library-only check confirmed four markers, current version and dependency order |
| Offline dependency lock | Pass; 32 locked packages, lock hash valid |
| Windows wheelhouse manifest | Pass; 102 wheels, hashes and ZIP structure valid |
| Installer lock recovery | Pass; active cross-process lock blocked, stale/unlocked content was replaceable, replacement token was preserved on release |
| Runtime control corruption guard | Pass; non-numeric PIDs are treated safely and another release is refused rather than stopped |
| Protected module preservation | Pass; all five excluded module source hashes match the uploaded canonical ZIP members |

## Environment limitation recorded honestly

This packaging environment uses Python 3.12.13 and does not have Streamlit or `httpx` installed. The bundled wheelhouse is Windows CPython 3.11-only, so a real Windows `.venv`, Streamlit startup and AppTest run were not executed here. The release scripts now reject this host runtime with a friendly CPython 3.11.9 x64 requirement.

## Final package checks

| Check | Result |
| --- | --- |
| Regenerated Step 196 source manifest | Pass; 25,115 source entries deep-hashed with 0 failures |
| Flat SHA-256 manifest | Pass; all listed source files matched |
| Four-part package membership | Pass; 25,117 package source entries, 0 missing, 0 extra and 0 duplicate entries |
| Part markers | Pass; exactly `step196_part1.ok` through `step196_part4.ok` |
| ZIP CRC | Pass with both Python ZIP validation and `unzip -t` validation for all four parts |
| Part SHA-256 | Pass against the generated package checksum record |
| Unsafe ZIP paths | Pass; 0 absolute or traversal paths |
| Clean extraction | Pass; extracted all four parts together into a fresh directory whose path contains spaces |
| Extracted manifest validation | Pass; 25,115 entries deep-hashed with 0 failures |
| Extracted preinstall contract | Pass; four markers, version consistency and dependency order validated |

Only the four ZIP parts are delivered. Source manifests, the release audit, changelog and this test report are included inside the release.
