from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import pandas as pd

CANONICAL_CONTIGS = {
    "GRCh37": {str(value) for value in range(1, 23)} | {"X", "Y", "MT"},
    "GRCh38": {str(value) for value in range(1, 23)} | {"X", "Y", "MT"},
    "GRCm39": {str(value) for value in range(1, 20)} | {"X", "Y", "MT"},
}


@dataclass(frozen=True)
class ReferenceValidationSummary:
    variants_checked: int
    reference_matches: int
    reference_mismatches: int
    missing_contigs: int
    out_of_range: int
    match_percent: float


def normalize_contig(contig: object) -> str:
    value = str(contig).strip()
    if value.lower().startswith("chr"):
        value = value[3:]
    return "MT" if value.upper() in {"M", "MT", "MITO"} else value.upper()


def normalize_alleles(position: int, ref: str, alt: str) -> tuple[int, str, str]:
    """Minimal left-trim-independent allele normalization.

    Common suffixes and prefixes are removed while retaining at least one base
    in each allele. Full repeat-aware left alignment additionally requires the
    declared reference sequence and is handled by ``left_align_variant``.
    """
    ref = str(ref).upper()
    alt = str(alt).upper()
    position = int(position)
    if not ref or not alt:
        raise ValueError("REF and ALT alleles cannot be empty.")
    if alt.startswith("<") or "[" in alt or "]" in alt or alt == "*":
        return position, ref, alt
    while len(ref) > 1 and len(alt) > 1 and ref[-1] == alt[-1]:
        ref = ref[:-1]
        alt = alt[:-1]
    while len(ref) > 1 and len(alt) > 1 and ref[0] == alt[0]:
        ref = ref[1:]
        alt = alt[1:]
        position += 1
    return position, ref, alt


def left_align_variant(
    position: int,
    ref: str,
    alt: str,
    reference_sequence: str,
) -> tuple[int, str, str]:
    position, ref, alt = normalize_alleles(position, ref, alt)
    reference = str(reference_sequence).upper()
    if alt.startswith("<") or "[" in alt or "]" in alt or len(ref) == len(alt):
        return position, ref, alt
    while position > 1:
        previous = reference[position - 2] if position - 2 < len(reference) else None
        if previous is None:
            break
        if len(ref) > len(alt):
            deleted = ref[1:] if ref.startswith(alt[0]) else ref
            if not deleted or deleted[-1] != previous:
                break
            ref = previous + ref[:-1]
            alt = previous + alt[:-1] if len(alt) > 1 else previous
        else:
            inserted = alt[1:] if alt.startswith(ref[0]) else alt
            if not inserted or inserted[-1] != previous:
                break
            alt = previous + alt[:-1]
            ref = previous + ref[:-1] if len(ref) > 1 else previous
        position -= 1
        position, ref, alt = normalize_alleles(position, ref, alt)
    return position, ref, alt


def normalize_variant_frame(
    frame: pd.DataFrame,
    *,
    reference_sequences: Mapping[str, str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    required = {"chrom", "pos", "ref", "alt"}
    if not required.issubset(frame.columns):
        raise ValueError("Variant table requires chrom, pos, ref and alt columns.")
    output = frame.copy()
    audit_rows = []
    normalized_rows = []
    for index, row in output.iterrows():
        chrom = str(row["chrom"])
        before = (int(row["pos"]), str(row["ref"]), str(row["alt"]))
        reference = None
        if reference_sequences:
            reference = reference_sequences.get(chrom) or reference_sequences.get(
                normalize_contig(chrom)
            )
        after = (
            left_align_variant(*before, reference)
            if reference is not None
            else normalize_alleles(*before)
        )
        updated = row.to_dict()
        updated.update({"pos": after[0], "ref": after[1], "alt": after[2]})
        normalized_rows.append(updated)
        audit_rows.append(
            {
                "row": index,
                "chrom": chrom,
                "original_pos": before[0],
                "original_ref": before[1],
                "original_alt": before[2],
                "normalized_pos": after[0],
                "normalized_ref": after[1],
                "normalized_alt": after[2],
                "changed": before != after,
                "left_aligned": reference is not None and before != after,
            }
        )
    normalized = pd.DataFrame(normalized_rows)
    normalized["chromosome"] = normalized["chrom"]
    normalized["variant_key"] = normalized.apply(
        lambda row: f"{row['chrom']}:{int(row['pos'])}:{row['ref']}:{row['alt']}", axis=1
    )
    return normalized.reset_index(drop=True), pd.DataFrame(audit_rows)


def parse_fasta_reference(text: str) -> dict[str, str]:
    references: dict[str, list[str]] = {}
    current: str | None = None
    for raw in str(text).splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith(">"):
            current = line[1:].split()[0]
            if current in references:
                raise ValueError(f"Duplicate FASTA contig: {current}")
            references[current] = []
        elif current is None:
            raise ValueError("Reference FASTA sequence appears before the first header.")
        else:
            sequence = line.upper()
            invalid = set(sequence) - set("ACGTRYSWKMBDHVN")
            if invalid:
                raise ValueError(f"Unsupported reference symbols: {', '.join(sorted(invalid))}")
            references[current].append(sequence)
    if not references:
        raise ValueError("No reference FASTA records were found.")
    output = {name: "".join(chunks) for name, chunks in references.items()}
    for name, sequence in list(output.items()):
        output.setdefault(normalize_contig(name), sequence)
    return output


def validate_reference_alleles(
    frame: pd.DataFrame,
    reference_sequences: Mapping[str, str],
) -> tuple[pd.DataFrame, ReferenceValidationSummary]:
    rows = []
    for index, row in frame.iterrows():
        chrom = str(row["chrom"])
        sequence = reference_sequences.get(chrom) or reference_sequences.get(
            normalize_contig(chrom)
        )
        position = int(row["pos"])
        ref = str(row["ref"]).upper()
        if sequence is None:
            status = "missing_contig"
            observed = None
        elif position < 1 or position + len(ref) - 1 > len(sequence):
            status = "out_of_range"
            observed = None
        else:
            observed = sequence[position - 1 : position - 1 + len(ref)].upper()
            status = "match" if observed == ref else "mismatch"
        rows.append(
            {
                "row": index,
                "chrom": chrom,
                "pos": position,
                "ref": ref,
                "observed_reference": observed,
                "reference_status": status,
            }
        )
    audit = pd.DataFrame(rows)
    checked = int(audit["reference_status"].isin(["match", "mismatch"]).sum())
    matches = int((audit["reference_status"] == "match").sum())
    summary = ReferenceValidationSummary(
        variants_checked=checked,
        reference_matches=matches,
        reference_mismatches=int((audit["reference_status"] == "mismatch").sum()),
        missing_contigs=int((audit["reference_status"] == "missing_contig").sum()),
        out_of_range=int((audit["reference_status"] == "out_of_range").sum()),
        match_percent=100 * matches / max(checked, 1),
    )
    return audit, summary


def genome_build_audit(frame: pd.DataFrame, build: str) -> pd.DataFrame:
    if build not in CANONICAL_CONTIGS:
        raise ValueError(f"Unsupported genome build: {build}")
    allowed = CANONICAL_CONTIGS[build]
    counts = frame["chrom"].astype(str).map(normalize_contig).value_counts()
    return pd.DataFrame(
        [
            {
                "contig": contig,
                "variants": int(count),
                "canonical_for_build": contig in allowed,
                "build": build,
            }
            for contig, count in counts.items()
        ]
    )


def structural_variant_table(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for row in frame.itertuples(index=False):
        alt = str(getattr(row, "alt"))
        info = getattr(row, "info", {}) or {}
        symbolic = alt.startswith("<") or "[" in alt or "]" in alt
        if not symbolic and str(info.get("SVTYPE", "")) == "":
            continue
        svtype = str(info.get("SVTYPE") or alt.strip("<>") or "BND")
        end = info.get("END")
        svlen = info.get("SVLEN")
        if isinstance(svlen, list):
            svlen = svlen[0] if svlen else None
        if end is None and svlen is not None:
            try:
                end = int(getattr(row, "pos")) + abs(int(svlen)) - 1
            except (TypeError, ValueError):
                end = None
        rows.append(
            {
                "chrom": getattr(row, "chrom"),
                "pos": int(getattr(row, "pos")),
                "end": end,
                "id": getattr(row, "id", None),
                "svtype": svtype,
                "svlen": svlen,
                "alt": alt,
                "filter": getattr(row, "filter", None),
                "qual": getattr(row, "qual", None),
            }
        )
    return pd.DataFrame(
        rows, columns=["chrom", "pos", "end", "id", "svtype", "svlen", "alt", "filter", "qual"]
    )


def annotate_feature_context(variants: pd.DataFrame, annotations: pd.DataFrame) -> pd.DataFrame:
    required = {"seqid", "start", "end", "type"}
    if not required.issubset(annotations.columns):
        raise ValueError("Annotation table requires seqid, start, end and type columns.")
    groups = {
        str(seqid): group.sort_values("start") for seqid, group in annotations.groupby("seqid")
    }
    rows = []
    for row in variants.itertuples(index=False):
        chrom = str(getattr(row, "chrom"))
        position = int(getattr(row, "pos"))
        candidates = groups.get(chrom)
        if candidates is None:
            candidates = groups.get(normalize_contig(chrom))
        if candidates is None:
            overlaps = pd.DataFrame()
        else:
            overlaps = candidates[
                (candidates["start"] <= position) & (candidates["end"] >= position)
            ]
        types = sorted(set(overlaps["type"].astype(str))) if not overlaps.empty else []
        if any(value.lower() == "cds" for value in types):
            context = "coding"
        elif any(value.lower() == "exon" for value in types):
            context = "exonic_non_coding"
        elif any(value.lower() in {"transcript", "mrna", "gene"} for value in types):
            context = "intronic_or_gene_body"
        else:
            context = "intergenic"
        attributes = []
        if not overlaps.empty and "attributes" in overlaps:
            attributes = overlaps["attributes"].astype(str).head(5).tolist()
        rows.append(
            {
                "chrom": chrom,
                "pos": position,
                "ref": getattr(row, "ref"),
                "alt": getattr(row, "alt"),
                "feature_context": context,
                "overlapping_feature_types": ", ".join(types),
                "annotation_attributes": " | ".join(attributes),
            }
        )
    return pd.DataFrame(rows)


def trio_mendelian_audit(
    frame: pd.DataFrame,
    *,
    child: str,
    mother: str,
    father: str,
) -> pd.DataFrame:
    def alleles(value: object) -> set[str] | None:
        genotype = str(value or "").split(":", 1)[0].replace("|", "/")
        if genotype in {"", ".", "./."}:
            return None
        values = genotype.split("/")
        return set(values) if all(item in {"0", "1"} for item in values) else None

    rows = []
    for row in frame.itertuples(index=False):
        samples = getattr(row, "samples", {}) or {}
        child_gt = alleles(samples.get(child))
        mother_gt = alleles(samples.get(mother))
        father_gt = alleles(samples.get(father))
        if child_gt is None or mother_gt is None or father_gt is None:
            status = "unassessable"
        else:
            # A child allele must be explainable by at least one parent; this is a conservative screen.
            status = "consistent" if child_gt.issubset(mother_gt | father_gt) else "violation"
        rows.append(
            {
                "chrom": getattr(row, "chrom"),
                "pos": int(getattr(row, "pos")),
                "ref": getattr(row, "ref"),
                "alt": getattr(row, "alt"),
                "child_gt": str(samples.get(child, "")),
                "mother_gt": str(samples.get(mother, "")),
                "father_gt": str(samples.get(father, "")),
                "mendelian_status": status,
            }
        )
    return pd.DataFrame(rows)
