from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from biointel.synthetic.core import CLEAN_SCENARIOS, FAILURE_SCENARIOS, MODULE_SPECS, SyntheticGenerationConfig
from biointel.synthetic.exports import build_synthetic_dataset_package
from biointel.synthetic.generators import SyntheticDatasetGenerator


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def build_fixtures(project_root: Path, *, seed: int = 219042) -> dict[str, object]:
    output_root = project_root / "data" / "synthetic_demo_fixtures"
    output_root.mkdir(parents=True, exist_ok=True)
    generator = SyntheticDatasetGenerator()
    records: list[dict[str, object]] = []

    for module_index, (module_id, spec) in enumerate(MODULE_SPECS.items()):
        module_root = output_root / module_id
        module_root.mkdir(parents=True, exist_ok=True)
        scenarios = list(spec["scenarios"])
        variants = (
            ("baseline", CLEAN_SCENARIOS[module_id], "Clean Dataset"),
            ("failure", FAILURE_SCENARIOS[module_id], "Pipeline-Failure Dataset"),
        )
        for variant_index, (variant, scenario, preset) in enumerate(variants):
            config = SyntheticGenerationConfig.from_preset(
                module_id=module_id,
                scenario=scenario,
                size_preset="small",
                preset_name=preset,
                seed=seed + module_index * 10 + variant_index,
                sample_count=12,
                feature_count=24,
            )
            dataset = generator.generate(config)
            content = build_synthetic_dataset_package(dataset)
            path = module_root / f"{variant}.zip"
            path.write_bytes(content)
            records.append({
                "module_id": module_id,
                "module_title": spec["title"],
                "variant": variant,
                "scenario": scenario,
                "seed": config.seed,
                "relative_path": path.relative_to(project_root).as_posix(),
                "size_bytes": len(content),
                "sha256": _sha256(content),
                "data_origin": "synthetic",
                "is_synthetic": True,
            })

    catalog = {
        "release": "Step219.0",
        "data_origin": "synthetic",
        "is_synthetic": True,
        "generator_id": generator.generator_id,
        "generator_version": generator.generator_version,
        "module_count": len(MODULE_SPECS),
        "fixture_count": len(records),
        "variants_per_module": ["baseline", "failure"],
        "records": records,
    }
    catalog_path = output_root / "catalog.json"
    catalog_path.write_text(json.dumps(catalog, indent=2, sort_keys=True), encoding="utf-8")
    return catalog


def main() -> int:
    parser = argparse.ArgumentParser(description="Build bundled BioIntel synthetic demo fixtures.")
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--seed", type=int, default=219042)
    args = parser.parse_args()
    catalog = build_fixtures(args.project_root.resolve(), seed=args.seed)
    print(json.dumps({
        "module_count": catalog["module_count"],
        "fixture_count": catalog["fixture_count"],
        "status": "ok",
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())