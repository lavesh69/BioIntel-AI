from __future__ import annotations

import hashlib
import ipaddress
import os
import socket
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


def _private_ipv4_addresses() -> list[str]:
    addresses: set[str] = {"127.0.0.1"}
    try:
        for item in socket.getaddrinfo(socket.gethostname(), None, family=socket.AF_INET):
            address = str(item[4][0])
            if address and not address.startswith("169.254."):
                addresses.add(address)
    except OSError:
        pass
    return sorted(addresses)


def generate_lan_tls_certificate(target_dir: Path, *, common_name: str = "BioIntel Live Workspace", valid_days: int = 365) -> dict[str, Any]:
    """Generate a local self-signed TLS certificate for trusted-LAN transport.

    The private key never leaves local UserData. Browsers may show a trust warning
    until the certificate is explicitly trusted by the lab administrator.
    """
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
    except ImportError as exc:  # pragma: no cover - installer includes cryptography
        raise RuntimeError("The bundled cryptography package is required for LAN HTTPS.") from exc

    target_dir = Path(target_dir).expanduser().resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    key_path = target_dir / "biointel-live-workspace-key.pem"
    cert_path = target_dir / "biointel-live-workspace-cert.pem"
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.now(UTC)
    hostname = socket.gethostname().strip() or "biointel-local"
    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "BioIntel AI Local Lab"),
            x509.NameAttribute(NameOID.COMMON_NAME, common_name[:64]),
        ]
    )
    san_entries: list[x509.GeneralName] = [x509.DNSName("localhost"), x509.DNSName(hostname)]
    for address in _private_ipv4_addresses():
        try:
            san_entries.append(x509.IPAddress(ipaddress.ip_address(address)))
        except ValueError:
            continue
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=min(max(int(valid_days), 30), 825)))
        .add_extension(x509.SubjectAlternativeName(san_entries), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    key_bytes = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    cert_bytes = certificate.public_bytes(serialization.Encoding.PEM)
    temporary_key = key_path.with_suffix(".tmp")
    temporary_cert = cert_path.with_suffix(".tmp")
    temporary_key.write_bytes(key_bytes)
    temporary_cert.write_bytes(cert_bytes)
    os.replace(temporary_key, key_path)
    os.replace(temporary_cert, cert_path)
    try:
        os.chmod(key_path, 0o600)
        os.chmod(cert_path, 0o644)
    except OSError:
        pass
    fingerprint = hashlib.sha256(certificate.public_bytes(serialization.Encoding.DER)).hexdigest()
    return {
        "certificate_file": str(cert_path),
        "private_key_file": str(key_path),
        "sha256_fingerprint": fingerprint,
        "valid_from_utc": certificate.not_valid_before_utc.isoformat(timespec="seconds"),
        "valid_until_utc": certificate.not_valid_after_utc.isoformat(timespec="seconds"),
        "subject_alt_names": [str(item.value) for item in san_entries],
        "self_signed": True,
    }


def inspect_tls_files(certificate_file: str, private_key_file: str) -> dict[str, Any]:
    cert_path = Path(str(certificate_file or "")).expanduser()
    key_path = Path(str(private_key_file or "")).expanduser()
    return {
        "certificate_file": str(cert_path),
        "private_key_file": str(key_path),
        "certificate_exists": cert_path.is_file(),
        "private_key_exists": key_path.is_file(),
        "ready": cert_path.is_file() and key_path.is_file(),
    }


__all__ = ["generate_lan_tls_certificate", "inspect_tls_files"]
