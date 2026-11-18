from __future__ import annotations

import ipaddress
import json
import re
from dataclasses import dataclass
from html import unescape
from typing import Any, Callable
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree

MAX_RESPONSE_BYTES = 5 * 1024 * 1024
USER_AGENT = "BioIntelAI/15.6.0 SciencePulse (+local-first; metadata-only)"

class AdapterError(RuntimeError):
    pass

def _validate_url(url: str) -> str:
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").strip().lower().rstrip(".")
    if parsed.scheme not in {"http", "https"} or not hostname or parsed.username or parsed.password:
        raise AdapterError("Source URL must be an absolute HTTP(S) URL without embedded credentials.")
    local_hosts = {"127.0.0.1", "localhost", "::1"}
    if parsed.scheme != "https" and hostname not in local_hosts:
        raise AdapterError("Remote Science Pulse sources require HTTPS.")
    if hostname in {"169.254.169.254", "metadata.google.internal", "metadata.azure.internal"} or hostname.endswith((".local", ".localhost", ".internal")) and hostname not in local_hosts:
        raise AdapterError("Private, link-local and metadata service hosts are blocked.")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address and hostname not in local_hosts and (address.is_private or address.is_loopback or address.is_link_local or address.is_multicast or address.is_reserved or address.is_unspecified):
        raise AdapterError("Private or non-routable source addresses are blocked.")
    if parsed.port is not None and parsed.port not in {80, 443, 8000, 8080, 8443}:
        raise AdapterError("Source URL uses a disallowed network port.")
    return url

def _read(url: str, *, timeout: float = 10.0, opener: Callable[..., Any] = urlopen) -> tuple[bytes, str]:
    request = Request(_validate_url(url), headers={"User-Agent": USER_AGENT, "Accept": "application/json, application/rss+xml, application/atom+xml, application/xml, text/xml"})
    try:
        with opener(request, timeout=timeout) as response:
            final_url = getattr(response, "geturl", lambda: url)()
            _validate_url(final_url)
            declared = int(response.headers.get("Content-Length", "0") or 0)
            if declared > MAX_RESPONSE_BYTES:
                raise AdapterError("Source response exceeds the 5 MiB metadata limit.")
            payload = response.read(MAX_RESPONSE_BYTES + 1)
            if len(payload) > MAX_RESPONSE_BYTES:
                raise AdapterError("Source response exceeds the 5 MiB metadata limit.")
            return payload, response.headers.get("Content-Type", "")
    except AdapterError:
        raise
    except Exception as exc:
        raise AdapterError(f"External source unavailable: {exc}") from exc

def _date(parts: Any) -> str:
    try:
        values = parts[0]
        return "-".join(f"{int(value):02d}" if index else f"{int(value):04d}" for index, value in enumerate(values[:3]))
    except (IndexError, TypeError, ValueError):
        return ""

@dataclass(frozen=True)
class CrossrefAdapter:
    base_url: str
    opener: Callable[..., Any] = urlopen

    def fetch(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 100))
        endpoint = self.base_url.rstrip("/")
        if not endpoint.endswith("/works"):
            endpoint += "/works"
        url = endpoint + "?" + urlencode({"query": query, "rows": safe_limit, "select": "DOI,title,author,URL,published,type,abstract,relation,update-to"})
        payload, _ = _read(url, opener=self.opener)
        try:
            items = json.loads(payload.decode("utf-8"))["message"]["items"]
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise AdapterError("Crossref returned invalid JSON metadata.") from exc
        records: list[dict[str, Any]] = []
        for item in items:
            doi = str(item.get("DOI", "")).strip().lower()
            title_values = item.get("title") or []
            title = str(title_values[0] if title_values else "").strip()
            source_url = str(item.get("URL") or (f"https://doi.org/{doi}" if doi else "")).strip()
            if not doi or not title or not source_url:
                continue
            authors = [" ".join(filter(None, (str(a.get("given", "")).strip(), str(a.get("family", "")).strip()))).strip() for a in item.get("author", [])]
            abstract = re.sub(r"<[^>]+>", " ", str(item.get("abstract", "")))
            records.append({"doi": doi, "title": title, "authors": [a for a in authors if a], "source_url": source_url, "published_at": _date((item.get("published") or {}).get("date-parts")), "abstract_excerpt": " ".join(unescape(abstract).split())[:2000], "preprint": str(item.get("type", "")).lower() in {"posted-content", "preprint"}, "retracted": bool(item.get("update-to")), "provider": "Crossref"})
        return records

@dataclass(frozen=True)
class RssNewsAdapter:
    feed_url: str
    opener: Callable[..., Any] = urlopen

    def fetch(self, limit: int = 50) -> list[dict[str, Any]]:
        payload, _ = _read(self.feed_url, opener=self.opener)
        try:
            root = ElementTree.fromstring(payload)
        except ElementTree.ParseError as exc:
            raise AdapterError("News source returned invalid RSS/Atom XML.") from exc
        records: list[dict[str, Any]] = []
        entries = root.findall(".//item") or root.findall(".//{*}entry")
        for entry in entries[:max(1, min(int(limit), 100))]:
            def value(*names: str) -> str:
                for name in names:
                    node = entry.find(name)
                    if node is None:
                        node = entry.find(f"{{*}}{name}")
                    if node is not None:
                        if name == "link" and node.attrib.get("href"):
                            return node.attrib["href"].strip()
                        if node.text:
                            return node.text.strip()
                return ""
            title = unescape(value("title"));link = value("link");external_id = value("guid", "id") or link
            if not title or not link or not external_id:
                continue
            summary = re.sub(r"<[^>]+>", " ", value("description", "summary", "content"))
            records.append({"external_id": external_id[:500], "title": title[:500], "summary_excerpt": " ".join(unescape(summary).split())[:1000], "source_url": link, "published_at": value("pubDate", "published", "updated"), "topics": [node.text.strip() for node in entry.findall("category") + entry.findall("{*}category") if node.text and node.text.strip()]})
        return records


