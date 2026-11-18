from __future__ import annotations

import ipaddress
import os
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

OFFICIAL_SCIENTIFIC_HOSTS = frozenset(
    {
        "data.rcsb.org",
        "files.rcsb.org",
        "www.rcsb.org",
        "rest.uniprot.org",
        "www.uniprot.org",
        "www.ebi.ac.uk",
        "ftp.ebi.ac.uk",
        "eutils.ncbi.nlm.nih.gov",
        "pubchem.ncbi.nlm.nih.gov",
        "www.ncbi.nlm.nih.gov",
        "bindingdb.org",
        "www.bindingdb.org",
        "api.openai.com",
        "api.ncbi.nlm.nih.gov",
        "search.rcsb.org",
        "rest.ensembl.org",
        "clinicaltrials.gov",
        "reactome.org",
        "string-db.org",
        "pubmed.ncbi.nlm.nih.gov",
        "europepmc.org",
        "gnomad.broadinstitute.org",
        "www.ensembl.org",
        "openneuro.org",
        "portal.brain-map.org",
        "www.proteinatlas.org",
        "www.guidetopharmacology.org",
        "gpcrdb.org",
    }
)


class NetworkPolicyError(ValueError):
    """Raised when an outbound URL violates the local security policy."""


@dataclass(frozen=True)
class InternetPolicy:
    enabled: bool = True
    allow_public_https: bool = True
    official_hosts_only: bool = False
    resolve_dns: bool = True
    max_download_bytes: int = 250 * 1024 * 1024
    timeout_seconds: float = 30.0
    retries: int = 2


def internet_policy_from_environment() -> InternetPolicy:
    def enabled(name: str, default: bool) -> bool:
        raw = os.environ.get(name)
        if raw is None:
            return default
        return raw.strip().lower() not in {"0", "false", "no", "off"}

    max_mb = int(os.environ.get("BIOINTEL_MAX_DOWNLOAD_MB", "250"))
    timeout = float(os.environ.get("BIOINTEL_NETWORK_TIMEOUT", "30"))
    retries = int(os.environ.get("BIOINTEL_NETWORK_RETRIES", "2"))
    return InternetPolicy(
        enabled=enabled("BIOINTEL_INTERNET_ENABLED", True),
        allow_public_https=enabled("BIOINTEL_ALLOW_PUBLIC_HTTPS", True),
        official_hosts_only=enabled("BIOINTEL_OFFICIAL_HOSTS_ONLY", False),
        resolve_dns=enabled("BIOINTEL_RESOLVE_DNS", True),
        max_download_bytes=max(1, max_mb) * 1024 * 1024,
        timeout_seconds=max(1.0, timeout),
        retries=max(0, retries),
    )


def _validate_ip(value: str) -> None:
    address = ipaddress.ip_address(value)
    if not address.is_global:
        raise NetworkPolicyError(
            "Private, loopback, link-local, reserved and local network addresses are blocked."
        )


from functools import lru_cache


@lru_cache(maxsize=512)
def _validate_dns(hostname: str) -> None:

    try:
        results = socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise NetworkPolicyError(
            f"Could not resolve the remote hostname: {hostname}. Check internet/DNS access."
        ) from exc
    addresses = {item[4][0] for item in results}
    if not addresses:
        raise NetworkPolicyError(f"No public address was resolved for {hostname}.")
    for address in addresses:
        _validate_ip(address)


def validate_public_https_url(
    url: str,
    *,
    policy: InternetPolicy | None = None,
    allowed_hosts: set[str] | frozenset[str] | None = None,
    resolve_dns: bool | None = None,
) -> str:
    active = policy or internet_policy_from_environment()
    if not active.enabled:
        raise NetworkPolicyError(
            "Internet access is disabled. Set BIOINTEL_INTERNET_ENABLED=1 or use the internet launcher."
        )

    parsed = urlparse(url.strip())
    if parsed.scheme.lower() != "https":
        raise NetworkPolicyError("Only HTTPS internet downloads are allowed.")
    if parsed.username or parsed.password:
        raise NetworkPolicyError("URLs containing usernames or passwords are blocked.")
    if not parsed.hostname:
        raise NetworkPolicyError("The URL does not contain a valid hostname.")
    if parsed.port not in (None, 443):
        raise NetworkPolicyError("Only the standard HTTPS port 443 is allowed.")

    hostname = parsed.hostname.lower().rstrip(".")
    approved = allowed_hosts or OFFICIAL_SCIENTIFIC_HOSTS
    if active.official_hosts_only and hostname not in approved:
        raise NetworkPolicyError(
            f"The host {hostname} is not in the approved scientific-host list."
        )
    if not active.allow_public_https and hostname not in approved:
        raise NetworkPolicyError(
            f"Public HTTPS downloads are disabled for non-approved host {hostname}."
        )

    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        should_resolve = active.resolve_dns if resolve_dns is None else resolve_dns
        if should_resolve:
            _validate_dns(hostname)
    else:
        _validate_ip(hostname)

    return parsed.geturl()
