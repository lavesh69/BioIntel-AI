from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _exists(root: Path, relative: str) -> bool:
    return (root / relative).is_file()


def build_store_readiness(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    checks = {
        "privacy_policy": _exists(root, "docs/legal/PRIVACY_POLICY.md"),
        "terms_of_use": _exists(root, "docs/legal/TERMS_OF_USE.md"),
        "support_document": _exists(root, "docs/legal/SUPPORT.md"),
        "mobile_package": _exists(root, "platform/mobile/package.json"),
        "capacitor_configuration": _exists(root, "platform/mobile/capacitor.config.ts"),
        "android_project": (root / "platform/mobile/android").is_dir(),
        "ios_project": (root / "platform/mobile/ios").is_dir(),
        "desktop_package": _exists(root, "platform/desktop/package.json"),
        "windows_backend_spec": _exists(root, "platform/desktop/BioIntelDesktop.spec"),
        "store_metadata": (root / "store/metadata").is_dir(),
        "store_assets": (root / "store/assets").is_dir(),
        "mobile_release_workflow": _exists(root, ".github/workflows/store-mobile.yml"),
        "windows_release_workflow": _exists(root, ".github/workflows/store-windows.yml"),
        "privacy_site_workflow": _exists(root, ".github/workflows/store-legal-pages.yml"),
        "release_manifest": _exists(root, "store/release-manifest.json"),
        "offline_windows_lock": _exists(root, "requirements-windows-cp311-offline.lock"),
        "offline_windows_wheelhouse": _exists(
            root, "wheelhouse/windows-cp311-x64/WHEELHOUSE_METADATA.json"
        ),
        "offline_windows_installer": _exists(root, "INSTALL_WINDOWS.bat"),
        "low_memory_launcher": _exists(root, "RUN_APP_LOW_MEMORY_WINDOWS.bat"),
        "large_file_intake": _exists(root, "src/biointel/utils/large_files.py"),
    }
    repository_ready = sum(checks.values())
    total = len(checks)
    external_blockers = [
        "Reserve final bundle/package identifiers in Google Play, App Store Connect and Microsoft Partner Center.",
        "Provide the publishing organisation's legal name, support contact and public privacy-policy URL.",
        "Provide Android upload keystore credentials and enrol in Play App Signing.",
        "Provide an Apple Developer team, signing certificate and provisioning profile; build/upload iOS on macOS with Xcode.",
        "Provide Microsoft Store identity values from Partner Center for the MSIX/AppX manifest.",
        "Deploy the production BioIntel server with HTTPS before releasing connected mobile builds.",
        "Complete physical-device, TestFlight, Play internal-track and Windows certification testing.",
    ]
    manifest: dict[str, Any] = {}
    manifest_path = root / "store" / "release-manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            manifest = {"error": "release-manifest.json is invalid JSON"}
    return {
        "version": version,
        "repository_checks": checks,
        "repository_ready_count": repository_ready,
        "repository_check_count": total,
        "repository_readiness_percent": round(repository_ready / max(total, 1) * 100, 1),
        "external_blockers": external_blockers,
        "manifest": manifest,
        "truthful_status": (
            "Repository-side store preparation can be complete, but signed binaries and store approval require external developer accounts, certificates, identifiers and review."
        ),
    }
