from __future__ import annotations

import base64
import hashlib
import io
import json
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

_KEY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
MAX_ARCHIVE_BYTES = 500_000_000
MAX_EXPANDED_BYTES = 2_000_000_000
MAX_FILES = 20_000


@dataclass(frozen=True)
class TrustDecision:
    passed: bool
    artifact_type: str
    publisher_key_id: str
    signature_status: str
    files_verified: int
    artifact_sha256: str
    findings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "artifact_type": self.artifact_type,
            "publisher_key_id": self.publisher_key_id,
            "signature_status": self.signature_status,
            "files_verified": self.files_verified,
            "artifact_sha256": self.artifact_sha256,
            "findings": list(self.findings),
        }


def canonical_json(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _public_key(trust_store: Path, key_id: str):
    if not _KEY_ID.fullmatch(key_id):
        raise ValueError("Invalid publisher key id.")
    path = (trust_store / f"{key_id}.pem").resolve()
    try:
        path.relative_to(trust_store.resolve())
    except ValueError as exc:
        raise ValueError("Publisher key path escapes the trust store.") from exc
    if not path.is_file():
        raise FileNotFoundError(f"Publisher key is not trusted: {key_id}")
    from cryptography.hazmat.primitives import serialization

    return serialization.load_pem_public_key(path.read_bytes())


def verify_ed25519(
    payload: bytes,
    signature: bytes,
    *,
    trust_store: str | Path,
    key_id: str,
) -> None:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    key = _public_key(Path(trust_store), key_id)
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError("Trusted publisher key is not Ed25519.")
    try:
        key.verify(signature, payload)
    except InvalidSignature as exc:
        raise ValueError("Detached Ed25519 signature is invalid.") from exc


def _safe_member(name: str) -> PurePosixPath:
    normalized = str(name).replace("\\", "/")
    path = PurePosixPath(normalized)
    if not normalized or path.is_absolute() or ".." in path.parts or "\x00" in normalized:
        raise ValueError(f"Unsafe archive member: {name}")
    return path


def _manifest_files(manifest: Mapping[str, Any]) -> list[dict[str, str]]:
    rows = manifest.get("files", [])
    if not isinstance(rows, list) or not rows:
        raise ValueError("Signed manifest has no file list.")
    output: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Signed manifest contains a non-object file row.")
        path = _safe_member(str(row.get("path", ""))).as_posix()
        digest = str(row.get("sha256", "")).lower()
        if path in seen:
            raise ValueError(f"Duplicate signed path: {path}")
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise ValueError(f"Invalid SHA-256 for signed path: {path}")
        seen.add(path)
        output.append({"path": path, "sha256": digest})
    return output


def inspect_signed_archive(
    archive_payload: bytes,
    *,
    trust_store: str | Path,
    artifact_type: str,
    manifest_name: str = "plugin.json",
    signature_name: str = "SIGNATURE.ed25519",
) -> TrustDecision:
    findings: list[str] = []
    key_id = ""
    verified = 0
    signature_status = "not_verified"
    if len(archive_payload) > MAX_ARCHIVE_BYTES:
        return TrustDecision(
            False,
            artifact_type,
            "",
            signature_status,
            0,
            sha256_bytes(archive_payload),
            ("Archive exceeds the configured compressed-size limit.",),
        )

    try:
        with zipfile.ZipFile(io.BytesIO(archive_payload)) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_FILES:
                findings.append("Archive contains too many files.")
            expanded = sum(int(info.file_size) for info in infos)
            if expanded > MAX_EXPANDED_BYTES:
                findings.append("Expanded archive exceeds the configured limit.")
            names: dict[str, zipfile.ZipInfo] = {}
            for info in infos:
                path = _safe_member(info.filename).as_posix()
                if path in names:
                    findings.append(f"Duplicate archive path: {path}")
                names[path] = info
                mode = (info.external_attr >> 16) & 0o170000
                if mode == 0o120000:
                    findings.append(f"Symbolic link is not permitted: {path}")

            if manifest_name not in names:
                findings.append(f"Missing signed manifest: {manifest_name}")
            if signature_name not in names:
                findings.append(f"Missing detached signature: {signature_name}")
            if findings:
                raise ValueError("; ".join(findings))

            manifest_value = json.loads(archive.read(manifest_name).decode("utf-8-sig"))
            if not isinstance(manifest_value, dict):
                raise ValueError("Signed manifest must be a JSON object.")
            key_id = str(manifest_value.get("publisher_key_id", "")).strip()
            signature_text = archive.read(signature_name).decode("ascii").strip()
            signature = base64.b64decode(signature_text, validate=True)
            verify_ed25519(
                canonical_json(manifest_value),
                signature,
                trust_store=trust_store,
                key_id=key_id,
            )
            signature_status = "verified"

            signed_files = _manifest_files(manifest_value)
            allowed = {manifest_name, signature_name, *(row["path"] for row in signed_files)}
            unsigned = sorted(set(names) - allowed)
            if unsigned:
                findings.append("Unsigned archive members: " + ", ".join(unsigned[:20]))
            for row in signed_files:
                info = names.get(row["path"])
                if info is None:
                    findings.append(f"Signed file is missing: {row['path']}")
                    continue
                actual = sha256_bytes(archive.read(info))
                if actual != row["sha256"]:
                    findings.append(f"Signed file hash mismatch: {row['path']}")
                    continue
                verified += 1
    except (OSError, ValueError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
        if not findings or str(exc) not in findings:
            findings.append(str(exc))

    return TrustDecision(
        not findings and signature_status == "verified",
        artifact_type,
        key_id,
        signature_status,
        verified,
        sha256_bytes(archive_payload),
        tuple(dict.fromkeys(item for item in findings if item)),
    )


def extract_trusted_archive(
    archive_payload: bytes,
    destination: str | Path,
    *,
    trust_store: str | Path,
    artifact_type: str = "plugin",
) -> TrustDecision:
    decision = inspect_signed_archive(
        archive_payload,
        trust_store=trust_store,
        artifact_type=artifact_type,
    )
    if not decision.passed:
        raise PermissionError("Signed archive failed trust verification: " + "; ".join(decision.findings))
    target = Path(destination).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise FileExistsError(f"Destination already exists: {target}")
    with tempfile.TemporaryDirectory(prefix="biointel-trusted-", dir=target.parent) as temporary:
        stage = Path(temporary) / "content"
        stage.mkdir()
        with zipfile.ZipFile(io.BytesIO(archive_payload)) as archive:
            for info in archive.infolist():
                relative = _safe_member(info.filename)
                output = stage.joinpath(*relative.parts).resolve()
                output.relative_to(stage.resolve())
                if info.is_dir():
                    output.mkdir(parents=True, exist_ok=True)
                    continue
                output.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, output.open("wb") as sink:
                    shutil.copyfileobj(source, sink, length=1024 * 1024)
        stage.replace(target)
    return decision


def isolated_plugin_environment(plugin_root: str | Path) -> Path:
    root = Path(plugin_root).resolve()
    return root / ".venv"
