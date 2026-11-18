from __future__ import annotations

import html
import ipaddress
import os
import re
import socket
import ssl
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlsplit
from urllib.error import HTTPError, URLError
from urllib.request import (
    HTTPRedirectHandler,
    HTTPSHandler,
    ProxyHandler,
    Request,
    build_opener,
)
from xml.etree import ElementTree


MAX_RESPONSE_BYTES = 5 * 1024 * 1024
ALLOWED_MIME_TYPES = {
    "application/atom+xml",
    "application/json",
    "application/xml",
    "text/json",
    "text/xml",
    "application/rss+xml",
}


class PulseSecurityError(ValueError):
    pass


class _LimitedRedirectHandler(HTTPRedirectHandler):
    max_redirections = 4
    max_repeats = 2

    def __init__(
        self,
        *,
        approved_hosts: set[str] | None,
        resolver: Callable[..., list[tuple]],
    ) -> None:
        super().__init__()
        self.approved_hosts = approved_hosts
        self.resolver = resolver

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Validate before urllib follows the redirect. Validating only the final
        # URL is too late because a hostile feed could already have reached a
        # loopback/private target.
        validate_remote_url(
            newurl,
            approved_hosts=self.approved_hosts,
            resolver=self.resolver,
        )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _is_public_ip(value: str) -> bool:
    address = ipaddress.ip_address(value.split("%", 1)[0])
    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


def validate_remote_url(
    url: str,
    *,
    approved_hosts: set[str] | None = None,
    resolver: Callable[..., list[tuple]] = socket.getaddrinfo,
) -> str:
    parsed = urlsplit(str(url or "").strip())
    if parsed.scheme.lower() != "https":
        raise PulseSecurityError("Only HTTPS provider URLs are allowed.")
    if parsed.username or parsed.password:
        raise PulseSecurityError("Credentials embedded in provider URLs are forbidden.")
    if not parsed.hostname:
        raise PulseSecurityError("Provider URL is missing a hostname.")
    host = parsed.hostname.rstrip(".").casefold()
    if parsed.port not in (None, 443):
        raise PulseSecurityError("Only the standard HTTPS port is allowed.")
    if host in {"localhost", "localhost.localdomain"} or host.endswith((".local", ".internal", ".localhost")):
        raise PulseSecurityError("Local or internal provider hosts are forbidden.")
    if approved_hosts and host not in {item.casefold() for item in approved_hosts}:
        raise PulseSecurityError("Provider host is not in the approved registry.")
    try:
        ipaddress.ip_address(host)
        addresses = [host]
    except ValueError:
        try:
            addresses = list(
                {
                    result[4][0]
                    for result in resolver(host, 443, type=socket.SOCK_STREAM)
                    if result and len(result) > 4 and result[4]
                }
            )
        except OSError as exc:
            raise PulseSecurityError(f"Provider DNS resolution failed: {host}") from exc
    if not addresses or any(not _is_public_ip(address) for address in addresses):
        raise PulseSecurityError("Provider host resolves to a non-public address.")
    return parsed.geturl()


def clean_text(value: object, *, limit: int = 20_000) -> str:
    text = str(value or "")
    text = re.sub(r"(?is)<(script|style|iframe|object|embed)[^>]*>.*?</\1>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", text)
    return re.sub(r"\s+", " ", text).strip()[:limit]


def safe_xml(data: bytes) -> ElementTree.Element:
    prefix = data[:16_384].decode("utf-8", errors="ignore").casefold()
    if "<!doctype" in prefix or "<!entity" in prefix:
        raise PulseSecurityError("DTD and entity declarations are forbidden.")
    try:
        return ElementTree.fromstring(data)
    except ElementTree.ParseError as exc:
        raise PulseSecurityError("Provider returned malformed XML.") from exc


@dataclass(frozen=True, slots=True)
class HttpPayload:
    data: bytes
    final_url: str
    content_type: str
    status: int
    network_route: str = "system"


class SafeHttpClient:
    """Small injectable client used only by the background worker."""

    def __init__(
        self,
        *,
        resolver: Callable[..., list[tuple]] = socket.getaddrinfo,
        transport: Callable[[str, dict[str, str], float], HttpPayload] | None = None,
        max_bytes: int = MAX_RESPONSE_BYTES,
        timeout: float = 20.0,
        proxy_mode: str | None = None,
    ) -> None:
        self.resolver = resolver
        self.transport = transport
        self.max_bytes = max(1024, min(int(max_bytes), MAX_RESPONSE_BYTES))
        self.timeout = max(1.0, min(float(timeout), 60.0))
        self.proxy_mode = (
            proxy_mode
            or os.environ.get("BIOINTEL_SCIENCE_PULSE_PROXY_MODE", "auto")
        ).strip().casefold()
        if self.proxy_mode not in {"auto", "system", "direct"}:
            raise PulseSecurityError(
                "BIOINTEL_SCIENCE_PULSE_PROXY_MODE must be auto, system, or direct."
            )

    def _open(
        self,
        request: Request,
        context: ssl.SSLContext,
        approved_hosts: set[str] | None,
        *,
        direct: bool,
    ):
        handlers: list[object] = [
            HTTPSHandler(context=context),
            _LimitedRedirectHandler(
                approved_hosts=approved_hosts,
                resolver=self.resolver,
            ),
        ]
        if direct:
            handlers.insert(0, ProxyHandler({}))
        opener = build_opener(*handlers)
        return opener.open(request, timeout=self.timeout)


    def get(
        self,
        url: str,
        *,
        approved_hosts: set[str] | None = None,
        accept: str = "application/json, application/xml, text/xml",
    ) -> HttpPayload:
        safe_url = validate_remote_url(url, approved_hosts=approved_hosts, resolver=self.resolver)
        headers = {
            "Accept": accept,
            "User-Agent": "BioIntel-Science-Pulse/1.0 (local-first metadata client)",
        }
        if self.transport:
            payload = self.transport(safe_url, headers, self.timeout)
            if payload.network_route == "system":
                payload = HttpPayload(
                    payload.data,
                    payload.final_url,
                    payload.content_type,
                    payload.status,
                    "injected_test_transport",
                )
        else:
            request = Request(safe_url, headers=headers, method="GET")
            context = ssl.create_default_context()
            route = "direct" if self.proxy_mode == "direct" else "system_proxy"
            try:
                response = self._open(
                    request,
                    context,
                    approved_hosts,
                    direct=self.proxy_mode == "direct",
                )
            except HTTPError:
                raise
            except URLError:
                if self.proxy_mode != "auto":
                    raise
                response = self._open(
                    Request(safe_url, headers=headers, method="GET"),
                    context,
                    approved_hosts,
                    direct=True,
                )
                route = "direct_fallback"
            with response:
                content_type = response.headers.get_content_type().casefold()
                data = response.read(self.max_bytes + 1)
                payload = HttpPayload(
                    data=data,
                    final_url=response.geturl(),
                    content_type=content_type,
                    status=int(getattr(response, "status", 200)),
                    network_route=route,
                )
        validate_remote_url(payload.final_url, approved_hosts=approved_hosts, resolver=self.resolver)
        mime = payload.content_type.partition(";")[0].strip().casefold()
        if mime not in ALLOWED_MIME_TYPES:
            raise PulseSecurityError(f"Provider MIME type is not allowed: {mime or 'missing'}")
        if len(payload.data) > self.max_bytes:
            raise PulseSecurityError("Provider response exceeded the configured size limit.")
        if payload.status < 200 or payload.status >= 300:
            raise PulseSecurityError(f"Provider returned HTTP {payload.status}.")
        return HttpPayload(
            payload.data,
            payload.final_url,
            mime,
            payload.status,
            payload.network_route,
        )
