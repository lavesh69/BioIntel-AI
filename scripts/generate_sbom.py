from __future__ import annotations

import argparse
import importlib.metadata
import json
from datetime import UTC, datetime
from pathlib import Path


def build_sbom() -> dict[str, object]:
    components = []
    for distribution in sorted(
        importlib.metadata.distributions(), key=lambda item: item.metadata.get("Name", "").lower()
    ):
        name = distribution.metadata.get("Name")
        if not name:
            continue
        components.append(
            {
                "type": "library",
                "name": name,
                "version": distribution.version,
                "purl": f"pkg:pypi/{name.lower().replace('_', '-')}@{distribution.version}",
            }
        )
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:biointel-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}",
        "version": 1,
        "metadata": {
            "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
            "component": {"type": "application", "name": "BioIntel AI"},
        },
        "components": components,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a dependency CycloneDX-style SBOM")
    parser.add_argument("--output", default="reports/sbom.cdx.json")
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(build_sbom(), indent=2, sort_keys=True), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
