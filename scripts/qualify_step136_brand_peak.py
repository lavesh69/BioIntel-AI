from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def result(control_id: str, name: str, passed: bool, evidence: Any) -> dict[str, Any]:
    return {"control_id": control_id, "name": name, "passed": bool(passed), "evidence": evidence}


def main() -> int:
    brand_source = (ROOT / "src/biointel/ui/brand.py").read_text(encoding="utf-8")
    theme_source = (ROOT / "src/biointel/ui/theme.py").read_text(encoding="utf-8")
    css_source = (ROOT / "src/biointel/ui/desktop_ux.css").read_text(encoding="utf-8")
    style_source = (ROOT / "src/biointel/ui/style_catalog.py").read_text(encoding="utf-8")
    onboarding_source = (ROOT / "src/biointel/ui/onboarding.py").read_text(encoding="utf-8")
    app_source = (ROOT / "app.py").read_text(encoding="utf-8")
    pdf_source = (ROOT / "src/biointel/reports/pdf_report.py").read_text(encoding="utf-8")
    workspace_report = (ROOT / "src/biointel/reports/workspace_report.py").read_text(encoding="utf-8")
    architecture = json.loads((ROOT / "brand/product_architecture.json").read_text(encoding="utf-8"))
    manifest = json.loads((ROOT / "brand/brand_manifest.json").read_text(encoding="utf-8"))
    asset_manifest = json.loads((ROOT / "assets/brand/brand-manifest.json").read_text(encoding="utf-8"))

    logos = sorted((ROOT / "brand/logo").glob("*.svg"))
    logo_valid = True
    for path in logos:
        try:
            ET.fromstring(path.read_text(encoding="utf-8"))
        except Exception:
            logo_valid = False

    required_external = [
        ROOT / "brand/website/HOMEPAGE_COPY.md",
        ROOT / "brand/store_assets/SCREENSHOT_STORYBOARD.md",
        ROOT / "brand/media_kit/README.md",
        ROOT / "brand/social/LAUNCH_COPY.md",
        ROOT / "brand/report_templates/report_cover.html",
        ROOT / "brand/BIOINTEL_BRAND_GUIDELINES.pdf",
    ]

    controls = [
        result("BR136-01", "Positioning and primary tagline", "Biology, Engineered into Intelligence." in brand_source and "Scientific Intelligence for Life Sciences" in brand_source, asset_manifest),
        result("BR136-02", "Seven-family product architecture", len(architecture.get("families", [])) == 7, [item.get("label") for item in architecture.get("families", [])]),
        result("BR136-03", "Approved logo variants", len(logos) >= 4 and logo_valid and "filter" not in (ROOT / "brand/logo/biointel-ai-full.svg").read_text(encoding="utf-8"), [p.name for p in logos]),
        result("BR136-04", "BioIntel Signature palette", 'DEFAULT_THEME = "BioIntel Signature"' in style_source and all(token in style_source for token in ("#22D3EE", "#3B82F6", "#8B5CF6", "#07111F")), "src/biointel/ui/style_catalog.py"),
        result("BR136-05", "Two-family typography hierarchy", (ROOT / "brand/typography.json").is_file() and "Inter" in (ROOT / "brand/typography.json").read_text(encoding="utf-8") and "Mono" in (ROOT / "brand/typography.json").read_text(encoding="utf-8"), "brand/typography.json"),
        result("BR136-06", "Home brand showcase", "Scientific intelligence for life sciences." in app_source and "brand_trust_strip_html" in app_source, "app.py"),
        result("BR136-07", "Professional founder placement", "BRAND.founder" not in brand_source.split("def brand_header_html", 1)[1].split("def sidebar_brand_html", 1)[0] and "Created and developed by" in brand_source, "Header excludes founder; About retains attribution"),
        result("BR136-08", "Professional line-icon system", len(list((ROOT / "brand/icons").glob("*.svg"))) >= 7 and "font-variant-emoji:text" in css_source, "brand/icons"),
        result("BR136-09", "Restrained motion policy", "--biointel-motion-fast:180ms" in css_source and ".pv-orbit" in css_source and "animation:none!important" in css_source, "src/biointel/ui/desktop_ux.css"),
        result("BR136-10", "Scientific trust strip", "def brand_trust_strip_html" in brand_source and all(label in brand_source for label in ("Evidence level", "Confidence", "Dataset status", "Model status")), "src/biointel/ui/brand.py"),
        result("BR136-11", "Compact module naming rules", "COMPACT_MODULE_NAMES" in brand_source and "compact_module_name" in theme_source, "Navigation retains full scientific descriptions while using compact labels"),
        result("BR136-12", "Signature components", all(token in css_source for token in ("bio-brand-trust-strip", "bio-evidence-tier", "biointel-radius-card")), "src/biointel/ui/desktop_ux.css"),
        result("BR136-13", "Semantic chart palette", all(token in theme_source for token in ("#22D3EE", "#3B82F6", "#22C55E", "#F59E0B", "#EF4444", "#94A3B8")), "src/biointel/ui/theme.py"),
        result("BR136-14", "Simplified scientific background", '[data-testid="stAppViewContainer"]::before' in css_source and "animation:none!important" in css_source, "Decorative background motion disabled"),
        result("BR136-15", "Premium first-launch onboarding", "bio-onboarding-brand" in onboarding_source and "BRAND.tagline" in onboarding_source, "src/biointel/ui/onboarding.py"),
        result("BR136-16", "External launch asset kit", all(path.is_file() and path.stat().st_size > 0 for path in required_external), [path.relative_to(ROOT).as_posix() for path in required_external]),
        result("BR136-17", "Branded report outputs", "Generated with BioIntel AI" in pdf_source and "BRAND.tagline" in workspace_report and "Evidence-aware scientific intelligence" in workspace_report, ["src/biointel/reports/pdf_report.py", "src/biointel/reports/workspace_report.py"]),
        result("BR136-18", "Brand governance source of truth", manifest.get("asset_count", 0) >= 20 and (ROOT / "brand/design_tokens.css").is_file() and (ROOT / "brand/BRAND_GUIDELINES.md").is_file(), manifest),
    ]
    passed = sum(item["passed"] for item in controls)
    report = {
        "schema": "biointel.step136.brand-peak-qualification.v1",
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "version": (ROOT / "VERSION").read_text(encoding="utf-8").strip(),
        "tagline": "Biology, Engineered into Intelligence.",
        "passed_controls": passed,
        "total_controls": len(controls),
        "qualified": passed == len(controls),
        "score": round(10 * passed / len(controls), 1),
        "brand_guidelines_sha256": sha256(ROOT / "brand/BIOINTEL_BRAND_GUIDELINES.pdf"),
        "controls": controls,
    }
    output = ROOT / "reports/generated/step136_brand_peak_qualification.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("score", "passed_controls", "total_controls", "qualified")}, indent=2))
    return 0 if report["qualified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
