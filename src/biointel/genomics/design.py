from __future__ import annotations

from dataclasses import asdict, dataclass

from Bio.Seq import Seq


@dataclass(frozen=True)
class PrimerCandidate:
    sequence: str
    start: int
    end: int
    length: int
    gc_percent: float
    tm_celsius: float
    homopolymer: int
    hairpin_risk: bool


@dataclass(frozen=True)
class PrimerPair:
    forward: PrimerCandidate
    reverse: PrimerCandidate
    product_size: int
    tm_difference: float
    score: float


@dataclass(frozen=True)
class GuideCandidate:
    sequence: str
    pam: str
    strand: str
    start: int
    gc_percent: float
    efficiency_score: float
    risk_flags: list[str]


def clean_dna(sequence: str) -> str:
    seq = "".join(sequence.split()).upper().replace("U", "T")
    if not seq or any(base not in "ACGTN" for base in seq):
        raise ValueError("DNA sequence contains unsupported symbols.")
    return seq


def tm(sequence: str) -> float:
    seq = clean_dna(sequence)
    gc = seq.count("G") + seq.count("C")
    at = seq.count("A") + seq.count("T")
    if len(seq) < 14:
        return float(2 * at + 4 * gc)
    return round(64.9 + 41 * (gc - 16.4) / len(seq), 2)


def _homopolymer(seq: str) -> int:
    best = run = 1
    for a, b in zip(seq, seq[1:]):
        run = run + 1 if a == b else 1
        best = max(best, run)
    return best


def primer_candidates(
    sequence: str,
    *,
    minimum_length: int = 18,
    maximum_length: int = 24,
    minimum_tm: float = 55,
    maximum_tm: float = 65,
    minimum_gc: float = 35,
    maximum_gc: float = 65,
) -> list[PrimerCandidate]:
    seq = clean_dna(sequence)
    rows = []
    for start in range(len(seq) - minimum_length + 1):
        for length in range(minimum_length, maximum_length + 1):
            oligo = seq[start : start + length]
            if len(oligo) != length or "N" in oligo:
                continue
            gc = 100 * (oligo.count("G") + oligo.count("C")) / length
            temp = tm(oligo)
            hom = _homopolymer(oligo)
            if minimum_gc <= gc <= maximum_gc and minimum_tm <= temp <= maximum_tm and hom <= 4:
                reverse_complement = str(Seq(oligo).reverse_complement())
                hairpin = any(
                    reverse_complement[i : i + 4] in oligo for i in range(max(0, len(oligo) - 7))
                )
                rows.append(
                    PrimerCandidate(
                        oligo, start, start + length, length, round(gc, 2), temp, hom, hairpin
                    )
                )
    return rows


def design_primer_pairs(
    sequence: str,
    *,
    minimum_product: int = 100,
    maximum_product: int = 600,
    maximum_pairs: int = 50,
) -> list[PrimerPair]:
    from bisect import bisect_left, bisect_right

    seq = clean_dna(sequence)
    forward = primer_candidates(seq)
    reverse_raw = primer_candidates(str(Seq(seq).reverse_complement()))
    mapped = []
    for item in reverse_raw:
        start = len(seq) - item.end
        end = len(seq) - item.start
        mapped.append(
            PrimerCandidate(
                item.sequence,
                start,
                end,
                item.length,
                item.gc_percent,
                item.tm_celsius,
                item.homopolymer,
                item.hairpin_risk,
            )
        )
    mapped.sort(key=lambda item: item.end)
    ends = [item.end for item in mapped]
    pairs = []
    for f in forward:
        lower = f.start + minimum_product
        upper = f.start + maximum_product
        left = bisect_left(ends, lower)
        right = bisect_right(ends, upper)
        for reverse in mapped[left:right]:
            if reverse.start <= f.end:
                continue
            product = reverse.end - f.start
            diff = abs(f.tm_celsius - reverse.tm_celsius)
            score = (
                100
                - diff * 5
                - abs(product - (minimum_product + maximum_product) / 2) / 20
                - 10 * (f.hairpin_risk + reverse.hairpin_risk)
            )
            pairs.append(PrimerPair(f, reverse, product, round(diff, 2), round(score, 2)))
    return sorted(pairs, key=lambda item: item.score, reverse=True)[:maximum_pairs]


def find_crispr_guides(
    sequence: str, *, pam: str = "NGG", guide_length: int = 20
) -> list[GuideCandidate]:
    seq = clean_dna(sequence)
    rows = []
    for strand, working in [("+", seq), ("-", str(Seq(seq).reverse_complement()))]:
        for i in range(guide_length, len(working) - 2):
            pam_seq = working[i : i + 3]
            if len(pam_seq) < 3 or not (pam_seq[1:] == "GG"):
                continue
            guide = working[i - guide_length : i]
            if "N" in guide:
                continue
            gc = 100 * (guide.count("G") + guide.count("C")) / len(guide)
            risks = []
            if gc < 35 or gc > 70:
                risks.append("GC outside preferred 35–70% range")
            if _homopolymer(guide) >= 5:
                risks.append("Long homopolymer")
            if "TTTT" in guide:
                risks.append("Pol III termination motif")
            efficiency = max(0, 100 - abs(gc - 50) * 1.5 - 10 * len(risks))
            position = i - guide_length if strand == "+" else len(seq) - i
            rows.append(
                GuideCandidate(
                    guide, pam_seq, strand, position, round(gc, 2), round(efficiency, 2), risks
                )
            )
    return sorted(rows, key=lambda item: item.efficiency_score, reverse=True)


def result_dict(item):
    return asdict(item)
