"""Current Step 196 runtime-preflight entry point.

The underlying preflight remains compatibility-safe for prior local workspaces,
but all active Step 196 launchers now enter through this current-name shim.
"""

from __future__ import annotations

from step97_runtime_preflight import main


if __name__ == "__main__":
    raise SystemExit(main())
