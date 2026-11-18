from __future__ import annotations

from dataclasses import asdict, dataclass
from urllib.parse import unquote

import pandas as pd


@dataclass(frozen=True)
class AnnotationSummary:
    features: int
    sequence_regions: int
    feature_types: dict[str, int]
    strands: dict[str, int]
    genes: int
    transcripts: int
    exons: int
    cds: int
    total_annotated_bases: int


def parse_attributes(text: str) -> dict[str, str]:
    result = {}
    for token in str(text or "").strip().strip(";").split(";"):
        token = token.strip()
        if not token:
            continue
        if "=" in token:
            key, value = token.split("=", 1)
        elif " " in token:
            key, value = token.split(" ", 1)
            value = value.strip('"')
        else:
            key, value = token, True
        result[key] = unquote(str(value))
    return result


def parse_gff(text: str, *, max_features: int = 2_000_000) -> pd.DataFrame:
    rows = []
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.startswith("#"):
            continue
        fields = line.split("\t")
        if len(fields) != 9:
            raise ValueError(f"GFF/GTF line {line_number} must contain 9 columns.")
        seqid, source, feature, start, end, score, strand, phase, attributes = fields
        if len(rows) >= max_features:
            raise ValueError("Annotation file exceeds safety limit.")
        start_i, end_i = int(start), int(end)
        if start_i < 1 or end_i < start_i:
            raise ValueError(f"Invalid coordinates at line {line_number}.")
        rows.append(
            {
                "seqid": seqid,
                "source": source,
                "type": feature,
                "start": start_i,
                "end": end_i,
                "length": end_i - start_i + 1,
                "score": None if score == "." else float(score),
                "strand": strand,
                "phase": None if phase == "." else phase,
                "attributes": parse_attributes(attributes),
            }
        )
    if not rows:
        raise ValueError("No GFF/GTF features found.")
    return pd.DataFrame(rows)


def annotation_summary(frame: pd.DataFrame) -> AnnotationSummary:
    counts = frame["type"].astype(str).value_counts().to_dict()
    lower = {str(k).lower(): int(v) for k, v in counts.items()}
    return AnnotationSummary(
        len(frame),
        int(frame["seqid"].nunique()),
        counts,
        frame["strand"].astype(str).value_counts().to_dict(),
        lower.get("gene", 0),
        lower.get("mrna", 0) + lower.get("transcript", 0),
        lower.get("exon", 0),
        lower.get("cds", 0),
        int(frame["length"].sum()),
    )


def overlap_features(frame: pd.DataFrame, seqid: str, start: int, end: int) -> pd.DataFrame:
    return frame[
        (frame["seqid"].astype(str) == str(seqid))
        & (frame["start"] <= end)
        & (frame["end"] >= start)
    ].copy()


def summary_dict(result: AnnotationSummary) -> dict:
    return asdict(result)
