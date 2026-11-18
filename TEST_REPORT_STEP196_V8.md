# BioIntel AI Step 196 V8 — Test Report

> Superseded by the current Step 196 V9 test report. Retained for release provenance only.

## Source and behaviour checks completed before package build

| Check | Result |
| --- | --- |
| Python syntax compile audit for `src/biointel` and `pages` | Pass |
| Shared Step 188/189/190 lifecycle UI contract | Pass: operational canvas present and raw `st.json` absent |
| Direct UI raw-JSON scan | Pass: no direct `st.json` calls remain in user-facing pages or UI renderers |
| Upload-surface audit | Pass: 54 page files / 108 upload controls are covered by shared preflight or explicit bounded staging |
| 1 GB staged upload smoke test | Pass: large profile requires staging; atomic streamed file and SHA-256 were verified |
| Operational-canvas smoke test | Pass: path compaction, nested-payload handling and sensitive-value redaction verified |
| Clinical staged-artifact registry smoke test | Pass: streamed file path hashes work for analysis, evidence and training; dual byte/path input is rejected |
| Protected-module preservation | Pass: all five excluded pages match canonical uploaded ZIP hashes byte-for-byte |

## Environment limitation recorded honestly

This build environment has Python 3.12 and does not include Streamlit or pytest. Therefore a Windows CPython 3.11.9 virtual-environment launch and Streamlit AppTest were not run here. The packaged Windows installer continues to require CPython 3.11.9 x64 and performs its own preflight before environment changes.

## Final package checks

| Check | Result |
| --- | --- |
| Release source manifest deep-hash validation | Pass: 25,120 source entries checked, 0 mismatches before final rebuild |
| Package source membership | Pass: 25,122 packaged source files, 0 missing, 0 extra and 0 duplicate members |
| Package markers | Pass: exactly `step196_part1.ok` through `step196_part4.ok` |
| ZIP CRC | Pass: Python package validation and `unzip -t` passed for all four parts |
| Unsafe ZIP paths | Pass: 0 absolute or traversal members |
| SHA-256 part checksums | Pass: generated alongside the four ZIP files in the delivery verification output |
| Clean extraction and extracted-manifest validation | Pass: all four parts extracted together into a fresh path containing spaces; 25,120 source entries deep-hashed with 0 mismatches and the extracted preinstall contract passed |
