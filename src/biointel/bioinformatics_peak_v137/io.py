from __future__ import annotations

import gzip
import io
import json
from pathlib import Path
from typing import Any

import pandas as pd

MAX_INTERACTIVE_BYTES = 250 * 1024 * 1024
MAX_INTERACTIVE_ROWS = 250_000


def _payload(upload: Any) -> tuple[bytes, str]:
    name = str(getattr(upload, "name", "upload"))
    if hasattr(upload, "getvalue"):
        raw = bytes(upload.getvalue())
    else:
        raw = bytes(upload.read())
    if not raw:
        raise ValueError("The uploaded file is empty.")
    if len(raw) > MAX_INTERACTIVE_BYTES:
        raise ValueError("Files above 250 MB must use the background job engine for bounded processing.")
    return raw, name


def _decode(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _read_table(raw: bytes, name: str) -> pd.DataFrame:
    lower = name.lower()
    if lower.endswith((".xlsx", ".xls")):
        return pd.read_excel(io.BytesIO(raw), nrows=MAX_INTERACTIVE_ROWS)
    if lower.endswith(".json"):
        payload = json.loads(_decode(raw))
        if isinstance(payload, dict):
            payload = payload.get("records", payload.get("data", payload.get("members", [payload])))
        return pd.DataFrame(payload).head(MAX_INTERACTIVE_ROWS)
    text = _decode(raw)
    suffix = Path(lower).suffix
    sep = "\t" if suffix in {".tsv", ".txt", ".maf"} else ","
    try:
        return pd.read_csv(io.StringIO(text), sep=sep, nrows=MAX_INTERACTIVE_ROWS)
    except Exception:
        return pd.read_csv(io.StringIO(text), sep=None, engine="python", nrows=MAX_INTERACTIVE_ROWS)


def _parse_vcf(raw: bytes, module_key: str) -> pd.DataFrame:
    text = _decode(raw)
    samples: list[str] = []
    rows: list[dict[str, object]] = []
    for line in text.splitlines():
        if line.startswith("#CHROM"):
            parts = line.split("\t")
            samples = parts[9:]
            continue
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 8:
            continue
        chrom, pos, ident, ref, alt, qual, _filter, info = parts[:8]
        info_map = {}
        for token in info.split(";"):
            if "=" in token:
                key, value = token.split("=", 1)
                info_map[key] = value
        fmt = parts[8].split(":") if len(parts) > 8 else []
        sample_values = parts[9:] if len(parts) > 9 else []
        variant = ident if ident not in {".", ""} else f"{chrom}:{pos}:{ref}>{alt}"
        if module_key in {"structural_variant_peak", "circular_dna_instability"}:
            end = int(float(info_map.get("END", pos)))
            svtype = info_map.get("SVTYPE", "SV")
            rows.append({
                "sample": samples[0] if samples else "VCF",
                "event_id": variant,
                "chrom": chrom,
                "start": int(pos),
                "end": end,
                "event_type": svtype,
                "support": float(info_map.get("SUPPORT", info_map.get("SU", 1)) or 1),
                "quality": pd.to_numeric(qual, errors="coerce"),
                "gene": info_map.get("GENE", "INTERGENIC"),
                "allele_fraction": pd.to_numeric(info_map.get("AF", 0.5), errors="coerce"),
                "copy_number": pd.to_numeric(info_map.get("CN", 2), errors="coerce"),
                "caller": info_map.get("CALLER", "VCF import"),
            })
            continue
        if module_key == "pharmacogenomics_peak":
            rows.append({
                "sample": samples[0] if samples else "VCF",
                "gene": info_map.get("GENE", "Unknown"),
                "variant": variant,
                "drug": "Review medication list",
                "allele": info_map.get("ALLELE", alt),
                "evidence_level": "Low",
                "copy_number": pd.to_numeric(info_map.get("CN", 2), errors="coerce"),
                "population_frequency": pd.to_numeric(info_map.get("AF", 0.5), errors="coerce"),
                "guideline_source": "Imported variant; evidence mapping required",
            })
            continue
        if module_key == "viral_within_host":
            rows.append({
                "sample": samples[0] if samples else "VCF",
                "subject": samples[0] if samples else "VCF",
                "time": 0,
                "chrom": chrom,
                "position": int(pos),
                "ref": ref,
                "alt": alt.split(",")[0],
                "frequency": pd.to_numeric(info_map.get("AF", 0.0), errors="coerce"),
                "lineage": info_map.get("LINEAGE", "Unassigned"),
                "depth": pd.to_numeric(info_map.get("DP", 0), errors="coerce"),
                "recombination_flag": False,
            })
            continue
        if not sample_values:
            rows.append({"sample": "VCF", "variant": variant, "chrom": chrom, "position": int(pos), "genotype": pd.NA, "phenotype": pd.NA})
            continue
        for sample, value in zip(samples, sample_values):
            values = value.split(":")
            fmt_map = dict(zip(fmt, values))
            gt = fmt_map.get("GT", "./.").replace("|", "/")
            dosage = sum(int(x) for x in gt.split("/") if x.isdigit()) if gt not in {"./.", "."} else pd.NA
            rows.append({"sample": sample, "variant": variant, "chrom": chrom, "position": int(pos), "genotype": dosage, "phenotype": pd.NA})
    return pd.DataFrame(rows).head(MAX_INTERACTIVE_ROWS)


def _parse_bed(raw: bytes, module_key: str) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for index, line in enumerate(_decode(raw).splitlines()):
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        chrom, start, end = parts[:3]
        name = parts[3] if len(parts) > 3 else f"region_{index+1}"
        score = pd.to_numeric(parts[4], errors="coerce") if len(parts) > 4 else 1.0
        if module_key == "epigenomics_peak":
            rows.append({"sample":"BED_import","region":name,"condition":"Unspecified","signal":score,"chrom":chrom,"start":int(start),"end":int(end),"motif":"Unknown","gene":"Unknown","methylation":pd.NA})
        elif module_key == "comparative_regulatory_genomics":
            rows.append({"species":"Unknown","region":name,"ortholog_group":name,"motif":"Unknown","conservation":score,"activity":score,"chrom":chrom,"start":int(start),"end":int(end),"tissue":"Unknown"})
        elif module_key in {"structural_variant_peak", "circular_dna_instability"}:
            rows.append({"sample":"BED_import","event_id":name,"chrom":chrom,"start":int(start),"end":int(end),"event_type":"BED_event","support":score,"quality":score,"gene":"INTERGENIC","allele_fraction":0.5,"copy_number":2.0,"caller":"BED import"})
    return pd.DataFrame(rows).head(MAX_INTERACTIVE_ROWS)


def _parse_gff(raw: bytes) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for index, line in enumerate(_decode(raw).splitlines()):
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 9:
            continue
        chrom, source, feature_type, start, end, score, strand, _phase, attributes = parts[:9]
        attr_map: dict[str, str] = {}
        for token in attributes.replace("; ", ";").split(";"):
            if "=" in token:
                key, value = token.split("=", 1)
                attr_map[key.strip()] = value.strip().strip('"')
            elif " " in token:
                key, value = token.split(" ", 1)
                attr_map[key.strip()] = value.strip().strip('"')
        feature_id = attr_map.get("ID", attr_map.get("gene_id", attr_map.get("transcript_id", f"feature_{index+1}")))
        rows.append({
            "genome": source or "GFF import",
            "feature_id": feature_id,
            "chrom": chrom,
            "start": int(start),
            "end": int(end),
            "strand": strand,
            "feature_type": feature_type,
            "evidence": "RNA" if source.lower() not in {".", "unknown"} else "ab_initio",
            "ortholog_group": attr_map.get("ortholog_group", "Unassigned"),
            "completeness": 0.5,
        })
    return pd.DataFrame(rows).head(MAX_INTERACTIVE_ROWS)


def _parse_phenopacket(raw: bytes) -> pd.DataFrame:
    payload = json.loads(_decode(raw))
    packets = payload if isinstance(payload, list) else payload.get("phenopackets", [payload]) if isinstance(payload, dict) else []
    rows: list[dict[str, object]] = []
    for index, packet in enumerate(packets):
        case_id = packet.get("id", packet.get("subject", {}).get("id", f"case_{index+1}"))
        phenotypes = packet.get("phenotypicFeatures", packet.get("phenotypic_features", [])) or [{}]
        interpretations = packet.get("interpretations", []) or [{}]
        for feature in phenotypes:
            phenotype = feature.get("type", {}).get("label", feature.get("label", "Unknown"))
            gene = interpretations[0].get("diagnosis", {}).get("genomicInterpretations", [{}])[0].get("gene", {}).get("symbol", "Unknown") if interpretations else "Unknown"
            rows.append({"case_id":case_id,"source":"Phenopacket import","phenotype":phenotype,"gene":gene,"variant":"Unspecified","phenotype_similarity":0.5,"variant_match":0.0,"access_status":"Controlled","consent_scope":"Unknown"})
    return pd.DataFrame(rows).head(MAX_INTERACTIVE_ROWS)


def read_upload(upload: Any, module_key: str) -> pd.DataFrame:
    raw, name = _payload(upload)
    lower = name.lower()
    if lower.endswith(".gz"):
        raw = gzip.decompress(raw)
        lower = lower[:-3]
    if lower.endswith((".vcf", ".bcf")):
        return _parse_vcf(raw, module_key)
    if lower.endswith((".bed", ".bedpe", ".narrowpeak", ".broadpeak")):
        return _parse_bed(raw, module_key)
    if lower.endswith((".gff", ".gff3", ".gtf")):
        return _parse_gff(raw)
    if lower.endswith(".json") and module_key == "federated_genomic_discovery":
        try:
            return _parse_phenopacket(raw)
        except Exception:
            return _read_table(raw, name)
    return _read_table(raw, name)
