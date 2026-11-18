from __future__ import annotations

import argparse
import os
import subprocess
import sys

from biointel.native.engines import ENGINE_REGISTRY


def _safe(value: str) -> str:
    text = str(value)
    if not text or any(character in text for character in ("\x00", "\r", "\n")):
        raise ValueError("Unsafe or empty WSL proxy argument.")
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description="Bounded BioIntel WSL2 scientific-engine proxy.")
    parser.add_argument("--distribution", required=True)
    parser.add_argument("--environment", default="biointel-engines-v196")
    parser.add_argument("--engine", required=True)
    parser.add_argument("args", nargs=argparse.REMAINDER)
    ns = parser.parse_args()
    engine = ns.engine.lower().strip()
    if engine not in ENGINE_REGISTRY:
        raise SystemExit(f"Unknown BioIntel engine: {engine}")
    executable = ENGINE_REGISTRY[engine].executables[0]
    args = list(ns.args)
    if args and args[0] == "--":
        args = args[1:]
    values = [_safe(item) for item in args]
    shell = 'exec "$HOME/.local/bin/micromamba" run -n "$1" "$2" "${@:3}"'
    command = [
        "wsl.exe",
        "-d",
        _safe(ns.distribution),
        "--",
        "bash",
        "-lc",
        shell,
        "biointel-engine-proxy",
        _safe(ns.environment),
        _safe(executable),
        *values,
    ]
    completed = subprocess.run(command, env={**os.environ, "PYTHONUTF8": "1"}, check=False)
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
