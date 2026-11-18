# Step205 Release Test Report

## Final status

Release source and four-part package validation passed in the Linux build environment.
Native execution of Windows batch files was not possible in this environment and is not claimed.

## Completed checks

- New and focused Neuro/CNS regression suite: **102 passed**.
- Python compilation for `src/biointel/neuro_cns`: **passed**.
- Deep Step205 source-manifest verification: **23,911 tracked files, 0 bad hashes**.
- Four-part package integrity: **25,300 packaged source files**.
- Cross-part completeness: **0 missing, 0 extra, 0 duplicate files**.
- ZIP CRC validation: **passed for all four parts**.
- Unsafe archive paths: **none found**.
- Active Step205 physical markers: **4/4 present**.
- Windows installer/run static contract: **passed**.
- Exact CPython 3.11.9 x64 policy: **verified in installer, locator, venv and launch scripts**.
- Windows paths containing spaces: **quoted-path contract passed**.
- Installer-integrated integrity gate: **verified**.
- Desktop shortcut stale-version cleanup: **verified as scoped to BioIntel launcher shortcuts**.
- Optional Ollama/SearXNG/provider services: **isolated from core install and launch**.
- Offline wheelhouse: **102 wheels; required baseline packages present**.
- Protected excluded modules: retained under the Step205 protected-module hash policy.

## Scientific test note

One test produced a non-fatal scikit-learn `FastICA` convergence warning on synthetic EEG data. The workflow completed and all assertions passed. The UI reports ICA as a review aid rather than a validated clinical detector.

## Environment boundary

- Build/test interpreter: CPython 3.13.5 x64 using a builder override.
- Required end-user runtime: **CPython 3.11.9 x64 exactly**.
- Native Windows execution still requires confirmation on a real Windows machine after clean extraction.
- Implemented software capability and internal automated tests do not constitute clinical, regulatory, wet-lab, prospective, or external scientific validation.
