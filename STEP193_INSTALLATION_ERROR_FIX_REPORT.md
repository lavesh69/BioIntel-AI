# Step 193 Installation Error Fix

**Root cause:** `scripts/install_windows_step97.py` passed `--allow-degraded` to `scripts/step192_self_test.py`, but that parser did not define the option. Argparse exited with code 2, so the installer rebuilt `.venv` and failed again.

**Fixes:**

1. Added a Step 193 self-test with compatible arguments.
2. Added a dedicated Step 193 installation helper.
3. Added robust Python 3.11 x64 discovery.
4. Added optional Winget bootstrap when Python is absent.
5. Added deep source-hash and four-part marker checks before installation.
6. Added one-click repair and support-bundle launchers.
7. Added installer contract regression tests.
