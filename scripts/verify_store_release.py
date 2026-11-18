from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MAX_RELEASE_BYTES = 2 * 1024**3
IGNORE_PARTS = {
    "node_modules",
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "dist-release",
}


@dataclass
class Check:
    name: str
    status: str
    detail: str
    category: str = "internal"


class Audit:
    def __init__(self) -> None:
        self.checks: list[Check] = []

    def add(self, name: str, ok: bool, detail: str, *, category: str = "internal") -> None:
        self.checks.append(Check(name, "pass" if ok else "fail", detail, category))

    def external(self, name: str, detail: str) -> None:
        self.checks.append(Check(name, "external_action", detail, "external"))

    @property
    def failures(self) -> list[Check]:
        return [check for check in self.checks if check.status == "fail"]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8").strip()


def source_size() -> int:
    total = 0
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in IGNORE_PARTS for part in path.parts):
            continue
        total += path.stat().st_size
    return total


def dimensions(path: Path) -> tuple[int, int, str]:
    from PIL import Image

    with Image.open(path) as image:
        return image.width, image.height, image.mode


def check_json(audit: Audit, relative: str) -> dict[str, Any]:
    path = ROOT / relative
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        audit.add(f"JSON: {relative}", False, str(exc))
        return {}
    audit.add(f"JSON: {relative}", True, "Valid JSON")
    return payload


def verify_versions(audit: Audit) -> str:
    version = text("VERSION")
    candidates = {
        "pyproject.toml": re.search(
            r'^version\s*=\s*"([^"]+)"', text("pyproject.toml"), re.MULTILINE
        ),
        "src/biointel/__init__.py": re.search(
            r'__version__\s*=\s*"([^"]+)"', text("src/biointel/__init__.py")
        ),
        "mobile package": re.search(
            r'"version"\s*:\s*"([^"]+)"', text("platform/mobile/package.json")
        ),
        "desktop package": re.search(
            r'"version"\s*:\s*"([^"]+)"', text("platform/desktop/package.json")
        ),
        "Android": re.search(
            r'versionName\s+"([^"]+)"', text("platform/mobile/android/app/build.gradle")
        ),
        "iOS": re.search(
            r"MARKETING_VERSION\s*=\s*([^;]+);",
            text("platform/mobile/ios/App/App.xcodeproj/project.pbxproj"),
        ),
    }
    for name, match in candidates.items():
        actual = match.group(1).strip() if match else "missing"
        audit.add(
            f"Version consistency: {name}", actual == version, f"Expected {version}; found {actual}"
        )
    audit.add("Semantic release version", bool(re.fullmatch(r"\d+\.\d+\.\d+", version)), version)
    return version


def verify_android(audit: Audit, version: str) -> None:
    variables = text("platform/mobile/android/variables.gradle")
    target_match = re.search(r"targetSdkVersion\s*=\s*(\d+)", variables)
    compile_match = re.search(r"compileSdkVersion\s*=\s*(\d+)", variables)
    target = int(target_match.group(1)) if target_match else 0
    compile_sdk = int(compile_match.group(1)) if compile_match else 0
    audit.add("Android target SDK", target >= 35, f"targetSdkVersion={target}")
    audit.add(
        "Android compile SDK", compile_sdk >= target >= 35, f"compileSdkVersion={compile_sdk}"
    )

    gradle = text("platform/mobile/android/app/build.gradle")
    audit.add(
        "Android release shrinking",
        "minifyEnabled true" in gradle and "shrinkResources true" in gradle,
        "R8 and resource shrinking enabled",
    )
    audit.add(
        "Android external signing",
        "BIOINTEL_ANDROID_KEYSTORE_PATH" in gradle,
        "Release signing is supplied by environment",
    )
    audit.add("Android version name", f'versionName "{version}"' in gradle, version)

    manifest = text("platform/mobile/android/app/src/main/AndroidManifest.xml")
    permissions = re.findall(r'<uses-permission[^>]+android:name="([^"]+)"', manifest)
    allowed = {"android.permission.INTERNET", "android.permission.ACCESS_NETWORK_STATE"}
    unexpected = sorted(set(permissions) - allowed)
    audit.add(
        "Android least-privilege permissions",
        not unexpected,
        f"Permissions={sorted(set(permissions))}; unexpected={unexpected}",
    )
    audit.add(
        "Android cleartext disabled",
        'android:usesCleartextTraffic="false"' in manifest,
        "HTTPS-only network policy",
    )
    audit.add(
        "Android backups disabled",
        'android:allowBackup="false"' in manifest,
        "Sensitive local preferences excluded from OS backup",
    )
    audit.add(
        "Android App Bundle workflow",
        (ROOT / ".github/workflows/store-mobile.yml").is_file()
        and "bundleRelease" in text("scripts/store/build_android_release.sh"),
        "Signed AAB workflow present",
    )
    audit.external(
        "Google Play signing/account",
        "Provide the Play Console account and upload keystore secrets; enable Play App Signing before submission.",
    )


def verify_ios(audit: Audit, version: str) -> None:
    info = text("platform/mobile/ios/App/App/Info.plist")
    project = text("platform/mobile/ios/App/App.xcodeproj/project.pbxproj")
    manifest = ROOT / "platform/mobile/ios/App/App/PrivacyInfo.xcprivacy"
    audit.add(
        "iOS privacy manifest",
        manifest.is_file() and "NSPrivacyTracking" in manifest.read_text(),
        "PrivacyInfo.xcprivacy present",
    )
    audit.add(
        "iOS privacy manifest embedded",
        "PrivacyInfo.xcprivacy in Resources" in project,
        "Xcode Resources build phase contains manifest",
    )
    audit.add("iOS version", f"MARKETING_VERSION = {version};" in project, version)
    audit.add(
        "iOS deployment target",
        all(
            float(value) >= 15.0
            for value in re.findall(r"IPHONEOS_DEPLOYMENT_TARGET = ([0-9.]+);", project)
        ),
        "Minimum iOS 15.0",
    )
    audit.add(
        "iOS encryption declaration",
        "ITSAppUsesNonExemptEncryption" in info and "<false/>" in info,
        "No non-exempt encryption declared",
    )
    audit.add(
        "iOS obsolete armv7 requirement removed",
        "armv7" not in info,
        "Modern device capability configuration",
    )
    audit.add(
        "iOS IPA workflow",
        "xcodebuild -exportArchive" in text("scripts/store/build_ios_release.sh"),
        "Archive and App Store IPA export scripted",
    )
    audit.external(
        "Apple signing/account",
        "Provide Apple Developer/App Store Connect access, distribution certificate, provisioning profile and team identifier on a macOS/Xcode runner.",
    )


def verify_windows(audit: Audit, version: str) -> None:
    package = json.loads(text("platform/desktop/package.json"))
    build = package.get("build", {})
    targets = set(build.get("win", {}).get("target", []))
    audit.add("Windows APPX target", "appx" in targets, f"Targets={sorted(targets)}")
    audit.add("Windows installer target", "nsis" in targets, f"Targets={sorted(targets)}")
    audit.add("Windows version", package.get("version") == version, str(package.get("version")))
    main = text("platform/desktop/src/main.cjs")
    audit.add(
        "Windows external navigation isolation",
        "setWindowOpenHandler" in main and "shell.openExternal" in main,
        "External URLs are opened outside the privileged renderer",
    )
    audit.add(
        "Windows context isolation",
        "contextIsolation: true" in main and "nodeIntegration: false" in main,
        "Secure Electron renderer defaults",
    )
    audit.add(
        "Windows local report preservation",
        "insideReports" in main and "preserveExisting" in main,
        "User report files are preserved across upgrades",
    )
    audit.add(
        "Windows reproducible backend setup",
        "pip install -e $Root" in text("scripts/store/build_windows_release.ps1"),
        "Python project installed before PyInstaller",
    )
    audit.external(
        "Microsoft Store identity/signing",
        "Replace Partner Center identity fields and provide a code-signing certificate before APPX submission.",
    )


def verify_metadata(audit: Audit) -> None:
    limits = {
        "store/metadata/google-play/en-US/title.txt": 30,
        "store/metadata/google-play/en-US/short-description.txt": 80,
        "store/metadata/google-play/en-US/full-description.txt": 4000,
        "store/metadata/apple/en-US/name.txt": 30,
        "store/metadata/apple/en-US/subtitle.txt": 30,
        "store/metadata/apple/en-US/promotional-text.txt": 170,
        "store/metadata/apple/en-US/keywords.txt": 100,
    }
    for relative, limit in limits.items():
        value = text(relative)
        audit.add(
            f"Metadata length: {relative}",
            0 < len(value) <= limit,
            f"{len(value)}/{limit} characters",
        )
    all_copy = "\n".join(text(path) for path in limits)
    forbidden = [
        phrase
        for phrase in ("diagnose disease", "medical diagnosis", "guaranteed cure")
        if phrase in all_copy.lower()
    ]
    audit.add(
        "Store copy scientific boundary",
        not forbidden and "research" in all_copy.lower(),
        f"Forbidden claims={forbidden}",
    )


def verify_assets(audit: Audit) -> None:
    icon = ROOT / "store/assets/apple/icon-1024.png"
    width, height, mode = dimensions(icon)
    audit.add("Apple 1024 icon", (width, height) == (1024, 1024), f"{width}x{height}")
    audit.add("Apple icon no alpha", mode in {"RGB", "L"}, f"mode={mode}")
    feature = ROOT / "store/screenshots/google-play/feature-graphic-1024x500.png"
    if feature.exists():
        fw, fh, _ = dimensions(feature)
        audit.add("Google Play feature graphic", (fw, fh) == (1024, 500), f"{fw}x{fh}")
    else:
        audit.add(
            "Google Play feature graphic",
            False,
            "Missing store/screenshots/google-play/feature-graphic-1024x500.png",
        )

    required_groups = {
        "Google Play screenshots": ROOT / "store/screenshots/google-play/phone",
        "Apple screenshots": ROOT / "store/screenshots/apple/iphone-6.9",
        "Microsoft screenshots": ROOT / "store/screenshots/microsoft/desktop",
    }
    for name, directory in required_groups.items():
        count = len(list(directory.glob("*.png"))) if directory.exists() else 0
        audit.add(name, count >= 3, f"{count} PNG files")


def verify_models(audit: Audit) -> None:
    payload = check_json(audit, "store/model-manifest.json")
    entries = payload.get("models", []) if isinstance(payload, dict) else []
    mismatches: list[str] = []
    for item in entries:
        path = ROOT / item.get("path", "")
        if (
            not path.is_file()
            or path.stat().st_size != item.get("size_bytes")
            or sha256(path) != item.get("sha256")
        ):
            mismatches.append(item.get("path", "unknown"))
    joblib_count = len(list((ROOT / "models").glob("*.joblib")))
    audit.add(
        "Model manifest coverage",
        len(entries) == joblib_count and not mismatches,
        f"manifest={len(entries)}, joblib={joblib_count}, mismatches={mismatches[:5]}",
    )


def verify_databases(audit: Audit) -> None:
    databases = [
        path
        for path in ROOT.rglob("*")
        if path.is_file()
        and path.suffix.lower() in {".db", ".sqlite", ".sqlite3"}
        and not any(part in IGNORE_PARTS for part in path.parts)
    ]
    bad: list[str] = []
    foreign_key_issues = 0
    for path in databases:
        try:
            with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
                result = connection.execute("PRAGMA integrity_check").fetchone()
                if not result or result[0] != "ok":
                    bad.append(str(path.relative_to(ROOT)))
                foreign_key_issues += len(connection.execute("PRAGMA foreign_key_check").fetchall())
        except sqlite3.Error:
            bad.append(str(path.relative_to(ROOT)))
    audit.add(
        "SQLite integrity",
        not bad and bool(databases),
        f"healthy={len(databases)-len(bad)}/{len(databases)}; bad={bad[:5]}",
    )
    audit.add("SQLite foreign keys", foreign_key_issues == 0, f"violations={foreign_key_issues}")


def verify_security_and_docs(audit: Audit) -> None:
    required = [
        "docs/legal/PRIVACY_POLICY.md",
        "docs/legal/TERMS_OF_USE.md",
        "docs/legal/SUPPORT.md",
        "docs/legal/site/privacy.html",
        "docs/legal/site/terms.html",
        "docs/legal/site/support.html",
        "store/data-safety/google-play-data-safety.json",
        "store/data-safety/apple-app-privacy.json",
        "store/checklists/STORE_SUBMISSION_CHECKLIST.md",
        "deploy/store/docker-compose.yml",
        "deploy/store/Caddyfile",
        ".github/workflows/store-mobile.yml",
        ".github/workflows/store-windows.yml",
        ".github/workflows/store-legal-pages.yml",
    ]
    missing = [relative for relative in required if not (ROOT / relative).is_file()]
    audit.add("Store/legal artifact coverage", not missing, f"missing={missing}")
    for relative in (
        "store/data-safety/google-play-data-safety.json",
        "store/data-safety/apple-app-privacy.json",
        "store/data-safety/permissions-inventory.json",
    ):
        check_json(audit, relative)
    middleware = text("src/biointel/api/middleware.py")
    audit.add(
        "Public legal/bootstrap endpoints",
        '"/legal"' in middleware and '"/v1/mobile/bootstrap"' in middleware,
        "Mobile connection bootstrap and legal pages work before API-key authentication",
    )
    audit.add(
        "Production UI authentication",
        "BIOINTEL_UI_AUTH_REQUIRED" in text("src/biointel/ui/access_control.py"),
        "Production Streamlit sign-in gate present",
    )


def verify_windows_offline_runtime(audit: Audit) -> None:
    pyproject = text("pyproject.toml")
    mypy_match = re.search(r"\[tool\.mypy\][\s\S]*?python_version\s*=\s*\"([^\"]+)\"", pyproject)
    mypy_version = mypy_match.group(1) if mypy_match else "missing"
    audit.add("MyPy Python target", mypy_version == "3.11", f"python_version={mypy_version}")

    config = text(".streamlit/config.toml")
    upload_match = re.search(r"maxUploadSize\s*=\s*(\d+)", config)
    message_match = re.search(r"maxMessageSize\s*=\s*(\d+)", config)
    upload_limit = int(upload_match.group(1)) if upload_match else 0
    message_limit = int(message_match.group(1)) if message_match else 0
    audit.add(
        "Large upload transport configuration",
        upload_limit == 1024 and message_limit >= upload_limit,
        f"maxUploadSize={upload_limit} MB; maxMessageSize={message_limit} MB",
    )
    audit.add(
        "Local multi-GB intake workflow",
        (ROOT / "src/biointel/utils/large_files.py").is_file()
        and (ROOT / "RUN_APP_LOW_MEMORY_WINDOWS.bat").is_file(),
        "Reference-based intake and low-memory launcher present",
    )

    required = [
        ROOT / "requirements-windows-cp311-offline.lock",
        ROOT / "wheelhouse/windows-cp311-x64/MANIFEST_SHA256.txt",
        ROOT / "wheelhouse/windows-cp311-x64/WHEELHOUSE_METADATA.json",
        ROOT / "scripts/verify_windows_wheelhouse.py",
        ROOT / "INSTALL_WINDOWS.bat",
    ]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    audit.add("Offline Windows runtime bundle", not missing, f"missing={missing}")
    if missing:
        return

    metadata = check_json(audit, "wheelhouse/windows-cp311-x64/WHEELHOUSE_METADATA.json")
    manifest_rows = [
        row
        for row in text("wheelhouse/windows-cp311-x64/MANIFEST_SHA256.txt").splitlines()
        if row.strip()
    ]
    lock_rows = [
        row
        for row in text("requirements-windows-cp311-offline.lock").splitlines()
        if row.strip() and not row.lstrip().startswith("#")
    ]
    wheel_count = len(list((ROOT / "wheelhouse/windows-cp311-x64").glob("*.whl")))
    expected_count = int(metadata.get("wheel_count", -1)) if isinstance(metadata, dict) else -1
    audit.add(
        "Offline wheelhouse coverage",
        wheel_count == expected_count == len(manifest_rows) == len(lock_rows) and wheel_count >= 90,
        f"wheels={wheel_count}; metadata={expected_count}; manifest={len(manifest_rows)}; lock={len(lock_rows)}",
    )
    audit.add(
        "Offline dependency hashes",
        all(" --hash=sha256:" in row for row in lock_rows),
        f"hashed_rows={sum(' --hash=sha256:' in row for row in lock_rows)}/{len(lock_rows)}",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate BioIntel AI source readiness for store packaging."
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return non-zero when any internally fixable check fails.",
    )
    parser.add_argument("--output", default="reports/store_release_verification.json")
    args = parser.parse_args()

    audit = Audit()
    version = verify_versions(audit)
    verify_android(audit, version)
    verify_ios(audit, version)
    verify_windows(audit, version)
    verify_metadata(audit)
    verify_assets(audit)
    verify_models(audit)
    verify_databases(audit)
    verify_security_and_docs(audit)
    verify_windows_offline_runtime(audit)
    size = source_size()
    audit.add(
        "Release size below 2 GiB",
        size < MAX_RELEASE_BYTES,
        f"{size / 1024**2:.2f} MiB excluding build caches",
    )

    result = {
        "generated_at": datetime.now(UTC).isoformat(),
        "version": version,
        "implementation_ready": not audit.failures,
        "internal_failures": len(audit.failures),
        "external_actions": sum(check.status == "external_action" for check in audit.checks),
        "release_size_bytes": size,
        "checks": [asdict(check) for check in audit.checks],
    }
    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")

    for check in audit.checks:
        symbol = {"pass": "PASS", "fail": "FAIL", "external_action": "EXTERNAL"}[check.status]
        print(f"[{symbol}] {check.name}: {check.detail}")
    print(
        f"\nInternal failures: {len(audit.failures)} | External account/signing actions: {result['external_actions']}"
    )
    print(f"Report: {output}")
    return 1 if args.strict and audit.failures else 0


if __name__ == "__main__":
    sys.exit(main())
