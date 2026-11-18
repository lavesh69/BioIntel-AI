# Reconstruct BioIntel AI Education Phase 11

Place these four files in one empty Windows folder without renaming them:

- `BioIntel-AI-15.6.0-EDUCATION-PHASE11-Part1.zip`
- `BioIntel-AI-15.6.0-EDUCATION-PHASE11-Part2.zip`
- `BioIntel-AI-15.6.0-EDUCATION-PHASE11-Part3.zip`
- `BioIntel-AI-15.6.0-EDUCATION-PHASE11-Part4.zip`

Run `EXTRACT_INSTALL_RUN_EDUCATION_PHASE11_4PART_WINDOWS.bat`. The archives contain non-overlapping paths under `BioIntel-Step220/`. All four Phase 11 markers are checked before the existing deep-verified Windows installer starts.

For extraction only:

```bat
EXTRACT_INSTALL_RUN_EDUCATION_PHASE11_4PART_WINDOWS.bat /extract-only
```

After reconstruction, run `VERIFY_EDUCATION_PHASE11_WINDOWS.bat` to execute Phase 11 controls and the Step220 deep SHA-256 source gate.
