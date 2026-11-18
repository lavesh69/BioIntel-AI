from __future__ import annotations

import gzip
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd

VCF_COLUMNS = [
    "chrom",
    "pos",
    "id",
    "ref",
    "alt",
    "qual",
    "filter",
    "info",
    "format",
    "samples",
    "variant_type",
    "depth",
    "allele_frequency",
]


@dataclass(frozen=True)
class VariantSummary:
    variants: int
    snps: int
    insertions: int
    deletions: int
    complex_variants: int
    multiallelic: int
    transitions: int
    transversions: int
    ts_tv_ratio: float | None
    pass_variants: int
    mean_quality: float
    mean_depth: float | None
    chromosomes: dict[str, int]
    genotype_counts: dict[str, int]
    samples: int

    @property
    def passed(self) -> int:  # backward compatibility
        return self.pass_variants

    @property
    def indels(self) -> int:  # backward compatibility
        return self.insertions + self.deletions + self.complex_variants


def decode_vcf_bytes(payload: bytes, *, filename: str = "") -> str:
    is_gzip = payload[:2] == b"\x1f\x8b" or filename.lower().endswith(".gz")
    raw = gzip.decompress(payload) if is_gzip else payload
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("VCF must be UTF-8 text (optionally gzip-compressed).") from exc


def _coerce_scalar(value: str) -> Any:
    if value in {"", "."}:
        return None
    if "," in value:
        return [_coerce_scalar(item) for item in value.split(",")]
    try:
        return int(value)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            return value


def parse_info(text: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for token in str(text or "").split(";"):
        if not token:
            continue
        if "=" in token:
            key, value = token.split("=", 1)
            result[key] = _coerce_scalar(value)
        else:
            result[token] = True
    return result


def _variant_type(ref: str, alt: str) -> str:
    alts = alt.split(",")
    if len(alts) > 1:
        return "Multiallelic"
    allele = alts[0]
    if len(ref) == 1 and len(allele) == 1:
        return "SNP"
    if len(ref) < len(allele) and allele.startswith(ref):
        return "Insertion"
    if len(ref) > len(allele) and ref.startswith(allele):
        return "Deletion"
    return "Complex"


def _sample_payload(format_text: str | None, sample_text: str) -> dict[str, Any]:
    keys = str(format_text or "").split(":") if format_text else []
    values = str(sample_text or "").split(":")
    return {key: _coerce_scalar(value) for key, value in zip(keys, values)}


def _allele_specific_value(value: Any, allele_index: int) -> Any:
    if isinstance(value, list):
        offset = allele_index - 1
        return value[offset] if offset < len(value) else None
    return value


def _recode_genotype(genotype: str, allele_index: int) -> str:
    text = str(genotype or ".")
    separator = "|" if "|" in text else "/" if "/" in text else None
    alleles = text.replace("|", "/").split("/")
    recoded: list[str] = []
    for allele in alleles:
        if allele == ".":
            recoded.append(".")
            continue
        try:
            recoded.append("1" if int(allele) == allele_index else "0")
        except ValueError:
            recoded.append(".")
    return (separator or "").join(recoded) if separator else recoded[0]


def _split_sample_value(format_text: str | None, sample_text: str, allele_index: int) -> str:
    if not format_text:
        return sample_text
    keys = str(format_text).split(":")
    values = str(sample_text).split(":")
    output = list(values)
    for position, key in enumerate(keys):
        if position >= len(output):
            break
        if key == "GT":
            output[position] = _recode_genotype(output[position], allele_index)
        elif key == "AD":
            depths = output[position].split(",")
            target = depths[allele_index] if allele_index < len(depths) else "."
            output[position] = ",".join([depths[0] if depths else ".", target])
    return ":".join(output)


def parse_vcf(text: str, *, max_variants: int = 1_000_000) -> pd.DataFrame:
    """Parse VCF text and split multiallelic records into allele-specific rows."""
    sample_names: list[str] = []
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.startswith("##"):
            continue
        if line.startswith("#CHROM"):
            fields = line.lstrip("#").split("\t")
            sample_names = fields[9:]
            continue
        if line.startswith("#"):
            continue
        fields = line.split("\t")
        if len(fields) < 8:
            raise ValueError(f"VCF line {line_number} has fewer than 8 columns.")
        chrom, pos, variant_id, ref, alt_text, qual, filter_value, info_text = fields[:8]
        try:
            position = int(pos)
        except ValueError as exc:
            raise ValueError(f"Invalid POS at line {line_number}.") from exc
        format_text = fields[8] if len(fields) > 8 else None
        original_samples = {name: value for name, value in zip(sample_names, fields[9:])}
        info = parse_info(info_text)
        depth_value = info.get("DP")
        if isinstance(depth_value, list):
            depth_value = depth_value[0] if depth_value else None
        alternate_alleles = [
            allele.strip().upper() for allele in alt_text.split(",") if allele.strip()
        ]
        if not alternate_alleles:
            raise ValueError(f"VCF line {line_number} has no ALT allele.")
        source_key = f"{chrom}:{position}:{ref.upper()}:{alt_text.upper()}:{line_number}"
        for allele_index, alternate in enumerate(alternate_alleles, 1):
            if len(rows) >= max_variants:
                raise ValueError(
                    f"VCF exceeds the {max_variants:,}-allele safety limit after multiallelic splitting."
                )
            split_samples = {
                name: _split_sample_value(format_text, value, allele_index)
                for name, value in original_samples.items()
            }
            parsed_samples = {
                name: _sample_payload(format_text, value) for name, value in split_samples.items()
            }
            allele_info = dict(info)
            for key in ("AF", "AC", "MLEAF", "MLEAC"):
                if key in allele_info:
                    allele_info[key] = _allele_specific_value(allele_info[key], allele_index)
            allele_frequency = allele_info.get("AF")
            rows.append(
                {
                    "chrom": chrom,
                    "chromosome": chrom,
                    "pos": position,
                    "id": None if variant_id == "." else variant_id,
                    "ref": ref.upper(),
                    "alt": alternate,
                    "qual": None if qual == "." else float(qual),
                    "quality": None if qual == "." else float(qual),
                    "filter": filter_value,
                    "info": allele_info,
                    "format": format_text,
                    "samples": split_samples,
                    "sample_fields": parsed_samples,
                    "variant_type": _variant_type(ref.upper(), alternate),
                    "depth": pd.to_numeric(depth_value, errors="coerce"),
                    "allele_frequency": pd.to_numeric(allele_frequency, errors="coerce"),
                    "allele_index": allele_index,
                    "source_alt_count": len(alternate_alleles),
                    "source_multiallelic": len(alternate_alleles) > 1,
                    "source_record_key": source_key,
                }
            )
    if not rows:
        raise ValueError("No VCF variants found.")
    return pd.DataFrame(rows)


def variant_summary(frame: pd.DataFrame) -> VariantSummary:
    required = {"chrom", "pos", "ref", "alt", "filter"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError("Missing VCF columns: " + ", ".join(sorted(missing)))
    types = frame.get(
        "variant_type",
        pd.Series([_variant_type(str(row.ref), str(row.alt)) for row in frame.itertuples()]),
    )
    transitions = 0
    transversions = 0
    transition_pairs = {("A", "G"), ("G", "A"), ("C", "T"), ("T", "C")}
    genotypes: dict[str, int] = {}
    sample_names: set[str] = set()
    for row, kind in zip(frame.itertuples(), types):
        if kind == "SNP":
            if (str(row.ref), str(row.alt)) in transition_pairs:
                transitions += 1
            else:
                transversions += 1
        for name, value in (getattr(row, "samples", {}) or {}).items():
            sample_names.add(name)
            genotype = str(value).split(":", 1)[0]
            genotypes[genotype] = genotypes.get(genotype, 0) + 1
    quality = pd.to_numeric(frame.get("qual"), errors="coerce")
    depth = (
        pd.to_numeric(frame.get("depth"), errors="coerce")
        if "depth" in frame
        else pd.Series(dtype=float)
    )
    return VariantSummary(
        variants=len(frame),
        snps=int((types == "SNP").sum()),
        insertions=int((types == "Insertion").sum()),
        deletions=int((types == "Deletion").sum()),
        complex_variants=int((types == "Complex").sum()),
        multiallelic=(
            int(
                frame.loc[
                    frame.get("source_multiallelic", False).astype(bool), "source_record_key"
                ].nunique()
            )
            if "source_multiallelic" in frame and "source_record_key" in frame
            else int((types == "Multiallelic").sum())
        ),
        transitions=transitions,
        transversions=transversions,
        ts_tv_ratio=round(transitions / transversions, 4) if transversions else None,
        pass_variants=int(frame["filter"].isin(["PASS", "."]).sum()),
        mean_quality=round(float(quality.mean()), 4) if quality.notna().any() else 0.0,
        mean_depth=round(float(depth.mean()), 4)
        if not depth.empty and depth.notna().any()
        else None,
        chromosomes=frame["chrom"].astype(str).value_counts().to_dict(),
        genotype_counts=genotypes,
        samples=len(sample_names),
    )


def genotype_matrix(frame: pd.DataFrame, *, sample_names: list[str] | None = None) -> pd.DataFrame:
    available = sorted({name for row in frame.get("samples", []) for name in (row or {})})
    selected = sample_names or available
    records: list[dict[str, Any]] = []
    for row in frame.itertuples():
        base: dict[str, Any] = {
            "chrom": row.chrom,
            "pos": row.pos,
            "id": row.id,
            "ref": row.ref,
            "alt": row.alt,
        }
        samples = getattr(row, "samples", {}) or {}
        for name in selected:
            base[name] = str(samples.get(name, "./.")).split(":", 1)[0]
        records.append(base)
    return pd.DataFrame(records)


def sample_summary(frame: pd.DataFrame) -> pd.DataFrame:
    names = sorted({name for row in frame.get("samples", []) for name in (row or {})})
    rows: list[dict[str, Any]] = []
    for name in names:
        counts: dict[str, int] = {}
        called = 0
        for sample_map in frame["samples"]:
            genotype = str((sample_map or {}).get(name, "./.")).split(":", 1)[0]
            counts[genotype] = counts.get(genotype, 0) + 1
            if genotype not in {"./.", ".|.", "."}:
                called += 1
        rows.append(
            {
                "sample": name,
                "variants": len(frame),
                "called": called,
                "call_rate_percent": round(100 * called / max(len(frame), 1), 3),
                "hom_ref": counts.get("0/0", 0) + counts.get("0|0", 0),
                "heterozygous": counts.get("0/1", 0)
                + counts.get("1/0", 0)
                + counts.get("0|1", 0)
                + counts.get("1|0", 0),
                "hom_alt": counts.get("1/1", 0) + counts.get("1|1", 0),
                "missing": counts.get("./.", 0) + counts.get(".|.", 0) + counts.get(".", 0),
            }
        )
    return pd.DataFrame(rows)


def mask_low_quality_genotypes(
    frame: pd.DataFrame,
    *,
    minimum_sample_depth: int | None = None,
    minimum_genotype_quality: float | None = None,
    minimum_alt_depth: int | None = None,
) -> pd.DataFrame:
    """Mask sample genotypes that fail FORMAT-level DP, GQ or AD thresholds."""
    output = frame.copy(deep=True)
    masked_counts: list[int] = []
    updated_samples = []
    updated_fields = []
    for row in output.itertuples(index=False):
        sample_map = dict(getattr(row, "samples", {}) or {})
        field_map = dict(getattr(row, "sample_fields", {}) or {})
        masked = 0
        for sample, fields in field_map.items():
            fail = False
            if minimum_sample_depth is not None:
                dp = pd.to_numeric(fields.get("DP"), errors="coerce")
                fail |= bool(pd.isna(dp) or float(dp) < minimum_sample_depth)
            if minimum_genotype_quality is not None:
                gq = pd.to_numeric(fields.get("GQ"), errors="coerce")
                fail |= bool(pd.isna(gq) or float(gq) < minimum_genotype_quality)
            if minimum_alt_depth is not None:
                ad = fields.get("AD")
                if isinstance(ad, list):
                    alt_depth = pd.to_numeric(ad[1] if len(ad) > 1 else None, errors="coerce")
                elif isinstance(ad, str) and "," in ad:
                    alt_depth = pd.to_numeric(ad.split(",")[1], errors="coerce")
                else:
                    alt_depth = np.nan
                fail |= bool(pd.isna(alt_depth) or float(alt_depth) < minimum_alt_depth)
            if fail:
                format_text = str(getattr(row, "format", "") or "")
                tokens = str(sample_map.get(sample, ".")).split(":")
                keys = format_text.split(":") if format_text else []
                if "GT" in keys and keys.index("GT") < len(tokens):
                    tokens[keys.index("GT")] = "./."
                elif tokens:
                    tokens[0] = "./."
                sample_map[sample] = ":".join(tokens)
                fields = dict(fields)
                fields["GT"] = "./."
                field_map[sample] = fields
                masked += 1
        updated_samples.append(sample_map)
        updated_fields.append(field_map)
        masked_counts.append(masked)
    output["samples"] = updated_samples
    output["sample_fields"] = updated_fields
    output["masked_sample_calls"] = masked_counts
    return output


def filter_variants(
    frame: pd.DataFrame,
    *,
    minimum_quality: float = 20,
    require_pass: bool = True,
    minimum_depth: int | None = None,
    maximum_allele_frequency: float | None = None,
    variant_types: list[str] | None = None,
    chromosomes: list[str] | None = None,
) -> pd.DataFrame:
    output = frame.copy()
    output = output[pd.to_numeric(output["qual"], errors="coerce").fillna(0) >= minimum_quality]
    if require_pass:
        output = output[output["filter"].isin(["PASS", "."])]
    if minimum_depth is not None:
        output = output[
            pd.to_numeric(output.get("depth"), errors="coerce").fillna(0) >= minimum_depth
        ]
    if maximum_allele_frequency is not None and "allele_frequency" in output:
        values = pd.to_numeric(output["allele_frequency"], errors="coerce")
        output = output[values.isna() | (values <= maximum_allele_frequency)]
    if variant_types:
        output = output[output["variant_type"].isin(variant_types)]
    if chromosomes:
        output = output[output["chrom"].astype(str).isin(chromosomes)]
    return output.reset_index(drop=True)


def summary_dict(result: VariantSummary) -> dict[str, Any]:
    return asdict(result)
