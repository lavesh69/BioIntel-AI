from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def control(control_id: str, name: str, passed: bool, evidence: Any) -> dict[str, Any]:
    return {
        "control_id": control_id,
        "name": name,
        "passed": bool(passed),
        "evidence": evidence,
    }


def main() -> int:
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    brand_manifest_path = ROOT / "assets/brand/brand-manifest.json"
    manifest = json.loads(brand_manifest_path.read_text(encoding="utf-8"))
    page_sources = {
        path.name: path.read_text(encoding="utf-8") for path in (ROOT / "pages").glob("*.py")
    }
    branded_pages = [
        name
        for name, source in page_sources.items()
        if "· BioIntel AI" in source or "branded_page_title(" in source
    ]

    asset_specs = {
        "master_icon": (ROOT / "store/assets/master/icon-1024.png", (1024, 1024)),
        "desktop_icon": (ROOT / "platform/desktop/assets/icon.png", (1024, 1024)),
        "mobile_icon": (ROOT / "platform/mobile/assets/icon-only.png", (1024, 1024)),
        "portrait_splash": (ROOT / "store/assets/master/splash-portrait.png", (1536, 2048)),
        "landscape_splash": (ROOT / "store/assets/master/splash-landscape.png", (2048, 1536)),
    }
    asset_results: dict[str, Any] = {}
    for key, (path, expected_size) in asset_specs.items():
        with Image.open(path) as image:
            actual_size = image.size
        asset_results[key] = {
            "path": path.relative_to(ROOT).as_posix(),
            "size": list(actual_size),
            "expected_size": list(expected_size),
            "sha256": sha256(path),
            "valid": actual_size == expected_size,
        }

    dti_source = page_sources["6_DTI_Predictor.py"]
    theme_source = (ROOT / "src/biointel/ui/theme.py").read_text(encoding="utf-8")
    css_source = (ROOT / "src/biointel/ui/desktop_ux.css").read_text(encoding="utf-8")
    store_manifest = json.loads((ROOT / "store/release-manifest.json").read_text(encoding="utf-8"))

    controls = [
        control("BR-01", "Master identity", manifest.get("brand") == "BioIntel AI", manifest),
        control(
            "BR-02",
            "Descriptor and tagline",
            manifest.get("descriptor") == "Scientific Intelligence for Life Sciences"
            and manifest.get("tagline") == "Biology, Engineered into Intelligence.",
            {"descriptor": manifest.get("descriptor"), "tagline": manifest.get("tagline")},
        ),
        control(
            "BR-03",
            "Founder attribution",
            manifest.get("founder") == "Lavesh Dobriyal",
            manifest.get("founder"),
        ),
        control(
            "BR-04",
            "Accessible SVG mark and wordmark",
            all(
                (ROOT / path).is_file()
                for path in ("assets/brand/biointel-mark.svg", "assets/brand/biointel-wordmark.svg")
            ),
            ["assets/brand/biointel-mark.svg", "assets/brand/biointel-wordmark.svg"],
        ),
        control(
            "BR-05",
            "Cross-platform asset dimensions",
            all(row["valid"] for row in asset_results.values()),
            asset_results,
        ),
        control(
            "BR-06",
            "All Streamlit modules brand-bound",
            len(branded_pages) == len(page_sources),
            {"branded": len(branded_pages), "total": len(page_sources)},
        ),
        control(
            "BR-07",
            "Unified header and sidebar",
            "brand_header_html(version)" in theme_source
            and "sidebar_brand_html(version)" in theme_source,
            "src/biointel/ui/theme.py",
        ),
        control(
            "BR-08",
            "Brand-safe theme typography",
            ".bio-brand-system-v136" in css_source and "Inter" in css_source,
            "src/biointel/ui/desktop_ux.css",
        ),
        control(
            "BR-09",
            "Branded DTI model identities",
            "branded_model_identity" in dti_source and "bio-model-identity" in dti_source,
            "pages/6_DTI_Predictor.py",
        ),
        control(
            "BR-10",
            "Evidence tier language",
            all(
                token in dti_source for token in ("tier_code", "evidence_label", "release_eligible")
            ),
            "Tier A-D model identity",
        ),
        control(
            "BR-11",
            "Prediction action clarity",
            "bio-action-readiness" in dti_source and "Demo acknowledgement" in dti_source,
            "Molecule, protein and acknowledgement readiness states",
        ),
        control(
            "BR-12",
            "Store release brand metadata",
            store_manifest.get("release_version") == version
            and store_manifest.get("brand_system", {}).get("name") == "BioIntel AI",
            store_manifest.get("brand_system", {}),
        ),
    ]
    passed = sum(item["passed"] for item in controls)
    report = {
        "schema": "biointel.step91.branding-qualification.v1",
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "version": version,
        "score": round(10 * passed / len(controls), 1),
        "passed_controls": passed,
        "total_controls": len(controls),
        "qualified": passed == len(controls),
        "controls": controls,
    }
    out = ROOT / "reports/generated/step91_branding_qualification.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                key: report[key]
                for key in ("version", "score", "passed_controls", "total_controls", "qualified")
            },
            indent=2,
        )
    )
    return 0 if report["qualified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
