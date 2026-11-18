from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.target_modules_v176 import TARGET_MODULES, TARGET_PROFILES, required_engines, required_references


def canonical(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def main() -> int:
    target = ROOT / "data" / "step176" / "target_modules"
    target.mkdir(parents=True, exist_ok=True)
    index: list[dict[str, object]] = []
    for key in TARGET_MODULES:
        profile = TARGET_PROFILES[key]
        folder = target / key
        folder.mkdir(parents=True, exist_ok=True)
        engines = required_engines(key).to_dict(orient="records")
        references = required_references(key).to_dict(orient="records")
        contract = {
            "schema": "biointel.step176.module-contract.v1",
            "module_key": key,
            "module_title": profile.title,
            "evidence_class": profile.evidence_class,
            "workflow": list(profile.workflow),
            "quality_gates": list(profile.quality_gates),
            "required_outputs": list(profile.required_outputs),
            "required_engines": [row["engine"] for row in engines],
            "required_references": [row["reference_id"] for row in references],
            "scientific_boundary": profile.boundary,
            "release_policy": "fail-closed",
        }
        contract_text = json.dumps(contract, indent=2, ensure_ascii=False)
        contract_path = folder / "qualification_contract.json"
        contract_path.write_text(contract_text, encoding="utf-8")
        fixture = {
            "schema": "biointel.step176.golden-fixture-template.v1",
            "module_key": key,
            "fixture_status": "template-not-engine-qualified",
            "positive_control_required": True,
            "negative_control_required": True,
            "expected_outputs": list(profile.required_outputs),
            "operator_note": "Replace this template with real engine-produced, checksum-locked golden and negative-control fixtures.",
        }
        fixture_path = folder / "golden_fixture_template.json"
        fixture_path.write_text(json.dumps(fixture, indent=2, ensure_ascii=False), encoding="utf-8")
        readme = (
            f"# {profile.title}\n\n"
            "This workspace is fail-closed. Populate real engine results and reference qualification manifests; "
            "do not mark external evidence complete without source records.\n\n"
            f"Required engines: {', '.join(contract['required_engines'])}\n\n"
            f"Required references: {', '.join(contract['required_references'])}\n"
        )
        (folder / "README.md").write_text(readme, encoding="utf-8")
        index.append({
            "module_key": key,
            "module_title": profile.title,
            "contract": str(contract_path.relative_to(ROOT)).replace("\\", "/"),
            "contract_sha256": sha256(contract_text.encode("utf-8")).hexdigest(),
            "golden_fixture_template": str(fixture_path.relative_to(ROOT)).replace("\\", "/"),
        })
    payload = {"schema": "biointel.step176.asset-index.v1", "module_count": len(index), "modules": index}
    (ROOT / "data" / "step176" / "asset_index.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"module_count": len(index), "target": str(target)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
