from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.runtime_v170 import Step170Registry, download_direct, reference_catalog


def main() -> int:
    parser = argparse.ArgumentParser(description="Step 170 production reference manager")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--reference", action="append", default=[])
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--max-size-gb", type=float, default=2.0)
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--accept-licence", action="append", default=[])
    parser.add_argument("--accepted-by", default="")
    parser.add_argument("--register-path", default="")
    parser.add_argument("--release-id", default="")
    parser.add_argument("--provider-checksum", default="")
    parser.add_argument("--reviewer", default="")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    catalog = reference_catalog()
    if args.list:
        print(catalog.to_csv(index=False))
        return 0
    registry = Step170Registry(root)
    accepted = []
    for licence_id in args.accept_licence:
        accepted.append(registry.accept_licence(licence_id, accepted_by=args.accepted_by))
    if args.register_path:
        if len(args.reference) != 1:
            raise SystemExit("--register-path requires exactly one --reference")
        result = registry.register_reference(args.reference[0], args.register_path, release_id=args.release_id, provider_checksum=args.provider_checksum, scientific_reviewer=args.reviewer)
        print(json.dumps(result, indent=2))
        return 0 if result["qualified"] else 2
    selected = args.reference or list(catalog["reference_id"])
    results = []
    for reference_id in selected:
        try:
            result = download_direct(root, reference_id, execute=args.execute, max_size_gb=args.max_size_gb)
        except (KeyError, OSError, ValueError) as exc:
            # A remote reference source must never abort the whole Windows
            # installer.  Keep every other eligible acquisition attempt and
            # make the unavailable state explicit in the report.
            result = {
                "reference_id": reference_id,
                "status": "optional-service-unavailable",
                "message": f"{type(exc).__name__}: {str(exc)[:400]}",
            }
        if result.get("status") in {"downloaded-unqualified", "already-downloaded-unqualified"}:
            target = str(result.get("target") or "").strip()
            if target:
                try:
                    result["registration"] = registry.register_reference(
                        reference_id,
                        target,
                        # Downloaded public references remain deliberately
                        # unqualified until a pinned release, licence record
                        # and named scientific review are attached.
                        release_id="",
                        provider_checksum=str(result.get("provider_checksum") or ""),
                        scientific_reviewer="",
                    )
                except (KeyError, OSError, ValueError) as exc:
                    result["registration"] = {
                        "qualified": False,
                        "message": f"{type(exc).__name__}: {str(exc)[:400]}",
                    }
        results.append(result)
    payload = {
        "schema": "biointel.step170.reference-manager.v1",
        "execute": args.execute,
        "max_size_gb": args.max_size_gb,
        "selected": len(selected),
        "downloaded": sum(row.get("status") == "downloaded-unqualified" for row in results),
        "already_downloaded": sum(row.get("status") == "already-downloaded-unqualified" for row in results),
        "dry_run": sum(row["status"] == "dry-run" for row in results),
        "manual_or_tool_managed": sum(row["status"] == "manual-or-tool-managed" for row in results),
        "blocked_by_size": sum(row["status"] == "blocked-by-size-policy" for row in results),
        "optional_service_unavailable": sum(row.get("status") == "optional-service-unavailable" for row in results),
        "accepted_licences": accepted,
        "results": results,
        "download_does_not_equal_qualification": True,
    }
    reports = root / "reports"
    reports.mkdir(exist_ok=True)
    (reports / "step170_reference_manager.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
