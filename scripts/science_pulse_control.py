from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.science_pulse.scheduler import SciencePulseScheduler
from biointel.science_pulse.service import SciencePulseService
from biointel.step101.background import BackgroundJobService


def _payload(value):
    if hasattr(value, "__dict__"):
        return value.__dict__
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="Governed Science Pulse worker controls.")
    parser.add_argument(
        "command",
        choices=["start", "stop", "restart", "health", "force-sync", "diagnostics", "repair"],
    )
    parser.add_argument("--source", default="")
    args = parser.parse_args()
    service = BackgroundJobService(
        ROOT,
        python_executable=ROOT / ".venv" / "Scripts" / "python.exe",
    )
    if args.command == "start":
        result = _payload(service.start())
    elif args.command == "stop":
        result = _payload(service.stop())
    elif args.command == "restart":
        result = _payload(service.restart())
    elif args.command == "health":
        result = {
            "worker": _payload(service.status()),
            "science_pulse": SciencePulseScheduler(ROOT).diagnostics(),
        }
    elif args.command == "repair":
        result = SciencePulseScheduler(ROOT).repair()
    elif args.command == "force-sync":
        pulse = SciencePulseService(ROOT)
        keys = [args.source] if args.source else [
            str(item["source_key"]) for item in pulse.source_status() if item["enabled"]
        ]
        with pulse.store.connect() as connection:
            for key in keys:
                connection.execute(
                    """
                    UPDATE sp_sources SET next_sync_at='',circuit_open_until=''
                    WHERE tenant_id='local' AND source_key=?
                    """,
                    (key,),
                )
        result = {"queued_sources": keys, "network_called": False}
    else:
        scheduler = SciencePulseScheduler(ROOT)
        result = scheduler.diagnostics()
        report = scheduler.store.path.parent.parent / "runtime_logs" / "science-pulse-diagnostics.json"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")
        result = {"report": str(report), "health": result}
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
