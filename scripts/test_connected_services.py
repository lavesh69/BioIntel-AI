from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.connected.diagnostics import test_openai_connection  # noqa: E402
from biointel.connected.providers import PROVIDERS, ConnectedProviderService  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Test BioIntel Step 52 live connections.")
    parser.add_argument(
        "--openai", action="store_true", help="Test OpenAI authentication/model visibility."
    )
    parser.add_argument(
        "--providers", nargs="*", choices=sorted(PROVIDERS), help="Provider keys to test."
    )
    parser.add_argument("--all", action="store_true", help="Test OpenAI and all providers.")
    parser.add_argument("--json", dest="json_path", default="reports/step52_connection_test.json")
    args = parser.parse_args()

    test_openai = args.all or args.openai
    selected = list(PROVIDERS) if args.all else (args.providers or [])
    report: dict[str, object] = {
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "openai": None,
        "providers": [],
    }
    if test_openai:
        report["openai"] = test_openai_connection(ROOT)
    if selected:
        report["providers"] = ConnectedProviderService(ROOT, persist_queries=False).probe_all(
            selected
        )

    target = ROOT / args.json_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8")

    print("BioIntel AI Step 52 connection test")
    if report["openai"]:
        row = report["openai"]
        print(
            f"OpenAI: {row.get('status')} | model={row.get('model')} | visible={row.get('model_visible')} | error={row.get('error', '')}"
        )
    for row in report["providers"]:
        print(
            f"{row['provider']}: {row['status']} | records={row['records']} | cache={row['cache_status']} | error={row['error']}"
        )
    print(f"Report: {target}")

    openai_ok = not test_openai or bool(report["openai"] and report["openai"].get("available"))
    provider_ok = all(bool(row.get("available")) for row in report["providers"])
    return 0 if openai_ok and provider_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
