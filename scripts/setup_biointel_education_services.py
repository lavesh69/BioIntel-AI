"""Configure and verify optional BioIntel Education service endpoints."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.education.education_suite import EducationSuiteService

CATALOG = (
    ("live_class", "BioIntel Live Classroom"),
    ("virtual_classroom", "BioIntel Virtual Classroom Pro"),
    ("whiteboard", "BioIntel Collaborative Board Service"),
    ("collaborative_notes", "BioIntel Real-Time Notes Service"),
    ("multi_user_lab", "BioIntel Multi-User Scientific Lab"),
    ("assessment_worker", "BioIntel Assessment Worker"),
    ("code_sandbox", "BioIntel Code Sandbox"),
    ("learning_record_store", "BioIntel Learning Record Store"),
    ("education_search", "BioIntel Education Search Service"),
    ("lms_bridge", "BioIntel LMS Bridge"),
    ("offline_library_sync", "BioIntel Offline Library Sync"),
)


def print_status(service: EducationSuiteService, institution: str) -> int:
    configured = {item["connector_type"]: item for item in service.list_connectors(institution)}
    failures = 0
    for key, name in CATALOG:
        item = configured.get(key)
        if not item:
            print(f"[OPTIONAL] {name}: not configured")
            continue
        health = service.connector_health(item["endpoint"])
        marker = "READY" if health["ok"] else "UNAVAILABLE"
        failures += int(bool(item["enabled"]) and not health["ok"])
        print(f"[{marker}] {name}: {health['status']} - {health['detail']}")
    return failures


def interactive(service: EducationSuiteService, institution: str, actor: str) -> int:
    print("\nBioIntel Education Services Setup")
    print("Local classroom features work without any optional service.")
    print("Leave an endpoint blank to keep that service disabled.\n")
    current = {item["connector_type"]: item for item in service.list_connectors(institution)}
    for key, name in CATALOG:
        previous = current.get(key, {}).get("endpoint", "")
        value = input(f"{name} endpoint [{previous}]: ").strip() or previous
        enabled = bool(value)
        service.configure_connector(institution, key, name, value, actor, enabled)
    print("\nSaved. Checking configured endpoints...")
    return print_status(service, institution)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--institution", default="local-institution")
    parser.add_argument("--actor", default="local-operator")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--export-template", type=Path)
    args = parser.parse_args()
    service = EducationSuiteService()
    if args.export_template:
        payload = {key: {"display_name": name, "endpoint": "", "enabled": False} for key, name in CATALOG}
        args.export_template.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"Template written: {args.export_template}")
        return 0
    if args.verify:
        return 1 if print_status(service, args.institution) else 0
    return 1 if interactive(service, args.institution, args.actor) else 0


if __name__ == "__main__":
    raise SystemExit(main())
