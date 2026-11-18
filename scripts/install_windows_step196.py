"""Historical compatibility delegate.

Step196 used ``launch_scientific_runtime_setup`` with
``setup_scientific_runtime_windows.py --attempt-wsl-bootstrap``. Step206 keeps
that optional workflow available separately but deliberately does not start it
during the core Windows installation.
"""
from __future__ import annotations

try:
    from .install_windows_step206 import main
except ImportError:
    from install_windows_step206 import main


if __name__ == "__main__":
    raise SystemExit(main())
