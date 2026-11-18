from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler
from typing import Any

USER_AGENT = "BioIntel-AI/15.8.0 (https://github.com/lavesh69/BioIntel-AI)"

CODON_TABLE = {
    "TTT": "F", "TTC": "F", "TTA": "L", "TTG": "L",
    "CTT": "L", "CTC": "L", "CTA": "L", "CTG": "L",
    "ATT": "I", "ATC": "I", "ATA": "I", "ATG": "M",
    "GTT": "V", "GTC": "V", "GTA": "V", "GTG": "V",
    "TCT": "S", "TCC": "S", "TCA": "S", "TCG": "S",
    "CCT": "P", "CCC": "P", "CCA": "P", "CCG": "P",
    "ACT": "T", "ACC": "T", "ACA": "T", "ACG": "T",
    "GCT": "A", "GCC": "A", "GCA": "A", "GCG": "A",
    "TAT": "Y", "TAC": "Y", "TAA": "*", "TAG": "*",
    "CAT": "H", "CAC": "H", "CAA": "Q", "CAG": "Q",
    "AAT": "N", "AAC": "N", "AAA": "K", "AAG": "K",
    "GAT": "D", "GAC": "D", "GAA": "E", "GAG": "E",
    "TGT": "C", "TGC": "C", "TGA": "*", "TGG": "W",
    "CGT": "R", "CGC": "R", "CGA": "R", "CGG": "R",
    "AGT": "S", "AGC": "S", "AGA": "R", "AGG": "R",
    "GGT": "G", "GGC": "G", "GGA": "G", "GGG": "G",
}

AA_WEIGHTS = {
    "A": 89.09, "R": 174.20, "N": 132.12, "D": 133.10, "C": 121.16,
    "E": 147.13, "Q": 146.15, "G": 75.07, "H": 155.16, "I": 131.17,
    "L": 131.17, "K": 146.19, "M": 149.21, "F": 165.19, "P": 115.13,
    "S": 105.09, "T": 119.12, "W": 204.23, "Y": 181.19, "V": 117.15,
}


def _fetch_json(url: str, timeout: float = 4.5, data: bytes | None = None, headers: dict[str, str] | None = None) -> Any:
    hdrs = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, data=data, headers=hdrs)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def analyze_sequence(raw_seq: str) -> dict[str, Any]:
    lines = [ln.strip() for ln in raw_seq.strip().splitlines() if ln.strip()]
    header = ""
    if lines and lines[0].startswith(">"):
        header = lines[0][1:].strip()
        lines = lines[1:]
    cleaned = re.sub(r"[^A-Za-z*]", "", "".join(lines)).upper()
    if not cleaned:
        return {"error": "Empty or invalid sequence. Paste DNA, RNA, or Protein (FASTA or raw)."}
    if len(cleaned) > 100000:
        return {"error": "Sequence exceeds 100,000 residue limit for web analysis."}

    unique = set(cleaned)
    is_dna = unique.issubset(set("ATGCN"))
    is_rna = unique.issubset(set("AUGCN")) and "U" in unique

    counts: dict[str, int] = {}
    for ch in cleaned:
        counts[ch] = counts.get(ch, 0) + 1

    if is_dna or is_rna:
        dna = cleaned.replace("U", "T")
        length = len(dna)
        gc_count = dna.count("G") + dna.count("C")
        at_count = dna.count("A") + dna.count("T")
        gc_pct = round((gc_count / length) * 100, 2)
        at_pct = round((at_count / length) * 100, 2)

        comp_map = str.maketrans("ATGCN", "TACGN")
        complement = dna.translate(comp_map)
        rev_complement = complement[::-1]
        rna = dna.replace("T", "U")

        # Translation (Frame +1)
        protein = "".join(CODON_TABLE.get(dna[i:i + 3], "X") for i in range(0, length - 2, 3))

        # Melting temperature (Wallace rule for <14 nt, Marmur-Doty for >=14 nt)
        if length < 14:
            tm_c = round(2 * at_count + 4 * gc_count, 2)
        else:
            tm_c = round(64.9 + 41 * (gc_count - 16.4) / length, 2)

        # Approximate ssDNA/ssRNA molecular weight (Da)
        if is_rna:
            mw_da = round(
                cleaned.count("A") * 329.2 + cleaned.count("U") * 306.2 +
                cleaned.count("C") * 305.2 + cleaned.count("G") * 345.2 + 159.0, 2
            )
        else:
            mw_da = round(
                dna.count("A") * 313.21 + dna.count("T") * 304.2 +
                dna.count("C") * 289.18 + dna.count("G") * 329.21 - 61.96, 2
            )

        # Find longest ORF in frame 1
        orfs = re.findall(r"M[^*]*\*", protein)
        longest_orf = max(orfs, key=len) if orfs else ""

        return {
            "header": header or "Untitled Sequence",
            "type": "RNA" if is_rna else "DNA",
            "length": length,
            "gc_percent": gc_pct,
            "at_percent": at_pct,
            "melting_temp_c": tm_c,
            "molecular_weight_da": mw_da,
            "composition": counts,
            "rna_transcript": rna[:600],
            "reverse_complement": rev_complement[:600],
            "protein_translation": protein[:600],
            "longest_orf": longest_orf[:300],
            "truncated": length > 600,
            "provenance": "Deterministic Bioinformatics Engine (BioIntel AI v15.8.0)",
        }

    # Protein analysis
    length = len(cleaned)
    mw_da = round(sum(AA_WEIGHTS.get(aa, 110.0) for aa in cleaned) - 18.015 * max(0, length - 1), 2)
    hydrophobic = sum(cleaned.count(x) for x in "AILMFWV")
    charged_pos = sum(cleaned.count(x) for x in "KRH")
    charged_neg = sum(cleaned.count(x) for x in "DE")
    return {
        "header": header or "Untitled Protein",
        "type": "Protein",
        "length": length,
        "molecular_weight_da": mw_da,
        "molecular_weight_kda": round(mw_da / 1000.0, 3),
        "hydrophobic_percent": round((hydrophobic / length) * 100, 2),
        "net_charge_approx": charged_pos - charged_neg,
        "composition": counts,
        "provenance": "Deterministic Protein Physicochemical Engine (BioIntel AI v15.8.0)",
    }


def _search_uniprot(q: str) -> list[dict[str, Any]]:
    url = f"https://rest.uniprot.org/uniprotkb/search?query={urllib.parse.quote(q)}&size=5&format=json"
    data = _fetch_json(url, timeout=4.0)
    results = []
    for item in data.get("results", [])[:5]:
        acc = item.get("primaryAccession", "")
        org = item.get("organism", {}).get("scientificName", "Unknown")
        pname = (
            item.get("proteinDescription", {})
            .get("recommendedName", {})
            .get("fullName", {})
            .get("value", item.get("uniProtkbId", acc))
        )
        length = item.get("sequence", {}).get("length", "")
        results.append({
            "source": "UniProtKB",
            "id": acc,
            "title": pname,
            "meta": f"{org} · {length} aa" if length else org,
            "url": f"https://www.uniprot.org/uniprotkb/{acc}",
        })
    return results


def _search_europepmc(q: str) -> list[dict[str, Any]]:
    url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?query={urllib.parse.quote(q)}&pageSize=5&format=json"
    data = _fetch_json(url, timeout=4.0)
    results = []
    for item in data.get("resultList", {}).get("result", [])[:5]:
        pmid = item.get("pmid") or item.get("id", "")
        results.append({
            "source": "Europe PMC",
            "id": f"PMID:{pmid}" if item.get("pmid") else str(pmid),
            "title": item.get("title", "Untitled Paper"),
            "meta": f"{item.get('journalTitle', 'Journal')} ({item.get('pubYear', '')}) · Citations: {item.get('citedByCount', 0)}",
            "url": f"https://europepmc.org/article/MED/{pmid}" if item.get("pmid") else "https://europepmc.org/",
        })
    return results


def _search_rcsb(q: str) -> list[dict[str, Any]]:
    payload = json.dumps({
        "query": {
            "type": "terminal",
            "service": "full_text",
            "parameters": {"value": q},
        },
        "return_type": "entry",
        "request_options": {"paginate": {"start": 0, "rows": 5}},
    }).encode("utf-8")
    data = _fetch_json(
        "https://search.rcsb.org/rcsbsearch/v2/query",
        timeout=4.0,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    results = []
    for item in data.get("result_set", [])[:5]:
        pdb_id = item.get("identifier", "")
        score = round(float(item.get("score", 0)), 3)
        results.append({
            "source": "RCSB PDB",
            "id": pdb_id,
            "title": f"3D Macromolecular Structure {pdb_id}",
            "meta": f"Relevance Score: {score} · Click 'Load in 3D' to inspect",
            "pdb_id": pdb_id,
            "url": f"https://www.rcsb.org/structure/{pdb_id}",
        })
    return results


def _search_pubchem(q: str) -> list[dict[str, Any]]:
    url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{urllib.parse.quote(q)}/property/MolecularFormula,MolecularWeight,IUPACName/JSON"
    data = _fetch_json(url, timeout=3.5)
    results = []
    for prop in data.get("PropertyTable", {}).get("Properties", [])[:3]:
        cid = prop.get("CID", "")
        results.append({
            "source": "PubChem",
            "id": f"CID:{cid}",
            "title": prop.get("IUPACName") or q,
            "meta": f"Formula: {prop.get('MolecularFormula', 'N/A')} · MW: {prop.get('MolecularWeight', 'N/A')} g/mol",
            "url": f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}",
        })
    return results


def multi_database_search(q: str) -> dict[str, Any]:
    q = q.strip()
    if not q:
        return {"error": "Enter a gene, protein, compound, or disease query (e.g. TP53, BRCA1, aspirin, insulin)."}

    providers = [
        ("UniProtKB", _search_uniprot),
        ("RCSB PDB", _search_rcsb),
        ("Europe PMC", _search_europepmc),
        ("PubChem", _search_pubchem),
    ]
    all_results: list[dict[str, Any]] = []
    provider_status: dict[str, str] = {}

    with ThreadPoolExecutor(max_workers=4) as pool:
        futs = {name: pool.submit(fn, q) for name, fn in providers}
        for name, fut in futs.items():
            try:
                res = fut.result(timeout=4.8)
                all_results.extend(res)
                provider_status[name] = f"OK ({len(res)})"
            except Exception:
                provider_status[name] = "No match / Timeout"

    return {
        "query": q,
        "total": len(all_results),
        "provider_status": provider_status,
        "results": all_results,
    }


def search_clinical_trials(q: str) -> dict[str, Any]:
    q = q.strip()
    if not q:
        return {"error": "Enter a disease, drug, or biomarker (e.g. glioblastoma, EGFR, Alzheimer)."}
    url = f"https://clinicaltrials.gov/api/v2/studies?query.term={urllib.parse.quote(q)}&pageSize=10"
    data = _fetch_json(url, timeout=5.0)
    trials = []
    for st_obj in data.get("studies", [])[:10]:
        ps = st_obj.get("protocolSection", {})
        ident = ps.get("identificationModule", {})
        status = ps.get("statusModule", {})
        design = ps.get("designModule", {})
        sponsor = ps.get("sponsorCollaboratorsModule", {}).get("leadSponsor", {})
        conds = ps.get("conditionsModule", {}).get("conditions", [])
        nct = ident.get("nctId", "")
        trials.append({
            "nct_id": nct,
            "title": ident.get("briefTitle", "Untitled Study"),
            "status": status.get("overallStatus", "UNKNOWN"),
            "phases": ", ".join(design.get("phases", [])) or "N/A",
            "conditions": ", ".join(conds[:3]),
            "sponsor": sponsor.get("name", "N/A"),
            "url": f"https://clinicaltrials.gov/study/{nct}",
        })
    return {"query": q, "count": len(trials), "trials": trials, "source": "ClinicalTrials.gov API v2 (Live)"}


def fetch_india_weather(city: str) -> dict[str, Any]:
    city = (city or "New Delhi").strip()
    geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={urllib.parse.quote(city)}&count=5&language=en&format=json"
    geo = _fetch_json(geo_url, timeout=4.0)
    matches = geo.get("results", [])
    if not matches:
        return {"error": f"Location '{city}' not found in Open-Meteo Geocoding."}

    # Prefer Indian locations if present
    selected = next((m for m in matches if m.get("country_code") == "IN"), matches[0])
    lat = selected["latitude"]
    lon = selected["longitude"]
    wx_url = (
        f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
        "&current=temperature_2m,relative_humidity_2m,wind_speed_10m,apparent_temperature"
    )
    wx = _fetch_json(wx_url, timeout=4.0)
    cur = wx.get("current", {})
    return {
        "city": selected.get("name", city),
        "state": selected.get("admin1", ""),
        "country": selected.get("country", ""),
        "latitude": lat,
        "longitude": lon,
        "temperature_c": cur.get("temperature_2m"),
        "feels_like_c": cur.get("apparent_temperature"),
        "humidity_pct": cur.get("relative_humidity_2m"),
        "wind_kmh": cur.get("wind_speed_10m"),
        "source": "Open-Meteo Live Weather & Geocoding API",
    }


class handler(BaseHTTPRequestHandler):
    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        action = (params.get("action", ["health"])[0] or "health").lower()

        try:
            if action == "health":
                self._send_json(200, {
                    "status": "ok",
                    "product": "BioIntel AI",
                    "version": "15.8.0",
                    "owner": "Lavesh Dobriyal",
                    "tagline": "Biology, Engineered into Intelligence.",
                })
            elif action == "search":
                q = params.get("q", [""])[0]
                self._send_json(200, multi_database_search(q))
            elif action == "trials":
                q = params.get("q", [""])[0]
                self._send_json(200, search_clinical_trials(q))
            elif action == "weather":
                city = params.get("city", ["New Delhi"])[0]
                self._send_json(200, fetch_india_weather(city))
            elif action == "sequence":
                seq = params.get("seq", [""])[0]
                self._send_json(200, analyze_sequence(seq))
            else:
                self._send_json(400, {"error": f"Unknown action: {action}"})
        except Exception as exc:
            self._send_json(500, {"error": f"Upstream API or runtime error: {exc}"})

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        action = (params.get("action", ["sequence"])[0] or "sequence").lower()
        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(min(length, 200000)).decode("utf-8", errors="replace")
            body = json.loads(raw) if raw else {}
            if action == "sequence":
                self._send_json(200, analyze_sequence(str(body.get("sequence", ""))))
            else:
                self._send_json(400, {"error": f"Unsupported POST action: {action}"})
        except Exception as exc:
            self._send_json(400, {"error": f"Invalid request payload: {exc}"})
