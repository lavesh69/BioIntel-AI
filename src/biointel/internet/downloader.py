from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from biointel.internet.download_registry import DownloadRecord, register_download
from biointel.internet.network_policy import (
    InternetPolicy,
    NetworkPolicyError,
    internet_policy_from_environment,
    validate_public_https_url,
)


class InternetDownloadError(RuntimeError):
    """Raised when a secure outbound download cannot be completed."""


BLOCKED_DOWNLOAD_EXTENSIONS = {
    ".exe",
    ".msi",
    ".bat",
    ".cmd",
    ".com",
    ".scr",
    ".dll",
    ".ps1",
    ".vbs",
    ".js",
    ".jar",
    ".apk",
}


def _validate_download_filename(filename: str) -> None:
    suffixes = {suffix.lower() for suffix in Path(filename).suffixes}
    blocked = suffixes & BLOCKED_DOWNLOAD_EXTENSIONS
    if blocked:
        raise InternetDownloadError(
            "Executable or script downloads are blocked: " + ", ".join(sorted(blocked))
        )


@dataclass(frozen=True)
class DownloadResult:
    provider: str
    resource_id: str | None
    url: str
    final_url: str
    filename: str
    path: Path
    relative_path: str
    content_type: str
    size_bytes: int
    sha256: str
    etag: str | None
    last_modified: str | None
    downloaded_at_epoch: float
    from_existing_file: bool


class _SafeRedirectHandler(HTTPRedirectHandler):
    def __init__(self, policy: InternetPolicy, allowed_hosts: set[str] | None) -> None:
        super().__init__()
        self.policy = policy
        self.allowed_hosts = allowed_hosts

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        validate_public_https_url(
            newurl,
            policy=self.policy,
            allowed_hosts=self.allowed_hosts,
        )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _safe_filename(value: str, fallback: str = "download.bin") -> str:
    cleaned = unquote(value).strip().replace("\\", "_").replace("/", "_")
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", cleaned)
    cleaned = cleaned.strip("._")[:180]
    return cleaned or fallback


def _filename_from_headers(url: str, headers, preferred: str | None) -> str:  # noqa: ANN001
    if preferred:
        return _safe_filename(preferred)
    disposition = headers.get("Content-Disposition", "")
    match = re.search(r"filename\*?=(?:UTF-8''|\")?([^\";]+)", disposition, re.I)
    if match:
        return _safe_filename(match.group(1))
    path_name = Path(urlparse(url).path).name
    return _safe_filename(path_name, "download.bin")


def _content_type(headers, filename: str) -> str:  # noqa: ANN001
    header = headers.get_content_type() if hasattr(headers, "get_content_type") else None
    if header and header != "application/octet-stream":
        return str(header)
    return mimetypes.guess_type(filename)[0] or "application/octet-stream"


def _build_opener(policy: InternetPolicy, allowed_hosts: set[str] | None):
    return build_opener(_SafeRedirectHandler(policy, allowed_hosts))


def fetch_public_bytes(
    url: str,
    *,
    policy: InternetPolicy | None = None,
    allowed_hosts: set[str] | None = None,
    max_bytes: int = 10 * 1024 * 1024,
    accept: str = "*/*",
) -> tuple[bytes, dict[str, object]]:
    active = policy or internet_policy_from_environment()
    validated = validate_public_https_url(
        url,
        policy=active,
        allowed_hosts=allowed_hosts,
    )
    opener = _build_opener(active, allowed_hosts)
    request = Request(
        validated,
        headers={
            "Accept": accept,
            "User-Agent": "BioIntel-AI/2.2 outbound-research-client",
        },
        method="GET",
    )
    last_error: Exception | None = None
    for attempt in range(active.retries + 1):
        try:
            with opener.open(request, timeout=active.timeout_seconds) as response:
                final_url = response.geturl()
                validate_public_https_url(
                    final_url,
                    policy=active,
                    allowed_hosts=allowed_hosts,
                )
                declared = response.headers.get("Content-Length")
                if declared and int(declared) > max_bytes:
                    raise InternetDownloadError(
                        f"Remote response exceeds the {max_bytes / (1024 * 1024):.0f} MB limit."
                    )
                body = response.read(max_bytes + 1)
                if len(body) > max_bytes:
                    raise InternetDownloadError(
                        f"Remote response exceeds the {max_bytes / (1024 * 1024):.0f} MB limit."
                    )
                return body, {
                    "status": int(response.status),
                    "final_url": final_url,
                    "content_type": _content_type(response.headers, "download.bin"),
                    "etag": response.headers.get("ETag"),
                    "last_modified": response.headers.get("Last-Modified"),
                }
        except (HTTPError, URLError, TimeoutError, NetworkPolicyError, OSError) as exc:
            last_error = exc
            if attempt < active.retries:
                time.sleep(0.5 * (2**attempt))
    raise InternetDownloadError(f"Remote request failed: {last_error}") from last_error


def fetch_public_json(
    url: str,
    *,
    policy: InternetPolicy | None = None,
    allowed_hosts: set[str] | None = None,
    max_bytes: int = 10 * 1024 * 1024,
) -> tuple[dict[str, object], dict[str, object]]:
    body, metadata = fetch_public_bytes(
        url,
        policy=policy,
        allowed_hosts=allowed_hosts,
        max_bytes=max_bytes,
        accept="application/json",
    )
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InternetDownloadError("The remote service returned invalid JSON.") from exc
    if not isinstance(payload, dict):
        raise InternetDownloadError("The remote service returned an unexpected JSON structure.")
    return payload, metadata


def download_public_file(
    url: str,
    destination_directory: str | Path,
    *,
    project_root: str | Path,
    registry_path: str | Path,
    provider: str = "public_https",
    resource_id: str | None = None,
    preferred_filename: str | None = None,
    policy: InternetPolicy | None = None,
    allowed_hosts: set[str] | None = None,
    max_bytes: int | None = None,
    notes: str = "",
) -> tuple[DownloadResult, DownloadRecord]:
    active = policy or internet_policy_from_environment()
    limit = min(max_bytes or active.max_download_bytes, active.max_download_bytes)
    validated = validate_public_https_url(
        url,
        policy=active,
        allowed_hosts=allowed_hosts,
    )
    destination = Path(destination_directory).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    root = Path(project_root).resolve()
    opener = _build_opener(active, allowed_hosts)
    request = Request(
        validated,
        headers={
            "Accept": "*/*",
            "User-Agent": "BioIntel-AI/2.2 outbound-research-client",
        },
        method="GET",
    )

    last_error: Exception | None = None
    for attempt in range(active.retries + 1):
        temp_path: Path | None = None
        try:
            with opener.open(request, timeout=active.timeout_seconds) as response:
                final_url = response.geturl()
                validate_public_https_url(
                    final_url,
                    policy=active,
                    allowed_hosts=allowed_hosts,
                )
                filename = _filename_from_headers(final_url, response.headers, preferred_filename)
                _validate_download_filename(filename)
                target = destination / filename
                declared = response.headers.get("Content-Length")
                if declared and int(declared) > limit:
                    raise InternetDownloadError(
                        f"Remote file exceeds the {limit / (1024 * 1024):.0f} MB safety limit."
                    )
                temp_path = target.with_suffix(target.suffix + ".part")
                hasher = hashlib.sha256()
                total = 0
                with temp_path.open("wb") as output:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        total += len(chunk)
                        if total > limit:
                            raise InternetDownloadError(
                                f"Remote file exceeds the {limit / (1024 * 1024):.0f} MB safety limit."
                            )
                        hasher.update(chunk)
                        output.write(chunk)
                digest = hasher.hexdigest()
                existing = (
                    target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == digest
                )
                if not existing:
                    os.replace(temp_path, target)
                else:
                    temp_path.unlink(missing_ok=True)
                relative = target.relative_to(root).as_posix()
                result = DownloadResult(
                    provider=provider,
                    resource_id=resource_id,
                    url=validated,
                    final_url=final_url,
                    filename=target.name,
                    path=target,
                    relative_path=relative,
                    content_type=_content_type(response.headers, target.name),
                    size_bytes=total,
                    sha256=digest,
                    etag=response.headers.get("ETag"),
                    last_modified=response.headers.get("Last-Modified"),
                    downloaded_at_epoch=time.time(),
                    from_existing_file=existing,
                )
                sidecar = target.with_suffix(target.suffix + ".metadata.json")
                sidecar.write_text(
                    json.dumps(asdict(result), indent=2, default=str, sort_keys=True),
                    encoding="utf-8",
                )
                record = register_download(
                    registry_path,
                    provider=provider,
                    resource_id=resource_id,
                    url=validated,
                    filename=target.name,
                    relative_path=relative,
                    content_type=result.content_type,
                    size_bytes=total,
                    sha256=digest,
                    etag=result.etag,
                    last_modified=result.last_modified,
                    notes=notes,
                )
                return result, record
        except (HTTPError, URLError, TimeoutError, NetworkPolicyError, OSError) as exc:
            last_error = exc
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
            if attempt < active.retries:
                time.sleep(0.5 * (2**attempt))
        except InternetDownloadError:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
            raise
    raise InternetDownloadError(f"Download failed: {last_error}") from last_error
