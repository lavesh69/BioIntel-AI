# Reconstruct BioIntel Education Full Upgrade R15

1. Put all four R15 ZIP parts and the SHA256SUMS file in one empty directory.
2. Verify every archive hash.
3. Extract Part1 through Part4 into the same destination; every part uses the shared `BioIntel-Step220` root.
4. Run `python scripts/validate_education_full_upgrade_r15.py --root BioIntel-Step220`.
5. Run `INSTALL_WINDOWS.bat`, then `RUN_BOTH_WINDOWS.bat`.
6. Keep UserData outside the release tree and back it up before migration.

The release package intentionally excludes runtime caches, test caches, and UserData.
