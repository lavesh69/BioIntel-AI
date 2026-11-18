from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from datetime import date, timedelta
from html import unescape
from typing import Any, Callable
from xml.etree import ElementTree

USER_AGENT = "BioIntelAI/15.6 Phase15 SciencePulse"
MAX_BYTES = 5 * 1024 * 1024
PROVIDERS = {"pubmed", "europe_pmc", "crossref", "openalex", "arxiv", "biorxiv", "medrxiv"}


def _request(url: str, *, opener: Callable[..., Any] = urllib.request.urlopen) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json, application/xml, application/atom+xml"})
    with opener(request, timeout=15) as response:
        payload = response.read(MAX_BYTES + 1)
    if len(payload) > MAX_BYTES:
        raise RuntimeError("Provider response exceeded 5 MiB safety limit.")
    return payload


def _clean(value: Any, limit: int = 4000) -> str:
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    return " ".join(unescape(text).split())[:limit]


def _authors(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    result: list[str] = []
    for item in values:
        if isinstance(item, dict):
            name = item.get("name") or " ".join(filter(None, [str(item.get("given", "")), str(item.get("family", ""))]))
        else:
            name = str(item)
        if name.strip():
            result.append(name.strip())
    return result


def fetch_provider(provider: str, query: str, *, limit: int = 20, cursor: str = "", opener: Callable[..., Any] = urllib.request.urlopen) -> tuple[list[dict[str, Any]], str]:
    provider = str(provider).strip().lower()
    if provider not in PROVIDERS:
        raise ValueError("Unsupported Science Pulse provider.")
    query = str(query or "biotechnology").strip()
    limit = max(1, min(int(limit), 100))
    if provider == "crossref":
        url = "https://api.crossref.org/works?" + urllib.parse.urlencode({"query": query, "rows": limit, "cursor": cursor or "*", "cursor-max": limit})
        data = json.loads(_request(url, opener=opener).decode("utf-8"))
        message = data.get("message", {})
        rows = []
        for item in message.get("items", []):
            doi = str(item.get("DOI", "")).lower()
            title = _clean((item.get("title") or [""])[0], 800)
            if not title:
                continue
            rows.append({"external_id": doi or str(item.get("URL", "")), "doi": doi, "pmid": "", "title": title, "abstract_excerpt": _clean(item.get("abstract")), "authors": _authors(item.get("author")), "source_url": str(item.get("URL") or (f"https://doi.org/{doi}" if doi else "")), "published_at": "", "record_type": str(item.get("type") or "journal"), "metadata": item})
        return rows, str(message.get("next-cursor") or cursor)
    if provider == "europe_pmc":
        url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search?" + urllib.parse.urlencode({"query": query, "format": "json", "pageSize": limit, "cursorMark": cursor or "*"})
        data = json.loads(_request(url, opener=opener).decode("utf-8"))
        rows = []
        for item in data.get("resultList", {}).get("result", []):
            external = str(item.get("id") or item.get("pmid") or item.get("doi") or "")
            title = _clean(item.get("title"), 800)
            if not external or not title:
                continue
            rows.append({"external_id": external, "doi": str(item.get("doi") or "").lower(), "pmid": str(item.get("pmid") or ""), "title": title, "abstract_excerpt": _clean(item.get("abstractText")), "authors": [part.strip() for part in str(item.get("authorString") or "").split(",") if part.strip()], "source_url": f"https://europepmc.org/article/{item.get('source','MED')}/{external}", "published_at": str(item.get("firstPublicationDate") or item.get("pubYear") or ""), "record_type": "journal", "metadata": item})
        return rows, str(data.get("nextCursorMark") or cursor)
    if provider == "openalex":
        params = {"search": query, "per-page": limit}
        if cursor:
            params["cursor"] = cursor
        else:
            params["cursor"] = "*"
        data = json.loads(_request("https://api.openalex.org/works?" + urllib.parse.urlencode(params), opener=opener).decode("utf-8"))
        rows = []
        for item in data.get("results", []):
            external = str(item.get("id") or "").rsplit("/", 1)[-1]
            title = _clean(item.get("title"), 800)
            if not external or not title:
                continue
            authors = [str(x.get("author", {}).get("display_name", "")).strip() for x in item.get("authorships", [])]
            rows.append({"external_id": external, "doi": str(item.get("doi") or "").replace("https://doi.org/", "").lower(), "pmid": "", "title": title, "abstract_excerpt": "", "authors": [a for a in authors if a], "source_url": str(item.get("doi") or item.get("id") or ""), "published_at": str(item.get("publication_date") or ""), "record_type": str(item.get("type") or "journal"), "metadata": {"cited_by_count": item.get("cited_by_count"), "open_access": item.get("open_access"), "concepts": item.get("concepts", [])[:20]}})
        return rows, str(data.get("meta", {}).get("next_cursor") or cursor)
    if provider in {"biorxiv", "medrxiv"}:
        end_date = date.today()
        start_date = end_date - timedelta(days=90)
        offset = max(0, int(cursor or 0))
        url = (
            f"https://api.biorxiv.org/details/{provider}/{start_date.isoformat()}/{end_date.isoformat()}/{offset}/json"
        )
        data = json.loads(_request(url, opener=opener).decode("utf-8"))
        terms = [term for term in re.findall(r"[a-z0-9]+", query.casefold()) if len(term) > 2]
        rows = []
        collection = data.get("collection", []) if isinstance(data, dict) else []
        for item in collection:
            title = _clean(item.get("title"), 800)
            abstract = _clean(item.get("abstract"))
            haystack = f"{title} {abstract}".casefold()
            if terms and not all(term in haystack for term in terms):
                continue
            doi = str(item.get("doi") or "").strip().casefold()
            if not title or not doi:
                continue
            rows.append({
                "external_id": doi,
                "doi": doi,
                "pmid": "",
                "title": title,
                "abstract_excerpt": abstract,
                "authors": [part.strip() for part in str(item.get("authors") or "").split(";") if part.strip()],
                "source_url": f"https://www.{provider}.org/content/{doi}",
                "published_at": str(item.get("date") or ""),
                "record_type": "preprint",
                "metadata": {**item, "server": provider, "fixture": False},
            })
            if len(rows) >= limit:
                break
        return rows, str(offset + len(collection))
    if provider == "arxiv":
        url = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode({"search_query": f"all:{query}", "start": int(cursor or 0), "max_results": limit})
        root = ElementTree.fromstring(_request(url, opener=opener))
        ns = {"a": "http://www.w3.org/2005/Atom"}
        rows = []
        for entry in root.findall("a:entry", ns):
            external = _clean(entry.findtext("a:id", default="", namespaces=ns), 500).rsplit("/", 1)[-1]
            title = _clean(entry.findtext("a:title", default="", namespaces=ns), 800)
            if not external or not title:
                continue
            rows.append({"external_id": external, "doi": "", "pmid": "", "title": title, "abstract_excerpt": _clean(entry.findtext("a:summary", default="", namespaces=ns)), "authors": [_clean(node.findtext("a:name", default="", namespaces=ns), 200) for node in entry.findall("a:author", ns)], "source_url": f"https://arxiv.org/abs/{external}", "published_at": _clean(entry.findtext("a:published", default="", namespaces=ns), 100), "record_type": "preprint", "metadata": {"updated": _clean(entry.findtext("a:updated", default="", namespaces=ns), 100)}})
        return rows, str(int(cursor or 0) + len(rows))
    # pubmed
    search_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?" + urllib.parse.urlencode({"db": "pubmed", "term": query, "retmode": "json", "retmax": limit, "retstart": int(cursor or 0)})
    search = json.loads(_request(search_url, opener=opener).decode("utf-8"))
    ids = [str(value) for value in search.get("esearchresult", {}).get("idlist", [])]
    if not ids:
        return [], cursor
    summary_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?" + urllib.parse.urlencode({"db": "pubmed", "id": ",".join(ids), "retmode": "json"})
    summary = json.loads(_request(summary_url, opener=opener).decode("utf-8"))
    rows = []
    for pmid in ids:
        item = summary.get("result", {}).get(pmid, {})
        title = _clean(item.get("title"), 800)
        if not title:
            continue
        article_ids = {str(v.get("idtype")): str(v.get("value")) for v in item.get("articleids", []) if isinstance(v, dict)}
        rows.append({"external_id": pmid, "doi": article_ids.get("doi", "").lower(), "pmid": pmid, "title": title, "abstract_excerpt": "", "authors": _authors(item.get("authors")), "source_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/", "published_at": str(item.get("pubdate") or ""), "record_type": "journal", "metadata": item})
    return rows, str(int(cursor or 0) + len(ids))


