from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from biointel.engine_audit_v196 import audit_catalog
from biointel.native.engines import ENGINE_REGISTRY

from .catalog import release_manifest
from .paths import project_root


CONDA_PACKAGE_ALIASES: dict[str, str] = {
    "obabel": "openbabel",
    "openslide | openslide-python": "openslide",
    "bgzip": "htslib",
    "tabix": "htslib",
}

WINDOWS_PYTHON_ENGINE_PACKAGES: dict[str, tuple[str, ...]] = {
    "cutadapt": ("cutadapt",),
    "multiqc": ("multiqc",),
}


@dataclass(frozen=True)
class AcquisitionRecipe:
    engine: str
    label: str
    priority: str
    mode: str
    windows_mode: str
    install_route: str
    package_specs: tuple[str, ...]
    official_url: str
    licence_spdx: str
    redistribution_policy: str
    references: tuple[str, ...]
    model_weights_required: bool
    licence_acceptance_required: bool
    automatic_bundle_policy: str
    exact_release_qualified: bool
    blockers: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["package_specs"] = list(self.package_specs)
        payload["references"] = list(self.references)
        payload["blockers"] = list(self.blockers)
        return payload


def _parts(value: Any) -> tuple[str, ...]:
    text = str(value or "").strip()
    if not text:
        return ()
    return tuple(dict.fromkeys(part.strip() for part in re.split(r"\s*\|\s*", text) if part.strip()))


def _conda_specs(value: Any) -> tuple[str, ...]:
    output: list[str] = []
    for item in _parts(value):
        mapped = CONDA_PACKAGE_ALIASES.get(item, item)
        output.extend(part.strip() for part in mapped.split("|") if part.strip())
    return tuple(dict.fromkeys(output))


def _mode(row: dict[str, Any]) -> tuple[str, tuple[str, ...]]:
    engine = str(row.get("engine", ""))
    pip_packages = _parts(row.get("pip_packages"))
    conda_packages = _conda_specs(row.get("conda_packages"))
    route = str(row.get("install_route", ""))
    windows_mode = str(row.get("windows_mode", ""))
    if bool(row.get("licence_acceptance_required")) or bool(row.get("manual_distribution")):
        return "manual-authorized", ()
    if bool(row.get("model_weights_required")):
        return "model-pack", pip_packages or conda_packages
    if windows_mode == "Native Windows":
        windows_python = pip_packages or WINDOWS_PYTHON_ENGINE_PACKAGES.get(engine, ())
        if windows_python and ("python" in route or engine in WINDOWS_PYTHON_ENGINE_PACKAGES):
            return "windows-python", windows_python
        if route.startswith("official-") or route in {"provider-release", "openms-windows-pack"}:
            return "official-provider", ()
    if conda_packages:
        return "wsl2-micromamba", conda_packages
    if pip_packages:
        return ("windows-python" if windows_mode == "Native Windows" else "wsl2-python"), pip_packages
    if route.startswith("official-") or route in {"provider-release", "openms-windows-pack"}:
        return "official-provider", ()
    return "manual-review", ()


def acquisition_recipes(*, root: str | Path | None = None) -> tuple[AcquisitionRecipe, ...]:
    base = Path(root).resolve() if root else project_root()
    pins = release_manifest(base).get("engines", {})
    rows = audit_catalog(probe_runtime=False).to_dict(orient="records")
    recipes: list[AcquisitionRecipe] = []
    for row in rows:
        engine = str(row["engine"])
        mode, specs = _mode(row)
        pin = pins.get(engine, {})
        pinned_version = str(pin.get("version", "")).strip()
        if pinned_version and specs:
            specs = tuple(spec if any(ch in spec for ch in "=<>!") else f"{spec}={pinned_version}" for spec in specs)
        blockers = _parts(row.get("blockers"))
        exact = bool(
            pinned_version
            and str(pin.get("artifact_sha256", "")).strip()
            and str(pin.get("licence_sha256", "")).strip()
            and str(pin.get("qualification_status", "")) == "qualified"
        )
        recipes.append(
            AcquisitionRecipe(
                engine=engine,
                label=str(row["label"]),
                priority=str(row["priority_tier"]),
                mode=mode,
                windows_mode=str(row["windows_mode"]),
                install_route=str(row["install_route"]),
                package_specs=specs,
                official_url=str(row.get("official_url", "")),
                licence_spdx=str(row.get("licence_spdx", "")),
                redistribution_policy=str(row.get("redistribution_policy", "")),
                references=_parts(row.get("required_databases")),
                model_weights_required=bool(row.get("model_weights_required")),
                licence_acceptance_required=bool(row.get("licence_acceptance_required")),
                automatic_bundle_policy=str(row.get("automatic_bundle_policy", "")),
                exact_release_qualified=exact,
                blockers=blockers,
            )
        )
    if len(recipes) != len(ENGINE_REGISTRY) or len({item.engine for item in recipes}) != len(ENGINE_REGISTRY):
        raise RuntimeError("Acquisition recipes must cover every registered engine exactly once.")
    return tuple(sorted(recipes, key=lambda item: item.engine))


def acquisition_catalog(*, root: str | Path | None = None) -> pd.DataFrame:
    return pd.DataFrame([item.to_dict() for item in acquisition_recipes(root=root)])


def _qualification_template(recipe: AcquisitionRecipe) -> dict[str, Any]:
    registry = ENGINE_REGISTRY[recipe.engine]
    version_args = [str(value) for value in registry.version_args]
    return {
        "schema": "biointel.engine-target-qualification.v1",
        "engine": recipe.engine,
        "executable": "REPLACE_WITH_TARGET_EXECUTABLE_PATH",
        "executable_sha256": "REPLACE_WITH_TARGET_EXECUTABLE_SHA256",
        "version_args": version_args,
        "version_regex": r"(?i)(?:version\s*)?v?\d+(?:\.\d+)+(?:[-+._a-z0-9]*)?",
        "positive_command": ["{executable}", *version_args],
        "positive_expected_codes": [0],
        "negative_command": ["{executable}", "--biointel-invalid-option"],
        "negative_expected_codes": [1, 2, 64, 127, 255],
        "expected_outputs": [],
        "timeout_seconds": 60,
        "qualification_scope": "installation-and-version-smoke-only",
        "claim_boundary": "This generic template verifies executable integrity, version output and failure handling. Method-specific scientific fixtures remain required before scientific qualification.",
    }


def build_acquisition_bundle(destination: str | Path, *, root: str | Path | None = None) -> dict[str, Any]:
    base = Path(root).resolve() if root else project_root()
    output = Path(destination).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    recipes = acquisition_recipes(root=base)

    conda_specs = sorted({spec for item in recipes if item.mode == "wsl2-micromamba" for spec in item.package_specs})
    pip_specs = sorted({spec for item in recipes if item.mode == "windows-python" for spec in item.package_specs})
    manual = [item.to_dict() for item in recipes if item.mode in {"manual-authorized", "manual-review", "official-provider"}]
    assets = [
        {
            "engine": item.engine,
            "references": list(item.references),
            "model_weights_required": item.model_weights_required,
            "licence_acceptance_required": item.licence_acceptance_required,
        }
        for item in recipes
        if item.references or item.model_weights_required
    ]

    environment = [
        "name: biointel-engines-v196",
        "channels:",
        "  - conda-forge",
        "  - bioconda",
        "  - nodefaults",
        "dependencies:",
        "  - python=3.11",
        *[f"  - {spec}" for spec in conda_specs],
        "",
    ]
    # Compatibility environment for administrators who deliberately prefer one large
    # environment. The managed installer uses isolated per-engine environments so a
    # dependency conflict in one specialist tool cannot block every other engine.
    (output / "biointel-wsl2-environment.yml").write_text("\n".join(environment), encoding="utf-8")
    isolated_root = output / "wsl2-environments"
    isolated_root.mkdir(parents=True, exist_ok=True)
    isolated_rows: list[dict[str, Any]] = []
    for item in recipes:
        if item.mode != "wsl2-micromamba":
            continue
        environment_name = "biointel-v196-" + re.sub(r"[^a-z0-9-]+", "-", item.engine.lower()).strip("-")
        isolated = [
            f"name: {environment_name}",
            "channels:",
            "  - conda-forge",
            "  - bioconda",
            "  - nodefaults",
            "dependencies:",
            "  - python=3.11",
            *[f"  - {spec}" for spec in item.package_specs],
            "",
        ]
        relative = Path("wsl2-environments") / f"{item.engine}.yml"
        (output / relative).write_text("\n".join(isolated), encoding="utf-8")
        isolated_rows.append(
            {
                "engine": item.engine,
                "environment": environment_name,
                "environment_file": relative.as_posix(),
                "package_specs": list(item.package_specs),
                "priority": item.priority,
                "references": list(item.references),
                "claim_boundary": "Environment creation is installation only; target-machine and scientific qualification remain required.",
            }
        )
    (output / "WSL2_ENVIRONMENT_INDEX.json").write_text(
        json.dumps(
            {
                "schema": "biointel.wsl2-isolated-environments.v1",
                "environments": isolated_rows,
                "count": len(isolated_rows),
                "strategy": "one-engine-per-environment",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (output / "biointel-windows-python-engines.txt").write_text("\n".join(pip_specs) + ("\n" if pip_specs else ""), encoding="utf-8")
    (output / "MANUAL_OR_PROVIDER_ENGINES.json").write_text(json.dumps(manual, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output / "REFERENCE_AND_MODEL_ASSETS.json").write_text(json.dumps(assets, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    templates = output / "qualification-templates"
    templates.mkdir(parents=True, exist_ok=True)
    for item in recipes:
        (templates / f"{item.engine}.json").write_text(json.dumps(_qualification_template(item), indent=2, sort_keys=True) + "\n", encoding="utf-8")

    payload = {
        "schema": "biointel.engine-acquisition-bundle.v1",
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "registered_engines": len(recipes),
        "wsl2_micromamba_engines": sum(item.mode == "wsl2-micromamba" for item in recipes),
        "windows_python_engines": sum(item.mode == "windows-python" for item in recipes),
        "manual_or_provider_engines": len(manual),
        "asset_dependent_engines": len(assets),
        "exact_release_qualified": sum(item.exact_release_qualified for item in recipes),
        "recipes": [item.to_dict() for item in recipes],
        "claim_boundary": "This bundle prepares deterministic acquisition routes. It does not claim that external binaries, databases or model weights ran on a Windows/WSL2/GPU target until target-machine evidence passes.",
    }
    manifest_path = output / "BIOINTEL_ENGINE_ACQUISITION.json"
    manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    files = []
    for path in sorted(output.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS.txt":
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            files.append({"path": path.relative_to(output).as_posix(), "size_bytes": path.stat().st_size, "sha256": digest})
    (output / "SHA256SUMS.txt").write_text("".join(f"{item['sha256']}  {item['path']}\n" for item in files), encoding="utf-8")
    return {**payload, "output": str(output), "files": len(files)}
