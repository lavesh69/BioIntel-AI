# Reconstruct BioIntel AI Education Phase 7 Desktop

1. Place all four `BioIntel-AI-15.6.0-EDUCATION-PHASE7-PartN.zip` files in one empty folder.
2. Run `EXTRACT_INSTALL_RUN_EDUCATION_4PART_WINDOWS.bat`, or extract all four archives into the same destination.
3. The shared archive root is `BioIntel-Step220`.
4. Confirm `.release_parts/education_phase7_part1.ok` through `education_phase7_part4.ok` are present.
5. Run `VERIFY_EDUCATION_PHASE7_WINDOWS.bat` from the reconstructed source root.
6. Compare the four archive hashes against `SHA256SUMS_PHASE7.txt` when the external delivery bundle is available.

Each ZIP contains a disjoint subset of the source tree plus its own part manifest. All four parts are required.
