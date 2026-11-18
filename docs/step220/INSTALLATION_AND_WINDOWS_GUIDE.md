# Installation and Windows Guide

Extract all four matching Step220 ZIP parts into one new directory. Do not run from an individual ZIP and do not mix parts from another release. Use `INSTALL_WINDOWS.bat`, then `RUN_BOTH_WINDOWS.bat`. The managed runtime remains under LocalAppData and user data remains outside the application release folder.

For source verification, use the managed Python 3.11 environment, set `PYTHONPATH=src`, and compile/import before launch. Windows paths with spaces and Unicode names are supported. Keep the extraction path reasonably short because the historical tree contains deeply nested assets.

The installer and launcher require compatible 64-bit CPython 3.11.x. For unattended verification, use `INSTALL_WINDOWS.bat /no-pause` and `RUN_BOTH_WINDOWS.bat /managed /no-browser /no-pause`. `BIOINTEL_APP_HOME` and `BIOINTEL_USER_DATA_DIR` may be set before launch to use custom, space-safe managed and data paths.
