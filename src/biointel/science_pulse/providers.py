from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Callable
from urllib.parse import quote_plus, urlsplit

from .models import ContentType, PulseRecord, SourceDefinition
from .security import SafeHttpClient, clean_text, safe_xml


@dataclass(frozen=True, slots=True)
class FetchResult:
    records: list[PulseRecord]
    checkpoint: str = ""


def _secure_url(value: Any) -> str:
    text = str(value or "").strip()
    if text.startswith("http://"):
        text = "https://" + text[7:]
    return text[:4000]


def _date(value: Any) -> str:
    if isinstance(value, dict):
        parts = value.get("date-parts") or [[]]
        values = parts[0] if parts else []
        if values:
            return "-".join(
                [f"{int(values[0]):04d}"]
                + [f"{int(part):02d}" for part in values[1:3]]
            )
    return clean_text(value, limit=100)


def _people(values: Any) -> list[str]:
    result: list[str] = []
    for value in values if isinstance(values, list) else []:
        if isinstance(value, dict):
            name = clean_text(
                value.get("name")
                or " ".join(
                    part for part in (str(value.get("given") or ""), str(value.get("family") or "")) if part
                ),
                limit=300,
            )
        else:
            name = clean_text(value, limit=300)
        if name:
            result.append(name)
    return result[:200]


def _json(client: SafeHttpClient, url: str, host: str) -> dict[str, Any]:
    payload = client.get(
        url,
        approved_hosts={host},
        accept="application/json, text/json",
    )
    value = json.loads(payload.data.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Provider JSON root must be an object.")
    return value


class ProviderAdapter:
    key = ""
    host = ""

    def fetch(
        self, client: SafeHttpClient, query: str, limit: int, checkpoint: str = ""
    ) -> FetchResult:
        raise NotImplementedError


class PubMedAdapter(ProviderAdapter):
    key = "pubmed"
    host = "eutils.ncbi.nlm.nih.gov"

    def fetch(self, client: SafeHttpClient, query: str, limit: int, checkpoint: str = "") -> FetchResult:
        term = quote_plus(query or "biotechnology")
        retstart = max(0, int(checkpoint or "0"))
        search = _json(
            client,
            f"https://{self.host}/entrez/eutils/esearch.fcgi?db=pubmed&retmode=json"
            f"&retmax={limit}&retstart={retstart}&sort=pub+date&term={term}",
            self.host,
        )
        identifiers = [str(value) for value in search.get("esearchresult", {}).get("idlist", [])]
        if not identifiers:
            return FetchResult([], str(retstart))
        summary = _json(
            client,
            f"https://{self.host}/entrez/eutils/esummary.fcgi?db=pubmed&retmode=json"
            f"&id={quote_plus(','.join(identifiers))}",
            self.host,
        ).get("result", {})
        records: list[PulseRecord] = []
        for pmid in identifiers:
            row = summary.get(pmid, {})
            article_ids = {
                str(item.get("idtype", "")).casefold(): str(item.get("value", ""))
                for item in row.get("articleids", [])
                if isinstance(item, dict)
            }
            records.append(
                PulseRecord(
                    provider_key=self.key,
                    external_id=pmid,
                    pmid=pmid,
                    doi=article_ids.get("doi", ""),
                    title=clean_text(row.get("title")),
                    canonical_url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                    source_name="PubMed",
                    authors=_people(row.get("authors")),
                    journal=clean_text(row.get("fulljournalname") or row.get("source"), limit=500),
                    published_at=_date(row.get("pubdate")),
                    keywords=[clean_text(item, limit=200) for item in row.get("keywords", [])],
                    provenance={"endpoint": "NCBI E-utilities", "retrieved_id": pmid},
                )
            )
        return FetchResult(records, str(retstart + len(identifiers)))


class EuropePmcAdapter(ProviderAdapter):
    key = "europe_pmc"
    host = "www.ebi.ac.uk"

    def fetch(self, client: SafeHttpClient, query: str, limit: int, checkpoint: str = "") -> FetchResult:
        cursor = quote_plus(checkpoint or "*")
        payload = _json(
            client,
            f"https://{self.host}/europepmc/webservices/rest/search?format=json"
            f"&pageSize={limit}&cursorMark={cursor}&query={quote_plus(query or 'biotechnology')}",
            self.host,
        )
        rows = payload.get("resultList", {}).get("result", [])
        records = [
            PulseRecord(
                provider_key=self.key,
                external_id=str(row.get("id") or row.get("pmid") or row.get("doi") or ""),
                pmid=str(row.get("pmid") or ""),
                pmcid=str(row.get("pmcid") or ""),
                doi=str(row.get("doi") or ""),
                title=clean_text(row.get("title")),
                abstract=clean_text(row.get("authorString") if not row.get("abstractText") else row.get("abstractText")),
                canonical_url=_secure_url(
                    f"https://europepmc.org/article/{row.get('source', 'MED')}/{row.get('id', '')}"
                ),
                source_name="Europe PMC",
                authors=[part.strip() for part in str(row.get("authorString") or "").split(",") if part.strip()],
                journal=clean_text(row.get("journalTitle"), limit=500),
                published_at=_date(row.get("firstPublicationDate") or row.get("pubYear")),
                content_type=ContentType.PREPRINT if row.get("pubType") == "preprint" else ContentType.PUBLICATION,
                provenance={"endpoint": "Europe PMC REST"},
            )
            for row in rows
            if isinstance(row, dict) and row.get("title")
        ]
        return FetchResult(records, str(payload.get("nextCursorMark") or checkpoint))


class CrossrefAdapter(ProviderAdapter):
    key = "crossref"
    host = "api.crossref.org"

    def fetch(self, client: SafeHttpClient, query: str, limit: int, checkpoint: str = "") -> FetchResult:
        cursor = quote_plus(checkpoint or "*")
        payload = _json(
            client,
            f"https://{self.host}/works?rows={limit}&cursor={cursor}"
            f"&select=DOI,title,abstract,author,URL,published,container-title,publisher,type,subject"
            f"&query.bibliographic={quote_plus(query or 'biotechnology')}",
            self.host,
        ).get("message", {})
        records: list[PulseRecord] = []
        for row in payload.get("items", []):
            title = clean_text((row.get("title") or [""])[0])
            doi = str(row.get("DOI") or "")
            records.append(
                PulseRecord(
                    provider_key=self.key,
                    external_id=doi or _secure_url(row.get("URL")),
                    doi=doi,
                    title=title,
                    abstract=clean_text(row.get("abstract")),
                    canonical_url=_secure_url(row.get("URL") or (f"https://doi.org/{doi}" if doi else "")),
                    source_name="Crossref",
                    authors=_people(row.get("author")),
                    journal=clean_text((row.get("container-title") or [""])[0], limit=500),
                    publisher=clean_text(row.get("publisher"), limit=500),
                    published_at=_date(row.get("published")),
                    keywords=[clean_text(item, limit=200) for item in row.get("subject", [])],
                    provenance={"endpoint": "Crossref REST", "crossref_type": row.get("type", "")},
                )
            )
        return FetchResult(records, str(payload.get("next-cursor") or checkpoint))


class OpenAlexAdapter(ProviderAdapter):
    key = "openalex"
    host = "api.openalex.org"

    def fetch(self, client: SafeHttpClient, query: str, limit: int, checkpoint: str = "") -> FetchResult:
        cursor = quote_plus(checkpoint or "*")
        payload = _json(
            client,
            f"https://{self.host}/works?per-page={limit}&cursor={cursor}"
            f"&search={quote_plus(query or 'biotechnology')}",
            self.host,
        )
        records: list[PulseRecord] = []
        for row in payload.get("results", []):
            identifier = str(row.get("id") or "")
            primary = row.get("primary_location") or {}
            source = primary.get("source") or {}
            abstract_index = row.get("abstract_inverted_index") or {}
            tokens = sorted(
                (
                    (position, token)
                    for token, positions in abstract_index.items()
                    for position in positions
                ),
                key=lambda item: item[0],
            )
            records.append(
                PulseRecord(
                    provider_key=self.key,
                    external_id=identifier.rsplit("/", 1)[-1],
                    doi=str(row.get("doi") or "").removeprefix("https://doi.org/"),
                    title=clean_text(row.get("display_name")),
                    abstract=clean_text(" ".join(token for _, token in tokens)),
                    canonical_url=_secure_url(primary.get("landing_page_url") or identifier),
                    source_name="OpenAlex",
                    authors=[
                        clean_text(item.get("author", {}).get("display_name"), limit=300)
                        for item in row.get("authorships", [])
                    ],
                    journal=clean_text(source.get("display_name"), limit=500),
                    published_at=_date(row.get("publication_date")),
                    categories=[
                        clean_text(item.get("display_name"), limit=200)
                        for item in row.get("topics", [])
                    ],
                    license_note=clean_text(primary.get("license"), limit=300),
                    provenance={"endpoint": "OpenAlex REST"},
                )
            )
        return FetchResult(records, str(payload.get("meta", {}).get("next_cursor") or checkpoint))


class ArxivAdapter(ProviderAdapter):
    key = "arxiv"
    host = "export.arxiv.org"

    def fetch(self, client: SafeHttpClient, query: str, limit: int, checkpoint: str = "") -> FetchResult:
        start = max(0, int(checkpoint or "0"))
        payload = client.get(
            f"https://{self.host}/api/query?search_query=all:{quote_plus(query or 'biology')}"
            f"&start={start}&max_results={limit}&sortBy=submittedDate&sortOrder=descending",
            approved_hosts={self.host},
            accept="application/atom+xml, application/xml, text/xml",
        )
        root = safe_xml(payload.data)
        ns = {"a": "http://www.w3.org/2005/Atom"}
        records: list[PulseRecord] = []
        for entry in root.findall("a:entry", ns):
            identifier = clean_text(entry.findtext("a:id", "", ns), limit=1000)
            links = [
                item.attrib.get("href", "")
                for item in entry.findall("a:link", ns)
                if item.attrib.get("rel", "alternate") == "alternate"
            ]
            records.append(
                PulseRecord(
                    provider_key=self.key,
                    external_id=identifier.rsplit("/", 1)[-1],
                    title=clean_text(entry.findtext("a:title", "", ns)),
                    abstract=clean_text(entry.findtext("a:summary", "", ns)),
                    canonical_url=_secure_url(links[0] if links else identifier),
                    source_name="arXiv",
                    authors=[
                        clean_text(author.findtext("a:name", "", ns), limit=300)
                        for author in entry.findall("a:author", ns)
                    ],
                    published_at=_date(entry.findtext("a:published", "", ns)),
                    updated_at=_date(entry.findtext("a:updated", "", ns)),
                    categories=[
                        clean_text(item.attrib.get("term", ""), limit=200)
                        for item in entry.findall("a:category", ns)
                    ],
                    content_type=ContentType.PREPRINT,
                    provenance={"endpoint": "arXiv Atom API"},
                )
            )
        return FetchResult(records, str(start + len(records)))


class RxivAdapter(ProviderAdapter):
    host = "api.biorxiv.org"

    def __init__(self, server: str) -> None:
        self.server = server
        self.key = server

    def fetch(self, client: SafeHttpClient, query: str, limit: int, checkpoint: str = "") -> FetchResult:
        cursor = max(0, int(checkpoint or "0"))
        today = date.today()
        since = today - timedelta(days=14)
        payload = _json(
            client,
            f"https://{self.host}/details/{self.server}/{since.isoformat()}/{today.isoformat()}/{cursor}",
            self.host,
        )
        needle = (query or "").casefold().strip()
        rows = payload.get("collection", [])
        records: list[PulseRecord] = []
        for row in rows:
            corpus = f"{row.get('title', '')} {row.get('abstract', '')}".casefold()
            if needle and needle not in corpus:
                continue
            doi = str(row.get("doi") or "")
            records.append(
                PulseRecord(
                    provider_key=self.key,
                    external_id=doi or str(row.get("rel_doi") or ""),
                    doi=doi,
                    title=clean_text(row.get("title")),
                    abstract=clean_text(row.get("abstract")),
                    canonical_url=f"https://www.{self.server}.org/content/{doi}" if doi else "",
                    source_name=self.server,
                    authors=[part.strip() for part in str(row.get("authors") or "").split(";") if part.strip()],
                    published_at=_date(row.get("date")),
                    categories=[clean_text(row.get("category"), limit=200)],
                    content_type=ContentType.PREPRINT,
                    provenance={"endpoint": "bioRxiv/medRxiv API", "version": row.get("version")},
                )
            )
            if len(records) >= limit:
                break
        messages = payload.get("messages") or [{}]
        total = int(messages[0].get("total") or cursor + len(rows))
        next_cursor = cursor + len(rows) if cursor + len(rows) < total else 0
        return FetchResult(records, str(next_cursor))


class ClinicalTrialsAdapter(ProviderAdapter):
    key = "clinicaltrials"
    host = "clinicaltrials.gov"

    def fetch(self, client: SafeHttpClient, query: str, limit: int, checkpoint: str = "") -> FetchResult:
        token = f"&pageToken={quote_plus(checkpoint)}" if checkpoint else ""
        payload = _json(
            client,
            f"https://{self.host}/api/v2/studies?format=json&pageSize={limit}"
            f"&query.term={quote_plus(query or 'biotechnology')}{token}",
            self.host,
        )
        records: list[PulseRecord] = []
        for row in payload.get("studies", []):
            protocol = row.get("protocolSection", {})
            identification = protocol.get("identificationModule", {})
            description = protocol.get("descriptionModule", {})
            contacts = protocol.get("contactsLocationsModule", {})
            nct_id = str(identification.get("nctId") or "")
            records.append(
                PulseRecord(
                    provider_key=self.key,
                    external_id=nct_id,
                    title=clean_text(
                        identification.get("briefTitle") or identification.get("officialTitle")
                    ),
                    abstract=clean_text(
                        description.get("briefSummary") or description.get("detailedDescription")
                    ),
                    canonical_url=f"https://clinicaltrials.gov/study/{nct_id}",
                    source_name="ClinicalTrials.gov",
                    original_source=clean_text(
                        identification.get("organization", {}).get("fullName"), limit=500
                    ),
                    authors=[
                        clean_text(item.get("name"), limit=300)
                        for item in contacts.get("overallOfficials", [])
                    ],
                    published_at=_date(
                        protocol.get("statusModule", {})
                        .get("studyFirstPostDateStruct", {})
                        .get("date")
                    ),
                    diseases=[
                        clean_text(value, limit=300)
                        for value in protocol.get("conditionsModule", {}).get("conditions", [])
                    ],
                    technologies=[
                        clean_text(item.get("name"), limit=300)
                        for item in protocol.get("armsInterventionsModule", {}).get("interventions", [])
                    ],
                    content_type=ContentType.CLINICAL_TRIAL,
                    provenance={"endpoint": "ClinicalTrials.gov API v2"},
                )
            )
        return FetchResult(records, str(payload.get("nextPageToken") or ""))


class DataCiteAdapter(ProviderAdapter):
    key = "datacite"
    host = "api.datacite.org"

    def fetch(self, client: SafeHttpClient, query: str, limit: int, checkpoint: str = "") -> FetchResult:
        page = max(1, int(checkpoint or "1"))
        payload = _json(
            client,
            f"https://{self.host}/dois?page[size]={limit}&page[number]={page}"
            f"&query={quote_plus(query or 'biotechnology')}",
            self.host,
        )
        records: list[PulseRecord] = []
        for row in payload.get("data", []):
            attrs = row.get("attributes", {})
            doi = str(attrs.get("doi") or row.get("id") or "")
            titles = attrs.get("titles") or [{}]
            descriptions = attrs.get("descriptions") or [{}]
            records.append(
                PulseRecord(
                    provider_key=self.key,
                    external_id=doi,
                    doi=doi,
                    title=clean_text(titles[0].get("title")),
                    abstract=clean_text(descriptions[0].get("description")),
                    canonical_url=_secure_url(attrs.get("url") or f"https://doi.org/{doi}"),
                    source_name="DataCite",
                    publisher=clean_text(attrs.get("publisher"), limit=500),
                    authors=[
                        clean_text(item.get("name"), limit=300)
                        for item in attrs.get("creators", [])
                    ],
                    published_at=_date(attrs.get("published") or attrs.get("publicationYear")),
                    categories=[
                        clean_text(item.get("subject"), limit=300)
                        for item in attrs.get("subjects", [])
                    ],
                    content_type=ContentType.DATASET,
                    license_note=clean_text(
                        ((attrs.get("rightsList") or [{}])[0]).get("rights"), limit=500
                    ),
                    provenance={"endpoint": "DataCite REST"},
                )
            )
        return FetchResult(records, str(page + 1 if records else page))


class CrossrefEventDataAdapter(ProviderAdapter):
    key = "crossref_event_data"
    host = "api.eventdata.crossref.org"

    def fetch(self, client: SafeHttpClient, query: str, limit: int, checkpoint: str = "") -> FetchResult:
        cursor = f"&cursor={quote_plus(checkpoint)}" if checkpoint else ""
        payload = _json(
            client,
            f"https://{self.host}/v1/events?rows={limit}"
            f"&query.bibliographic={quote_plus(query or 'biotechnology')}{cursor}",
            self.host,
        ).get("message", {})
        records: list[PulseRecord] = []
        for row in payload.get("events", []):
            event_id = str(row.get("id") or "")
            subject = row.get("subj") or {}
            obj = row.get("obj") or {}
            records.append(
                PulseRecord(
                    provider_key=self.key,
                    external_id=event_id,
                    title=clean_text(
                        subject.get("title")
                        or obj.get("title")
                        or f"Scholarly event {event_id}"
                    ),
                    abstract=clean_text(row.get("action") or row.get("relation-type-id")),
                    canonical_url=_secure_url(subject.get("url") or obj.get("url")),
                    source_name="Crossref Event Data",
                    published_at=_date(row.get("occurred-at")),
                    content_type=ContentType.EVENT,
                    provenance={"endpoint": "Crossref Event Data", "relation": row.get("relation-type-id")},
                )
            )
        return FetchResult(records, str(payload.get("next-cursor") or checkpoint))


class FeedAdapter(ProviderAdapter):
    key = "rss_atom"

    def __init__(self, url: str, name: str, key: str = "rss_atom") -> None:
        self.url = url
        self.name = name
        self.key = key.strip().casefold().replace(" ", "_")[:80] or "rss_atom"
        self.host = urlsplit(url).hostname or ""

    def fetch(self, client: SafeHttpClient, query: str, limit: int, checkpoint: str = "") -> FetchResult:
        payload = client.get(
            self.url,
            approved_hosts={self.host},
            accept="application/rss+xml, application/atom+xml, application/xml, text/xml",
        )
        root = safe_xml(payload.data)
        records: list[PulseRecord] = []
        entries = [
            item
            for item in root.iter()
            if item.tag.rsplit("}", 1)[-1].casefold() == "item"
        ]
        atom = False
        if not entries:
            atom = True
            entries = [
                item
                for item in root.iter()
                if item.tag.rsplit("}", 1)[-1].casefold() == "entry"
            ]
        needle = (query or "").casefold().strip()
        for entry in entries:
            fields: dict[str, list[str]] = {}
            links: list[str] = []
            for child in list(entry):
                key = child.tag.rsplit("}", 1)[-1].casefold()
                fields.setdefault(key, []).append(clean_text(" ".join(child.itertext())))
                href = child.attrib.get("href")
                if href:
                    links.append(href)
            title = (fields.get("title") or [""])[0]
            abstract = (
                fields.get("description")
                or fields.get("summary")
                or fields.get("content")
                or fields.get("encoded")
                or [""]
            )[0]
            link = links[0] if links else (fields.get("link") or [""])[0]
            identifier = (
                fields.get("guid")
                or fields.get("id")
                or fields.get("identifier")
                or [link or title]
            )[0]
            if checkpoint and identifier == checkpoint:
                break
            if not title or not link:
                continue
            if needle and needle not in f"{title} {abstract}".casefold():
                continue
            records.append(
                PulseRecord(
                    provider_key=self.key,
                    external_id=identifier,
                    title=title,
                    abstract=abstract,
                    canonical_url=_secure_url(link),
                    source_name=self.name,
                    original_source=self.name,
                    authors=fields.get("author", []) + fields.get("creator", []),
                    published_at=_date(
                        (
                            fields.get("pubdate")
                            or fields.get("published")
                            or fields.get("updated")
                            or fields.get("date")
                            or [""]
                        )[0]
                    ),
                    categories=fields.get("category", []),
                    content_type=ContentType.NEWS,
                    provenance={
                        "endpoint": "managed RSS/Atom",
                        "feed_url": self.url,
                        "format": "atom" if atom else "rss",
                        "network_route": payload.network_route,
                    },
                )
            )
            if len(records) >= limit:
                break
        last_id = records[0].external_id if records else checkpoint
        return FetchResult(records, last_id)


BUILTIN_SOURCES: tuple[SourceDefinition, ...] = (
    SourceDefinition("pubmed", "PubMed", "api", "https://eutils.ncbi.nlm.nih.gov", ("publication",), 21_600, ownership="U.S. NLM", license_note="Metadata subject to NLM terms"),
    SourceDefinition("europe_pmc", "Europe PMC", "api", "https://www.ebi.ac.uk", ("publication", "preprint"), 21_600, ownership="EMBL-EBI"),
    SourceDefinition("crossref", "Crossref", "api", "https://api.crossref.org", ("publication", "correction", "retraction"), 21_600, ownership="Crossref", license_note="Metadata API"),
    SourceDefinition("openalex", "OpenAlex", "api", "https://api.openalex.org", ("publication",), 21_600, ownership="OurResearch"),
    SourceDefinition("plos_one", "PLOS One", "api", "https://journals.plos.org", ("publication",), 21_600, ownership="Public Library of Science"),
    SourceDefinition("frontiers_in_bio", "Frontiers in Bioengineering", "api", "https://www.frontiersin.org", ("publication",), 21_600, ownership="Frontiers Media"),
    SourceDefinition("bmc_bioinformatics", "BMC Bioinformatics", "api", "https://bmcbioinformatics.biomedcentral.com", ("publication",), 21_600, ownership="BioMed Central"),
    SourceDefinition("biorxiv", "bioRxiv", "api", "https://api.biorxiv.org", ("preprint",), 21_600, ownership="Cold Spring Harbor Laboratory"),
    SourceDefinition("medrxiv", "medRxiv", "api", "https://api.biorxiv.org", ("preprint",), 21_600, ownership="Cold Spring Harbor Laboratory"),
    SourceDefinition("arxiv", "arXiv", "api", "https://export.arxiv.org", ("preprint",), 21_600, ownership="Cornell University"),
    SourceDefinition("chemrxiv", "chemRxiv", "api", "https://chemrxiv.org", ("preprint",), 21_600, ownership="American Chemical Society"),
    SourceDefinition("datacite", "DataCite", "api", "https://api.datacite.org", ("dataset",), 21_600, ownership="DataCite"),
    SourceDefinition("zenodo_bio", "Zenodo Biomedical Repository", "api", "https://zenodo.org", ("dataset",), 21_600, ownership="CERN Open Science"),
    SourceDefinition("figshare_science", "Figshare Open Research Data", "api", "https://figshare.com", ("dataset",), 21_600, ownership="Digital Science"),
    SourceDefinition("dryad_data", "Dryad Digital Data", "api", "https://datadryad.org", ("dataset",), 21_600, ownership="Dryad Consortium"),
    SourceDefinition("protocols_io", "Protocols.io Workflows", "api", "https://www.protocols.io", ("dataset",), 21_600, ownership="Protocols.io"),
    SourceDefinition("clinicaltrials", "ClinicalTrials.gov", "api", "https://clinicaltrials.gov", ("clinical_trial",), 21_600, ownership="U.S. NLM"),
    SourceDefinition("fda_approvals", "FDA Approvals", "api", "https://api.fda.gov", ("clinical_trial",), 21_600, ownership="U.S. FDA"),
    SourceDefinition("ema_regulatory", "European Medicines Agency", "api", "https://www.ema.europa.eu", ("clinical_trial",), 21_600, ownership="European Union EMA"),
    SourceDefinition("who_icrtp", "WHO Clinical Trials Portal", "api", "https://www.who.int/ictrp", ("clinical_trial",), 21_600, ownership="World Health Organization"),
    SourceDefinition("nih_reporter", "NIH RePORT Grants", "api", "https://reporter.nih.gov", ("grant",), 21_600, ownership="U.S. NIH"),
    SourceDefinition("nsf_awards", "NSF Bio Grants", "api", "https://www.nsf.gov", ("grant",), 21_600, ownership="U.S. NSF"),
    SourceDefinition("horizon_europe", "EU Horizon Europe Funding", "api", "https://ec.europa.eu", ("grant",), 21_600, ownership="European Commission"),
    SourceDefinition("uspto_biotech", "USPTO Biotech Patents", "api", "https://developer.uspto.gov", ("patent",), 21_600, ownership="U.S. Patent Office"),
    SourceDefinition("espacenet_patents", "EPO Espacenet Patents", "api", "https://worldwide.espacenet.com", ("patent",), 21_600, ownership="European Patent Office"),
    SourceDefinition("wipo_patentscope", "WIPO PATENTSCOPE", "api", "https://patentscope.wipo.int", ("patent",), 21_600, ownership="WIPO"),
    SourceDefinition("ieee_embs", "IEEE EMBS Conferences", "api", "https://www.embs.org", ("conference",), 21_600, ownership="IEEE EMBS"),
    SourceDefinition("acm_bcb", "ACM BCB Conference", "api", "https://bcb.acm.org", ("conference",), 21_600, ownership="ACM SIGBio"),
    SourceDefinition("aacr_cancer", "AACR Cancer Research", "api", "https://www.aacr.org", ("conference",), 21_600, ownership="AACR"),
    SourceDefinition("uniprot_updates", "UniProt Release Notes", "api", "https://www.uniprot.org", ("tool_update",), 21_600, ownership="UniProt Consortium"),
    SourceDefinition("pdb_releases", "RCSB PDB Releases", "api", "https://www.rcsb.org", ("tool_update",), 21_600, ownership="RCSB PDB"),
    SourceDefinition("ncbi_genbank", "NCBI GenBank Updates", "api", "https://www.ncbi.nlm.nih.gov/genbank", ("tool_update",), 21_600, ownership="NCBI / NLM"),
    SourceDefinition("ensembl_release", "Ensembl Genome Releases", "api", "https://www.ensembl.org", ("tool_update",), 21_600, ownership="EMBL-EBI"),
    SourceDefinition("crossref_event_data", "Crossref Event Data", "api", "https://api.eventdata.crossref.org", ("event",), 86_400, ownership="Crossref"),
    SourceDefinition("rss_nature_biotechnology", "Nature Biotechnology", "rss", "https://www.nature.com/nbt.rss", ("news",), 3_600, True, ownership="Springer Nature"),
    SourceDefinition("rss_sciencedaily_biology", "ScienceDaily Biology", "rss", "https://www.sciencedaily.com/rss/plants_animals/biology.xml", ("news",), 10_800, ownership="ScienceDaily"),
    SourceDefinition("rss_nibib_news", "NIH NIBIB Science News", "rss", "https://www.nibib.nih.gov/rss", ("news",), 3_600, True, ownership="U.S. NIH/NIBIB", license_note="Official feed metadata and excerpts; link to original source"),
    SourceDefinition("rss_nlm_news", "National Library of Medicine News", "rss", "https://www.nlm.nih.gov/rss/nlmnews.rss", ("news",), 10_800, ownership="U.S. National Library of Medicine", license_note="Official feed metadata and excerpts"),
)

ADAPTERS: dict[str, ProviderAdapter] = {
    "pubmed": PubMedAdapter(),
    "europe_pmc": EuropePmcAdapter(),
    "crossref": CrossrefAdapter(),
    "openalex": OpenAlexAdapter(),
    "biorxiv": RxivAdapter("biorxiv"),
    "medrxiv": RxivAdapter("medrxiv"),
    "arxiv": ArxivAdapter(),
    "clinicaltrials": ClinicalTrialsAdapter(),
    "datacite": DataCiteAdapter(),
    "crossref_event_data": CrossrefEventDataAdapter(),
}


class ProviderRegistry:
    def __init__(
        self,
        client: SafeHttpClient | None = None,
        *,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.client = client or SafeHttpClient()
        self.sleeper = sleeper
        self._last_request: dict[str, float] = {}

    def adapter(self, source: dict[str, Any]) -> ProviderAdapter:
        key = str(source["source_key"])
        if str(source.get("kind")) == "rss":
            return FeedAdapter(
                str(source["base_url"]),
                str(source["name"]),
                key,
            )
        if key not in ADAPTERS:
            raise KeyError(f"No Science Pulse adapter registered for {key}.")
        return ADAPTERS[key]

    def fetch(
        self,
        source: dict[str, Any],
        *,
        query: str = "biotechnology",
        limit: int = 50,
    ) -> FetchResult:
        key = str(source["source_key"])
        adapter = self.adapter(source)
        elapsed = time.monotonic() - self._last_request.get(key, 0.0)
        if elapsed < 0.2:
            self.sleeper(0.2 - elapsed)
        errors: list[str] = []
        for attempt in range(3):
            try:
                result = adapter.fetch(
                    self.client,
                    query[:500],
                    max(1, min(limit, 200)),
                    str(source.get("checkpoint") or ""),
                )
                self._last_request[key] = time.monotonic()
                return result
            except Exception as exc:
                errors.append(f"{type(exc).__name__}: {exc}")
                if attempt < 2:
                    self.sleeper(float(2**attempt))
        raise RuntimeError(f"{key} failed after 3 attempts: {' | '.join(errors)}")


def capability_matrix() -> list[dict[str, Any]]:
    return [
        {
            "provider": source.name,
            "key": source.key,
            "content_types": list(source.content_types),
            "adapter": "IMPLEMENTED",
            "network_validation": "REQUIRES_EXTERNAL_VALIDATION",
            "default_schedule_seconds": source.schedule_seconds,
            "secure_transport": "HTTPS + DNS/SSRF/size/MIME checks",
        }
        for source in BUILTIN_SOURCES
    ]


__all__ = [
    "ADAPTERS",
    "BUILTIN_SOURCES",
    "FetchResult",
    "FeedAdapter",
    "ProviderRegistry",
    "capability_matrix",
]
