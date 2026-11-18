from __future__ import annotations

import argparse
import json
from pathlib import Path

from .core import CONTROL_PRESETS, MODULE_SPECS, SIZE_PRESETS, SyntheticGenerationConfig
from .exports import write_synthetic_package_directory
from .generators import generate_synthetic_dataset


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m biointel.synthetic", description="Generate safe, labelled BioIntel synthetic demo datasets.")
    commands = parser.add_subparsers(dest="command", required=True)
    generate = commands.add_parser("generate", help="Generate a synthetic dataset package directory.")
    generate.add_argument("--module", required=True, choices=sorted(MODULE_SPECS))
    generate.add_argument("--scenario", default=None)
    generate.add_argument("--size", default="small", choices=sorted(SIZE_PRESETS))
    generate.add_argument("--preset", default="Typical Research Dataset", choices=tuple(CONTROL_PRESETS))
    generate.add_argument("--samples", type=int, default=None)
    generate.add_argument("--features", type=int, default=None)
    generate.add_argument("--groups", type=int, default=2)
    generate.add_argument("--effect-size", type=float, default=None)
    generate.add_argument("--noise", type=float, default=None)
    generate.add_argument("--missingness", type=float, default=None)
    generate.add_argument("--batch-effect", type=float, default=None)
    generate.add_argument("--seed", type=int, default=42)
    generate.add_argument("--output", type=Path, required=True)
    generate.add_argument("--cancel-file", type=Path, default=None, help="Cancel safely when this sentinel file exists.")
    commands.add_parser("catalog", help="Print the module and scenario catalog as JSON.")
    return parser


def _config(arguments: argparse.Namespace) -> SyntheticGenerationConfig:
    scenario = arguments.scenario or MODULE_SPECS[arguments.module]["scenarios"][0]
    overrides = {"sample_count": arguments.samples, "feature_count": arguments.features, "group_count": arguments.groups}
    optional = {
        "effect_size": arguments.effect_size,
        "noise_level": arguments.noise,
        "missing_data_rate": arguments.missingness,
        "batch_effect_strength": arguments.batch_effect,
    }
    overrides.update({key: value for key, value in optional.items() if value is not None})
    return SyntheticGenerationConfig.from_preset(arguments.module, scenario, arguments.size, arguments.preset, seed=arguments.seed, **overrides)


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    if arguments.command == "catalog":
        print(json.dumps({module: spec for module, spec in MODULE_SPECS.items()}, indent=2))
        return 0
    config = _config(arguments)
    cancel_check = (lambda: bool(arguments.cancel_file and arguments.cancel_file.exists()))
    dataset = generate_synthetic_dataset(config, cancel_check=cancel_check)
    destination = arguments.output / f"{config.module_id}-{config.scenario}-seed-{config.seed}"
    write_synthetic_package_directory(dataset, destination, cancel_check=cancel_check)
    result = {
        "status": "generated",
        "output": str(destination.resolve()),
        "module": config.module_id,
        "scenario": config.scenario,
        "seed": config.seed,
        "data_origin": "synthetic",
        "is_synthetic": True,
        "table_count": len(dataset.tables),
    }
    print(json.dumps(result, indent=2))
    return 0


__all__ = ["build_parser", "main"]
