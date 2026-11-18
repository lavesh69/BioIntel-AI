from __future__ import annotations

import argparse
import json
from pathlib import Path

from biointel.engine_platform_v196 import EngineManager


def main() -> int:
    parser = argparse.ArgumentParser(description="BioIntel V19.6 Engine Platform manager")
    parser.add_argument("--project-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--user-data", default="")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("health")
    sub.add_parser("probe-all")
    probe = sub.add_parser("probe")
    probe.add_argument("engine")
    plan = sub.add_parser("plan")
    plan.add_argument("engine")
    plan.add_argument("--offline-pack", default="")
    install = sub.add_parser("install-pack")
    install.add_argument("path")
    install.add_argument("--engine", action="append", default=[])
    install.add_argument("--accept-restricted-licences", action="store_true")
    qualify = sub.add_parser("qualify")
    qualify.add_argument("spec", type=Path)
    repair = sub.add_parser("repair")
    repair.add_argument("engine")
    uninstall = sub.add_parser("uninstall")
    uninstall.add_argument("engine")
    uninstall.add_argument("--remove-unused-pack", action="store_true")
    report = sub.add_parser("report")
    report.add_argument("output")

    args = parser.parse_args()
    manager = EngineManager(project=args.project_root, user_data=args.user_data or None)
    if args.command == "health":
        payload = manager.health_report()
    elif args.command == "probe-all":
        payload = {"rows": manager.probe_all().to_dict(orient="records")}
    elif args.command == "probe":
        payload = manager.probe(args.engine)
    elif args.command == "plan":
        payload = manager.plan(args.engine, offline_pack=args.offline_pack or None).to_dict()
    elif args.command == "install-pack":
        payload = manager.install_pack(args.path, engines=args.engine or None, accept_restricted_licences=args.accept_restricted_licences)
    elif args.command == "qualify":
        from biointel.engine_platform_v196 import qualify_engine
        spec = json.loads(args.spec.read_text(encoding="utf-8"))
        engine = str(spec.pop("engine"))
        payload = qualify_engine(engine, spec, store=manager.store, workspace_root=manager.home / "qualification").to_dict()
    elif args.command == "repair":
        payload = manager.repair(args.engine)
    elif args.command == "uninstall":
        payload = manager.uninstall(args.engine, remove_pack_when_unused=args.remove_unused_pack)
    elif args.command == "report":
        path = manager.export_report(args.output)
        payload = {"status": "written", "path": str(path)}
    else:
        raise RuntimeError(args.command)
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
