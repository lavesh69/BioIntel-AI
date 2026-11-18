from __future__ import annotations

from biointel.runtime_paths import runtime_database_path

import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote, urlencode

from biointel.connected.config import settings_from_environment
from biointel.connected.http import ConnectedHttpClient, ConnectedServiceError
from biointel.connected.models import (
    ConnectedRecord,
    ConnectionDiagnostic,
    ProviderSpec,
    QueryResult,
)
from biointel.connected.registry import record_health_check, record_query

PROVIDERS: dict[str, ProviderSpec] = {
    "ncbi": ProviderSpec(
        "ncbi", "NCBI Entrez", "https://eutils.ncbi.nlm.nih.gov/entrez/eutils", "eutils.ncbi.nlm.nih.gov",
        ("gene", "literature", "sequence", "variant", "expression study", "protein"),
        "Genes, PubMed, ClinVar, GEO, SRA, nucleotide and protein records.", optional_key_env="NCBI_API_KEY",
        documentation_url="https://www.ncbi.nlm.nih.gov/books/NBK25501/", requests_per_second=3,
    ),
    "pubchem": ProviderSpec(
        "pubchem", "PubChem", "https://pubchem.ncbi.nlm.nih.gov/rest/pug", "pubchem.ncbi.nlm.nih.gov",
        ("compound", "bioassay"), "Compound identity, descriptors and structure records.",
        documentation_url="https://pubchem.ncbi.nlm.nih.gov/docs/pug-rest", requests_per_second=4,
    ),
    "uniprot": ProviderSpec(
        "uniprot", "UniProt", "https://rest.uniprot.org", "rest.uniprot.org", ("protein",),
        "Protein sequence, function, taxonomy and annotation.",
        documentation_url="https://www.uniprot.org/help/api_queries", requests_per_second=3,
    ),
    "rcsb": ProviderSpec(
        "rcsb", "RCSB PDB", "https://data.rcsb.org/rest/v1", "data.rcsb.org", ("structure",),
        "Experimentally determined macromolecular structures.",
        documentation_url="https://search.rcsb.org/", requests_per_second=2,
    ),
    "chembl": ProviderSpec(
        "chembl", "ChEMBL", "https://www.ebi.ac.uk/chembl/api/data", "www.ebi.ac.uk",
        ("compound", "target", "bioactivity"), "Drug-like molecules, targets and bioactivity records.",
        documentation_url="https://www.ebi.ac.uk/chembl/api/data/docs", requests_per_second=3,
    ),
    "ensembl": ProviderSpec(
        "ensembl", "Ensembl", "https://rest.ensembl.org", "rest.ensembl.org",
        ("gene", "transcript", "variant", "comparative genomics"),
        "Gene, transcript, homology and variant annotation services.",
        documentation_url="https://rest.ensembl.org/", requests_per_second=5, supports_free_text=False,
    ),
    "clinicaltrials": ProviderSpec(
        "clinicaltrials", "ClinicalTrials.gov", "https://clinicaltrials.gov/api/v2", "clinicaltrials.gov",
        ("clinical trial",), "Structured clinical study registry records.",
        documentation_url="https://clinicaltrials.gov/data-api/api", requests_per_second=3,
    ),
    "reactome": ProviderSpec(
        "reactome", "Reactome", "https://reactome.org/ContentService", "reactome.org", ("pathway",),
        "Curated biological pathways and reactions.",
        documentation_url="https://reactome.org/dev/content-service", requests_per_second=3,
    ),
    "string": ProviderSpec(
        "string", "STRING", "https://string-db.org/api", "string-db.org", ("protein interaction", "protein"),
        "Protein association networks and interaction evidence.",
        documentation_url="https://string-db.org/help/api/", requests_per_second=2,
    ),
    "interpro": ProviderSpec(
        "interpro", "InterPro", "https://www.ebi.ac.uk/interpro/api", "www.ebi.ac.uk", ("protein domain", "protein"),
        "Protein families, domains and functional sites.",
        documentation_url="https://www.ebi.ac.uk/interpro/api/", requests_per_second=2,
    ),
    "europepmc": ProviderSpec(
        "europepmc", "Europe PMC", "https://www.ebi.ac.uk/europepmc/webservices/rest", "www.ebi.ac.uk",
        ("literature",), "Biomedical publications, citations and open-access metadata.",
        documentation_url="https://europepmc.org/RestfulWebService", requests_per_second=3,
    ),
}

ENTITY_PROVIDER_DEFAULTS: dict[str, tuple[str, ...]] = {
    "gene": ("ncbi", "ensembl", "europepmc"),
    "protein": ("uniprot", "ncbi", "interpro", "string"),
    "compound": ("pubchem", "chembl"),
    "structure": ("rcsb",),
    "variant": ("ncbi", "ensembl"),
    "literature": ("ncbi", "europepmc"),
    "clinical trial": ("clinicaltrials",),
    "pathway": ("reactome",),
    "protein interaction": ("string",),
    "expression study": ("ncbi",),
    "sequence": ("ncbi",),
}

_NCBI_DATABASES = {
    "literature": "pubmed",
    "variant": "clinvar",
    "expression study": "gds",
    "sequence": "nuccore",
    "protein": "protein",
    "gene": "gene",
    "auto": "gene",
}


def provider_supports_entity(provider: str, entity_type: str) -> bool:
    if entity_type in {"", "auto"}:
        return True
    spec = PROVIDERS.get(provider)
    if spec is None:
        return False
    aliases = {
        "expression": "expression study",
        "trial": "clinical trial",
        "interaction": "protein interaction",
        "domain": "protein domain",
    }
    requested = aliases.get(entity_type, entity_type)
    return requested in spec.domains or (
        requested == "protein" and provider in {"ncbi", "interpro", "string"}
    )


def provider_rows() -> list[dict[str, object]]:
    return [
        {
            "key": spec.key,
            "provider": spec.name,
            "domains": ", ".join(spec.domains),
            "base_url": spec.base_url,
            "documentation_url": spec.documentation_url,
            "description": spec.description,
            "rate_limit_rps": spec.requests_per_second,
            "credential": spec.optional_key_env or "Not required",
            "credential_configured": bool(os.getenv(spec.optional_key_env, "").strip()) if spec.optional_key_env else True,
            "query_mode": "Free text / accession" if spec.supports_free_text else "Identifier / exact symbol",
        }
        for spec in PROVIDERS.values()
    ]


class ConnectedProviderService:
    def __init__(
        self,
        project_root: str | Path,
        client: ConnectedHttpClient | None = None,
        *,
        persist_queries: bool = True,
    ) -> None:
        self.root = Path(project_root).resolve()
        settings = settings_from_environment()
        self.registry = runtime_database_path(self.root, "connected_sources.sqlite3")
        self.persist_queries = bool(persist_queries)
        self.client = client or ConnectedHttpClient(
            self.root / "cache" / "connected",
            timeout_seconds=settings.timeout_seconds,
            connect_timeout_seconds=settings.connect_timeout_seconds,
            retries=settings.retries,
            cache_ttl_seconds=settings.cache_ttl_seconds,
            maximum_redirects=settings.maximum_redirects,
        )

    @staticmethod
    def _query(query: str) -> str:
        clean = " ".join(str(query).strip().split())
        if not clean:
            raise ValueError("A scientific query or accession is required.")
        if len(clean) > 2_000:
            raise ValueError("Connected-provider queries are limited to 2,000 characters.")
        return clean

    @staticmethod
    def _limit(limit: int) -> int:
        settings = settings_from_environment()
        return min(settings.maximum_records, max(1, int(limit)))

    @staticmethod
    def _result(
        provider: str,
        query: str,
        entity_type: str,
        records: list[ConnectedRecord],
        response: Any,
        warnings: tuple[str, ...] = (),
    ) -> QueryResult:
        version = ""
        if getattr(response, "headers", None):
            version = str(response.headers.get("etag") or response.headers.get("last-modified") or "")
        return QueryResult(
            provider=provider,
            query=query,
            entity_type=entity_type,
            records=tuple(records),
            retrieved_at_utc=datetime.now(UTC).isoformat(timespec="seconds"),
            source_url=response.url,
            sha256=response.sha256,
            cache_status=response.cache_status,
            warnings=warnings,
            elapsed_ms=float(getattr(response, "elapsed_ms", 0.0)),
            request_id=str(getattr(response, "request_id", "")),
            provider_version=version,
        )

    def _save(self, result: QueryResult) -> QueryResult:
        if self.persist_queries:
            record_query(self.registry, result)
        return result

    def search_ncbi(self, query: str, *, database: str = "gene", limit: int = 10) -> QueryResult:
        query = self._query(query)
        limit = self._limit(limit)
        allowed = {PROVIDERS["ncbi"].host}
        settings = settings_from_environment()
        parameters = {
            "db": database,
            "term": query,
            "retmode": "json",
            "retmax": limit,
            "tool": settings.ncbi_tool,
        }
        email = os.getenv("NCBI_EMAIL", "").strip()
        api_key = os.getenv("NCBI_API_KEY", "").strip()
        if email:
            parameters["email"] = email
        if api_key:
            parameters["api_key"] = api_key
        rate = 10.0 if api_key else 3.0
        search_url = f"{PROVIDERS['ncbi'].base_url}/esearch.fcgi?{urlencode(parameters)}"
        payload, search_response = self.client.get_json(
            "ncbi", search_url, allowed_hosts=allowed, requests_per_second=rate
        )
        ids = [str(value) for value in payload.get("esearchresult", {}).get("idlist", [])]
        warnings: list[str] = []
        if not email:
            warnings.append("NCBI_EMAIL is not configured; add a contact email for production use.")
        if not ids:
            return self._save(self._result("ncbi", query, database, [], search_response, tuple(warnings)))
        summary_parameters = {
            "db": database,
            "id": ",".join(ids),
            "retmode": "json",
            "tool": settings.ncbi_tool,
        }
        if email:
            summary_parameters["email"] = email
        if api_key:
            summary_parameters["api_key"] = api_key
        summary_url = f"{PROVIDERS['ncbi'].base_url}/esummary.fcgi?{urlencode(summary_parameters)}"
        summary, response = self.client.get_json(
            "ncbi", summary_url, allowed_hosts=allowed, requests_per_second=rate
        )
        result_map = summary.get("result", {}) if isinstance(summary, dict) else {}
        records: list[ConnectedRecord] = []
        ordered_ids = result_map.get("uids", ids) if isinstance(result_map, dict) else ids
        for uid in ordered_ids:
            row = result_map.get(str(uid), {}) if isinstance(result_map, dict) else {}
            if not isinstance(row, dict):
                continue
            title = str(row.get("title") or row.get("name") or row.get("caption") or f"{database} {uid}")
            summary_text = str(
                row.get("summary") or row.get("description") or row.get("extra") or "NCBI indexed record"
            )
            if database == "pubmed":
                source_url = f"https://pubmed.ncbi.nlm.nih.gov/{uid}/"
            else:
                source_url = f"https://www.ncbi.nlm.nih.gov/{quote(database)}/{uid}"
            records.append(
                ConnectedRecord("ncbi", str(uid), database, title, summary_text[:1200], source_url, row)
            )
        return self._save(self._result("ncbi", query, database, records, response, tuple(warnings)))

    def search_pubchem(self, query: str, *, limit: int = 10) -> QueryResult:
        query = self._query(query)
        limit = self._limit(limit)
        namespace = "name"
        if query.isdigit():
            namespace = "cid"
        elif re.fullmatch(r"[A-Z]{14}-[A-Z]{10}-[A-Z]", query.upper()):
            namespace = "inchikey"
        encoded = quote(query, safe="")
        properties = "Title,CanonicalSMILES,IsomericSMILES,MolecularFormula,MolecularWeight,InChIKey"
        url = f"{PROVIDERS['pubchem'].base_url}/compound/{namespace}/{encoded}/property/{properties}/JSON"
        payload, response = self.client.get_json(
            "pubchem", url, allowed_hosts={PROVIDERS["pubchem"].host}, requests_per_second=4
        )
        rows = payload.get("PropertyTable", {}).get("Properties", []) if isinstance(payload, dict) else []
        records: list[ConnectedRecord] = []
        for row in rows[:limit] if isinstance(rows, list) else []:
            cid = str(row.get("CID", ""))
            title = str(row.get("Title") or query)
            summary = f"{row.get('MolecularFormula', 'Formula unavailable')} · MW {row.get('MolecularWeight', 'NA')}"
            records.append(
                ConnectedRecord(
                    "pubchem", cid, "compound", title, summary,
                    f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}", row,
                )
            )
        return self._save(self._result("pubchem", query, "compound", records, response))

    def search_uniprot(self, query: str, *, limit: int = 10) -> QueryResult:
        query = self._query(query)
        limit = self._limit(limit)
        api_query = f"accession:{query.upper()}" if re.fullmatch(r"[A-NR-Z0-9][A-Z0-9]{5,9}", query.upper()) else query
        params = urlencode({
            "query": api_query,
            "format": "json",
            "size": limit,
            "fields": "accession,id,protein_name,gene_names,organism_name,length,reviewed",
        })
        url = f"{PROVIDERS['uniprot'].base_url}/uniprotkb/search?{params}"
        payload, response = self.client.get_json(
            "uniprot", url, allowed_hosts={PROVIDERS["uniprot"].host}, requests_per_second=3
        )
        rows = payload.get("results", []) if isinstance(payload, dict) else []
        records: list[ConnectedRecord] = []
        for row in rows if isinstance(rows, list) else []:
            accession = str(row.get("primaryAccession", ""))
            protein = row.get("proteinDescription", {}) if isinstance(row, dict) else {}
            recommended = protein.get("recommendedName", {}) if isinstance(protein, dict) else {}
            full_name = recommended.get("fullName", {}) if isinstance(recommended, dict) else {}
            title = str(full_name.get("value") or row.get("uniProtkbId") or accession)
            organism = row.get("organism", {}) if isinstance(row, dict) else {}
            genes = row.get("genes", []) if isinstance(row, dict) else []
            gene_name = ""
            if genes and isinstance(genes[0], dict):
                gene_name = str(genes[0].get("geneName", {}).get("value", ""))
            reviewed = "Reviewed" if row.get("entryType") == "UniProtKB reviewed (Swiss-Prot)" else "Unreviewed"
            summary = " · ".join(
                value for value in [gene_name, str(organism.get("scientificName", "")),
                                    f"Length {row.get('sequence', {}).get('length', 'NA')}", reviewed] if value
            )
            records.append(
                ConnectedRecord(
                    "uniprot", accession, "protein", title, summary,
                    f"https://www.uniprot.org/uniprotkb/{accession}/entry", row,
                )
            )
        return self._save(self._result("uniprot", query, "protein", records, response))

    def search_rcsb(self, query: str, *, limit: int = 10) -> QueryResult:
        query = self._query(query)
        limit = self._limit(limit)
        allowed = {"search.rcsb.org", "data.rcsb.org"}
        clean = query.upper()
        if len(clean) == 4 and clean.isalnum():
            url = f"https://data.rcsb.org/rest/v1/core/entry/{quote(clean)}"
            payload, response = self.client.get_json(
                "rcsb", url, allowed_hosts=allowed, requests_per_second=3
            )
            title = str(payload.get("struct", {}).get("title") or clean) if isinstance(payload, dict) else clean
            methods = payload.get("exptl", []) if isinstance(payload, dict) else []
            method = ", ".join(str(item.get("method", "")) for item in methods if isinstance(item, dict))
            resolution = payload.get("rcsb_entry_info", {}).get("resolution_combined", []) if isinstance(payload, dict) else []
            summary = " · ".join(value for value in [method, f"Resolution {resolution[0]} Å" if resolution else ""] if value) or "RCSB PDB entry"
            records = [
                ConnectedRecord(
                    "rcsb", clean, "structure", title, summary,
                    f"https://www.rcsb.org/structure/{clean}", payload if isinstance(payload, dict) else {},
                )
            ]
            return self._save(self._result("rcsb", query, "structure", records, response))
        body = {
            "query": {"type": "terminal", "service": "full_text", "parameters": {"value": query}},
            "return_type": "entry",
            "request_options": {"paginate": {"start": 0, "rows": limit}},
        }
        payload, response = self.client.post_json(
            "rcsb", "https://search.rcsb.org/rcsbsearch/v2/query",
            allowed_hosts=allowed, json_body=body, requests_per_second=2,
        )
        rows = payload.get("result_set", []) if isinstance(payload, dict) else []
        records: list[ConnectedRecord] = []
        for row in rows if isinstance(rows, list) else []:
            pdb_id = str(row.get("identifier", ""))
            score = float(row.get("score", 0.0))
            records.append(
                ConnectedRecord(
                    "rcsb", pdb_id, "structure", pdb_id, f"Full-text search score {score:.4f}",
                    f"https://www.rcsb.org/structure/{pdb_id}", row, score,
                )
            )
        return self._save(self._result("rcsb", query, "structure", records, response))

    def search_chembl(self, query: str, *, limit: int = 10) -> QueryResult:
        query = self._query(query)
        limit = self._limit(limit)
        if re.fullmatch(r"CHEMBL\d+", query.upper()):
            url = f"{PROVIDERS['chembl'].base_url}/molecule/{quote(query.upper())}.json"
            payload, response = self.client.get_json(
                "chembl", url, allowed_hosts={PROVIDERS["chembl"].host}, requests_per_second=3
            )
            rows = [payload] if isinstance(payload, dict) else []
        else:
            url = f"{PROVIDERS['chembl'].base_url}/molecule/search.json?{urlencode({'q': query, 'limit': limit})}"
            payload, response = self.client.get_json(
                "chembl", url, allowed_hosts={PROVIDERS["chembl"].host}, requests_per_second=3
            )
            rows = payload.get("molecules", []) if isinstance(payload, dict) else []
        records: list[ConnectedRecord] = []
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            identifier = str(row.get("molecule_chembl_id", ""))
            title = str(row.get("pref_name") or identifier)
            properties = row.get("molecule_properties", {}) or {}
            summary = f"Type {row.get('molecule_type', 'NA')} · MW {properties.get('full_mwt', 'NA')}"
            records.append(
                ConnectedRecord(
                    "chembl", identifier, "compound", title, summary,
                    f"https://www.ebi.ac.uk/chembl/explore/compound/{identifier}", row,
                )
            )
        return self._save(self._result("chembl", query, "compound", records[:limit], response))

    def search_ensembl(self, query: str, *, species: str = "homo_sapiens", limit: int = 10) -> QueryResult:
        query = self._query(query)
        limit = self._limit(limit)
        if re.fullmatch(r"ENS[A-Z]*\d+(?:\.\d+)?", query.upper()):
            url = f"{PROVIDERS['ensembl'].base_url}/lookup/id/{quote(query)}?expand=1"
        else:
            url = f"{PROVIDERS['ensembl'].base_url}/lookup/symbol/{quote(species)}/{quote(query)}?expand=1"
        payload, response = self.client.get_json(
            "ensembl", url, allowed_hosts={PROVIDERS["ensembl"].host},
            headers={"Content-Type": "application/json"}, requests_per_second=5,
        )
        identifier = str(payload.get("id", query)) if isinstance(payload, dict) else query
        title = str(payload.get("display_name") or identifier) if isinstance(payload, dict) else identifier
        summary = (
            f"{payload.get('biotype', 'Unknown biotype')} · {payload.get('seq_region_name', 'NA')}:"
            f"{payload.get('start', 'NA')}-{payload.get('end', 'NA')} ({payload.get('strand', 'NA')})"
            if isinstance(payload, dict) else "Ensembl record"
        )
        species_path = species.replace("_", " ").title().replace(" ", "_")
        records = [
            ConnectedRecord(
                "ensembl", identifier, "gene", title, summary,
                f"https://www.ensembl.org/{species_path}/Gene/Summary?g={identifier}",
                payload if isinstance(payload, dict) else {},
            )
        ]
        return self._save(self._result("ensembl", query, "gene", records[:limit], response))

    def search_clinical_trials(self, query: str, *, limit: int = 10) -> QueryResult:
        query = self._query(query)
        limit = self._limit(limit)
        url = f"{PROVIDERS['clinicaltrials'].base_url}/studies?{urlencode({'query.term': query, 'pageSize': limit, 'format': 'json'})}"
        payload, response = self.client.get_json(
            "clinicaltrials", url, allowed_hosts={PROVIDERS["clinicaltrials"].host}, requests_per_second=3
        )
        rows = payload.get("studies", []) if isinstance(payload, dict) else []
        records: list[ConnectedRecord] = []
        for row in rows if isinstance(rows, list) else []:
            protocol = row.get("protocolSection", {})
            ident = protocol.get("identificationModule", {})
            status = protocol.get("statusModule", {})
            design = protocol.get("designModule", {})
            nct = str(ident.get("nctId", ""))
            title = str(ident.get("briefTitle") or ident.get("officialTitle") or nct)
            summary = f"{status.get('overallStatus', 'Unknown')} · {design.get('studyType', 'Study')}"
            records.append(
                ConnectedRecord(
                    "clinicaltrials", nct, "clinical trial", title, summary,
                    f"https://clinicaltrials.gov/study/{nct}", row,
                )
            )
        return self._save(self._result("clinicaltrials", query, "clinical trial", records, response))

    def search_reactome(self, query: str, *, species: str = "Homo sapiens", limit: int = 10) -> QueryResult:
        query = self._query(query)
        limit = self._limit(limit)
        url = f"{PROVIDERS['reactome'].base_url}/search/query?{urlencode({'query': query, 'species': species, 'types': 'Pathway', 'cluster': 'true'})}"
        payload, response = self.client.get_json(
            "reactome", url, allowed_hosts={PROVIDERS["reactome"].host}, requests_per_second=3
        )
        groups = payload.get("results", []) if isinstance(payload, dict) else []
        rows: list[dict[str, Any]] = []
        for group in groups if isinstance(groups, list) else []:
            entries = group.get("entries", []) if isinstance(group, dict) else []
            rows.extend([entry for entry in entries if isinstance(entry, dict)])
        records: list[ConnectedRecord] = []
        for row in rows[:limit]:
            stable = str(row.get("stId") or row.get("dbId") or "")
            title = str(row.get("name") or stable)
            summary = str(row.get("typeName") or "Pathway")
            records.append(
                ConnectedRecord(
                    "reactome", stable, "pathway", title, summary,
                    f"https://reactome.org/content/detail/{stable}", row,
                )
            )
        return self._save(self._result("reactome", query, "pathway", records, response))

    def search_string(self, query: str, *, species: int = 9606, limit: int = 50) -> QueryResult:
        query = self._query(query)
        limit = min(200, self._limit(limit))
        settings = settings_from_environment()
        identifiers = "\r".join(part.strip() for part in query.replace(",", " ").split() if part.strip())
        params = urlencode({
            "identifiers": identifiers,
            "species": int(species),
            "limit": limit,
            "caller_identity": settings.string_caller_identity,
        })
        url = f"{PROVIDERS['string'].base_url}/json/network?{params}"
        payload, response = self.client.get_json(
            "string", url, allowed_hosts={PROVIDERS["string"].host}, requests_per_second=2
        )
        rows = payload if isinstance(payload, list) else []
        records: list[ConnectedRecord] = []
        for row in rows[:limit]:
            left = str(row.get("preferredName_A") or row.get("stringId_A") or "A")
            right = str(row.get("preferredName_B") or row.get("stringId_B") or "B")
            score = float(row.get("score", 0.0))
            records.append(
                ConnectedRecord(
                    "string", f"{left}--{right}", "protein interaction", f"{left} ↔ {right}",
                    f"Combined score {score:.3f}",
                    f"https://string-db.org/network/{row.get('stringId_A', '')}", row, score,
                )
            )
        return self._save(self._result("string", query, "protein interaction", records, response))

    def search_interpro(self, query: str, *, limit: int = 10) -> QueryResult:
        query = self._query(query)
        limit = self._limit(limit)
        accession = query.upper()
        if re.fullmatch(r"[A-NR-Z0-9][A-Z0-9]{5,9}", accession):
            url = f"{PROVIDERS['interpro'].base_url}/entry/interpro/protein/uniprot/{quote(accession)}/?page_size={limit}"
        else:
            url = f"{PROVIDERS['interpro'].base_url}/entry/interpro/?{urlencode({'search': query, 'page_size': limit})}"
        payload, response = self.client.get_json(
            "interpro", url, allowed_hosts={PROVIDERS["interpro"].host}, requests_per_second=2
        )
        rows = payload.get("results", []) if isinstance(payload, dict) else []
        records: list[ConnectedRecord] = []
        for row in rows if isinstance(rows, list) else []:
            metadata = row.get("metadata", {}) if isinstance(row, dict) else {}
            identifier = str(metadata.get("accession") or "")
            title = str(metadata.get("name") or identifier)
            summary = str(metadata.get("type") or "InterPro entry")
            records.append(
                ConnectedRecord(
                    "interpro", identifier, "protein domain", title, summary,
                    f"https://www.ebi.ac.uk/interpro/entry/InterPro/{identifier}/", row,
                )
            )
        return self._save(self._result("interpro", query, "protein domain", records, response))

    def search_europe_pmc(self, query: str, *, limit: int = 10) -> QueryResult:
        query = self._query(query)
        limit = self._limit(limit)
        url = f"{PROVIDERS['europepmc'].base_url}/search?{urlencode({'query': query, 'format': 'json', 'pageSize': limit, 'resultType': 'core'})}"
        payload, response = self.client.get_json(
            "europepmc", url, allowed_hosts={PROVIDERS["europepmc"].host}, requests_per_second=3
        )
        rows = payload.get("resultList", {}).get("result", []) if isinstance(payload, dict) else []
        records: list[ConnectedRecord] = []
        for row in rows if isinstance(rows, list) else []:
            identifier = str(row.get("pmid") or row.get("pmcid") or row.get("id") or "")
            title = str(row.get("title") or identifier)
            summary = " · ".join(
                value for value in [str(row.get("authorString", "")), str(row.get("journalTitle", "")), str(row.get("pubYear", ""))] if value
            )
            source = str(row.get("source", "MED"))
            records.append(
                ConnectedRecord(
                    "europepmc", identifier, "literature", title, summary,
                    f"https://europepmc.org/article/{source}/{identifier}", row,
                )
            )
        return self._save(self._result("europepmc", query, "literature", records, response))

    def search(self, provider: str, query: str, *, entity_type: str = "auto", limit: int = 10) -> QueryResult:
        key = provider.strip().lower()
        if key not in PROVIDERS:
            raise ConnectedServiceError(f"Unsupported connected provider: {provider}", category="invalid_request")
        mapping: dict[str, Callable[..., QueryResult]] = {
            "pubchem": self.search_pubchem,
            "uniprot": self.search_uniprot,
            "rcsb": self.search_rcsb,
            "chembl": self.search_chembl,
            "ensembl": self.search_ensembl,
            "clinicaltrials": self.search_clinical_trials,
            "reactome": self.search_reactome,
            "string": self.search_string,
            "interpro": self.search_interpro,
            "europepmc": self.search_europe_pmc,
        }
        if key == "ncbi":
            return self.search_ncbi(query, database=_NCBI_DATABASES.get(entity_type, "gene"), limit=limit)
        return mapping[key](query, limit=limit)

    def universal_search(
        self,
        query: str,
        *,
        entity_type: str,
        providers: list[str] | None = None,
        limit: int = 10,
    ) -> dict[str, object]:
        query = self._query(query)
        selected = providers or list(ENTITY_PROVIDER_DEFAULTS.get(entity_type, ("ncbi", "europepmc")))
        results: list[QueryResult] = []
        errors: list[dict[str, object]] = []
        skipped: list[dict[str, str]] = []
        for provider in dict.fromkeys(selected):
            if provider not in PROVIDERS:
                errors.append({"provider": provider, "error_type": "unknown_provider", "error": "Unknown provider"})
                continue
            if not provider_supports_entity(provider, entity_type):
                skipped.append({
                    "provider": provider,
                    "reason": f"{PROVIDERS[provider].name} does not declare support for {entity_type} searches.",
                })
                continue
            try:
                results.append(self.search(provider, query, entity_type=entity_type, limit=limit))
            except ConnectedServiceError as exc:
                errors.append({
                    "provider": provider,
                    "error_type": exc.category,
                    "http_status": exc.status_code,
                    "retryable": exc.retryable,
                    "error": str(exc),
                })
            except Exception as exc:
                errors.append({"provider": provider, "error_type": "unexpected_error", "error": str(exc)})
        return {
            "query": query,
            "entity_type": entity_type,
            "providers_requested": selected,
            "providers_completed": [result.provider for result in results],
            "provider_results": [result.to_dict() for result in results],
            "records": [record.to_dict() for result in results for record in result.records],
            "errors": errors,
            "skipped": skipped,
            "completed_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        }

    def probe(self, provider: str) -> dict[str, object]:
        if provider not in PROVIDERS:
            raise ValueError(f"Unknown provider: {provider}")
        probes = {
            "ncbi": ("TP53[gene] AND human[orgn]", "gene"),
            "pubchem": ("aspirin", "compound"),
            "uniprot": ("P69905", "protein"),
            "rcsb": ("4HHB", "structure"),
            "chembl": ("CHEMBL25", "compound"),
            "ensembl": ("TP53", "gene"),
            "clinicaltrials": ("TP53", "clinical trial"),
            "reactome": ("TP53", "pathway"),
            "string": ("TP53 BRCA1", "protein interaction"),
            "interpro": ("P04637", "protein"),
            "europepmc": ("CRISPR", "literature"),
        }
        query, entity_type = probes[provider]
        started = datetime.now(UTC)
        diagnostic: ConnectionDiagnostic
        try:
            probe_service = ConnectedProviderService(
                self.root, client=self.client, persist_queries=False
            )
            result = probe_service.search(provider, query, entity_type=entity_type, limit=1)
            diagnostic = ConnectionDiagnostic(
                provider=provider,
                available=True,
                stage="application_query",
                status="connected",
                records=len(result.records),
                cache_status=result.cache_status,
                latency_ms=round((datetime.now(UTC) - started).total_seconds() * 1000, 2),
                request_id=result.request_id,
                checked_at_utc=datetime.now(UTC).isoformat(timespec="seconds"),
            )
        except ConnectedServiceError as exc:
            diagnostic = ConnectionDiagnostic(
                provider=provider,
                available=False,
                stage="application_query",
                status="failed",
                latency_ms=round((datetime.now(UTC) - started).total_seconds() * 1000, 2),
                http_status=exc.status_code,
                error_type=exc.category,
                error=str(exc),
                checked_at_utc=datetime.now(UTC).isoformat(timespec="seconds"),
            )
        except Exception as exc:
            diagnostic = ConnectionDiagnostic(
                provider=provider,
                available=False,
                stage="application_query",
                status="failed",
                latency_ms=round((datetime.now(UTC) - started).total_seconds() * 1000, 2),
                error_type="unexpected_error",
                error=str(exc),
                checked_at_utc=datetime.now(UTC).isoformat(timespec="seconds"),
            )
        record_health_check(self.registry, diagnostic)
        return diagnostic.to_dict()

    def probe_all(self, providers: list[str] | None = None) -> list[dict[str, object]]:
        return [self.probe(provider) for provider in (providers or list(PROVIDERS))]
