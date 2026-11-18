from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class AuditFinding:
    key: str
    severity: str
    path: str
    message: str


_TEXT_SUFFIXES = {
    ".py", ".toml", ".yaml", ".yml", ".json", ".md", ".txt", ".ini", ".cfg",
    ".env", ".sh", ".bat", ".ps1", ".html", ".css", ".js", ".ts", ".xml",
}
_EXCLUDED_PARTS = {
    ".git", ".venv", "venv", "cache", "models", "data", "visual", "node_modules",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
}
_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "private_key",
        re.compile(
            r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----\s+"
            r"[A-Za-z0-9+/=\r\n]{64,}\s+"
            r"-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
        ),
    ),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("generic_bearer", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{24,}")),
    ("hardcoded_secret", re.compile(r"(?i)(?:api[_-]?key|secret|password|token)\s*[:=]\s*['\"]([^'\"]{24,})['\"]")),
)
_SAFE_MARKERS = (
    "example", "placeholder", "replace_me", "replace-me", "replace_with", "changeme", "your_", "dummy",
    "test-secret", "not-a-real", "redacted", "${", "os.getenv", "secret_key",
)


def _iter_text_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        relative_parts = path.relative_to(root).parts
        if not path.is_file() or any(part in _EXCLUDED_PARTS for part in relative_parts):
            continue
        if path.name == ".env.example" or path.suffix.lower() in _TEXT_SUFFIXES:
            if path.stat().st_size <= 2_000_000:
                yield path


def scan_repository_secrets(root: str | Path) -> dict[str, object]:
    base = Path(root).resolve()
    findings: list[AuditFinding] = []
    scanned = 0
    for path in _iter_text_files(base):
        scanned += 1
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        relative = path.relative_to(base)
        for name, pattern in _SECRET_PATTERNS:
            if name == "hardcoded_secret" and relative.parts and relative.parts[0] == "tests":
                continue
            for match in pattern.finditer(text):
                context = text[max(0, match.start() - 80): min(len(text), match.end() + 80)].lower()
                if any(marker in context for marker in _SAFE_MARKERS):
                    continue
                line = text.count("\n", 0, match.start()) + 1
                findings.append(
                    AuditFinding(
                        key=name,
                        severity="critical",
                        path=f"{path.relative_to(base).as_posix()}:{line}",
                        message="Possible committed credential or private key material.",
                    )
                )
    return {
        "passed": not findings,
        "scanned_files": scanned,
        "finding_count": len(findings),
        "findings": [asdict(item) for item in findings],
    }


def check_workspace_hygiene(root: str | Path) -> dict[str, object]:
    base = Path(root).resolve()
    forbidden_names = {".DS_Store", "Thumbs.db"}
    forbidden_suffixes = {".pyc", ".pyo", ".tmp", ".bak", ".orig", ".rej", ".wal", ".shm"}
    findings: list[str] = []
    for path in base.rglob("*"):
        relative_parts = path.relative_to(base).parts
        if any(part in {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"} for part in relative_parts):
            continue
        rel = path.relative_to(base).as_posix()
        if path.is_file() and (path.name in forbidden_names or path.suffix.lower() in forbidden_suffixes):
            findings.append(rel)
    return {"passed": not findings, "finding_count": len(findings), "findings": sorted(findings)[:200]}


def check_version_consistency(root: str | Path) -> dict[str, object]:
    base = Path(root).resolve()
    version = (base / "VERSION").read_text(encoding="utf-8").strip()
    expected = {
        "VERSION": version,
        "src/biointel/__init__.py": f'__version__ = "{version}"',
        "pyproject.toml": f'version = "{version}"',
    }
    failures = []
    for relative, token in expected.items():
        path = base / relative
        if not path.is_file() or token not in path.read_text(encoding="utf-8", errors="ignore"):
            failures.append(relative)
    return {"passed": not failures, "version": version, "failures": failures}


def check_local_markdown_links(root: str | Path) -> dict[str, object]:
    base = Path(root).resolve()
    broken: list[dict[str, str]] = []
    checked = 0
    link_pattern = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
    for path in base.rglob("*.md"):
        if any(part in _EXCLUDED_PARTS for part in path.relative_to(base).parts):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for raw in link_pattern.findall(text):
            target = raw.strip().split("#", 1)[0].strip()
            if not target or target.startswith(("http://", "https://", "mailto:", "#", "sandbox:")):
                continue
            checked += 1
            resolved = (path.parent / target).resolve()
            try:
                resolved.relative_to(base)
            except ValueError:
                broken.append({"source": path.relative_to(base).as_posix(), "target": target})
                continue
            if not resolved.exists():
                broken.append({"source": path.relative_to(base).as_posix(), "target": target})
    return {"passed": not broken, "checked_links": checked, "broken_count": len(broken), "broken": broken[:200]}


def repository_manifest(root: str | Path, *, exclude_reports: bool = False) -> dict[str, object]:
    base = Path(root).resolve()
    files: list[dict[str, object]] = []
    for path in sorted(base.rglob("*")):
        if not path.is_file() or any(part in {"__pycache__", ".pytest_cache", ".git"} for part in path.parts):
            continue
        relative = path.relative_to(base).as_posix()
        if exclude_reports and relative.startswith("reports/"):
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        files.append({"path": relative, "size_bytes": path.stat().st_size, "sha256": digest})
    manifest_digest = hashlib.sha256(
        json.dumps(files, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "schema": "biointel.repository-manifest.v1",
        "file_count": len(files),
        "total_bytes": sum(int(item["size_bytes"]) for item in files),
        "manifest_sha256": manifest_digest,
        "files": files,
    }


def run_repository_audit(root: str | Path) -> dict[str, object]:
    base = Path(root).resolve()
    checks = {
        "secrets": scan_repository_secrets(base),
        "workspace_hygiene": check_workspace_hygiene(base),
        "version_consistency": check_version_consistency(base),
        "markdown_links": check_local_markdown_links(base),
    }
    return {
        "schema": "biointel.repository-audit.v1",
        "passed": all(bool(item.get("passed")) for item in checks.values()),
        "checks": checks,
        "environment": {"python": os.sys.version.split()[0], "platform": os.name},
    }
