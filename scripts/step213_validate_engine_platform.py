from __future__ import annotations

import argparse
import hashlib
import json
import os
import py_compile
import tempfile
from pathlib import Path

from biointel.engine_platform_v196 import EngineManager, adapter_catalog, engine_platform_catalog, pack_catalog, production_service_catalog


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    root = args.root.resolve()
    checks: list[dict[str, object]] = []

    def check(name: str, passed: bool, detail: object) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    engines = engine_platform_catalog(root=root)
    adapters = adapter_catalog()
    packs = pack_catalog()
    services = production_service_catalog()
    check("engine_catalog_76", len(engines) == 76 and engines["engine"].nunique() == 76, len(engines))
    check("adapters_12", len(adapters) == 12, len(adapters))
    check("pack_groups_5", len(packs) == 5 and int(packs["engine_count"].sum()) == 76, packs.to_dict(orient="records"))
    check("production_services_6", len(services) == 6, len(services))
    check("fail_closed_manifest", not engines["install_manifest_complete"].any(), int(engines["install_manifest_complete"].sum()))

    with tempfile.TemporaryDirectory(prefix="biointel-step213-") as temporary:
        manager = EngineManager(project=root, user_data=Path(temporary))
        health = manager.health_report()
        check("state_db_integrity", health["database"]["status"] == "passed", health["database"])
        check("health_counts", health["registered_engines"] == 76 and health["advanced_adapters"] == 12 and health["production_services"] == 6, health)
        check("restricted_fail_closed", manager.plan("netmhcpan").state.value == "requires-user-authorization", manager.plan("netmhcpan").to_dict())
        check("model_fail_closed", manager.plan("rfdiffusion").state.value == "requires-model-pack", manager.plan("rfdiffusion").to_dict())

    compiled = 0
    errors: list[str] = []
    for path in sorted((root / "src" / "biointel" / "engine_platform_v196").glob("*.py")):
        try:
            py_compile.compile(str(path), doraise=True)
            compiled += 1
        except py_compile.PyCompileError as exc:
            errors.append(str(exc))
    for path in (root / "pages" / "268_Engine_Control_Center.py", root / "scripts" / "step213_engine_platform.py", root / "scripts" / "step213_engine_platform_bootstrap.py"):
        try:
            py_compile.compile(str(path), doraise=True)
            compiled += 1
        except py_compile.PyCompileError as exc:
            errors.append(str(exc))
    check("compile", not errors, {"compiled": compiled, "errors": errors})

    protected = json.loads((root / "PROTECTED_MODULE_HASHES_STEP205.json").read_text(encoding="utf-8"))
    bad = [item["path"] for item in protected["entries"] if sha(root / item["path"]) != item["sha256"]]
    check("protected_hashes", not bad, {"checked": len(protected["entries"]), "bad": bad})

    passed = all(bool(item["passed"]) for item in checks)
    report = {
        "schema": "biointel.step213.engine-platform-validation.v1",
        "passed": passed,
        "checks": checks,
        "claim_boundary": "Linux validation cannot replace native Windows/WSL2 engine execution evidence.",
    }
    output = args.output or root / "reports" / "step213_engine_platform_validation.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
