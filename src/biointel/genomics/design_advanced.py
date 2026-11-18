from __future__ import annotations

import heapq
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Iterable

import numpy as np
from Bio.Seq import Seq
from Bio.SeqUtils import MeltingTemp as mt

from biointel.genomics.design import clean_dna

IUPAC = {
    "A": {"A"},
    "C": {"C"},
    "G": {"G"},
    "T": {"T"},
    "R": {"A", "G"},
    "Y": {"C", "T"},
    "S": {"G", "C"},
    "W": {"A", "T"},
    "K": {"G", "T"},
    "M": {"A", "C"},
    "B": {"C", "G", "T"},
    "D": {"A", "G", "T"},
    "H": {"A", "C", "T"},
    "V": {"A", "C", "G"},
    "N": {"A", "C", "G", "T"},
}

NUCLEASES = {
    "SpCas9": {"pam": "NGG", "pam_side": "3prime", "guide_length": 20, "seed_length": 10},
    "SpCas9-NG": {"pam": "NGN", "pam_side": "3prime", "guide_length": 20, "seed_length": 10},
    "SaCas9": {"pam": "NNGRRT", "pam_side": "3prime", "guide_length": 21, "seed_length": 10},
    "AsCas12a": {"pam": "TTTV", "pam_side": "5prime", "guide_length": 23, "seed_length": 8},
    "LbCas12a": {"pam": "TTTV", "pam_side": "5prime", "guide_length": 23, "seed_length": 8},
}


@dataclass(frozen=True)
class ThermodynamicPrimer:
    sequence: str
    start: int
    end: int
    strand: str
    length: int
    gc_percent: float
    tm_celsius: float
    gc_clamp: int
    homopolymer: int
    self_complementarity: int
    three_prime_complementarity: int
    hairpin_proxy: int
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class AdvancedPrimerPair:
    forward: ThermodynamicPrimer
    reverse: ThermodynamicPrimer
    product_size: int
    tm_difference: float
    heterodimer_proxy: int
    score: float
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class AdvancedGuide:
    guide: str
    pam: str
    nuclease: str
    strand: str
    start: int
    end: int
    cut_site: int
    gc_percent: float
    efficiency_score: float
    specificity_score: float | None
    off_target_count: int | None
    risk_flags: tuple[str, ...]


def nearest_neighbor_tm(
    sequence: str,
    *,
    sodium_millimolar: float = 50.0,
    magnesium_millimolar: float = 1.5,
    dntp_millimolar: float = 0.2,
    primer_nanomolar: float = 250.0,
) -> float:
    seq = clean_dna(sequence)
    if "N" in seq:
        raise ValueError("Nearest-neighbour Tm cannot be calculated for ambiguous bases.")
    value = mt.Tm_NN(
        seq,
        Na=float(sodium_millimolar),
        Mg=float(magnesium_millimolar),
        dNTPs=float(dntp_millimolar),
        dnac1=float(primer_nanomolar),
        dnac2=float(primer_nanomolar),
        saltcorr=7,
    )
    return round(float(value), 2)


def _max_homopolymer(sequence: str) -> int:
    return max((len(match.group(0)) for match in re.finditer(r"(A+|C+|G+|T+)", sequence)), default=0)


def _longest_complementarity(sequence_a: str, sequence_b: str, *, three_prime_only: bool = False) -> int:
    a = sequence_a[-10:] if three_prime_only else sequence_a
    b = str(Seq(sequence_b).reverse_complement())
    best = 0
    for offset in range(-len(b) + 1, len(a)):
        run = 0
        for index in range(len(a)):
            partner = index - offset
            if 0 <= partner < len(b) and a[index] == b[partner]:
                run += 1
                best = max(best, run)
            else:
                run = 0
    return best


def primer_candidate_advanced(
    sequence: str,
    *,
    start: int,
    strand: str,
    sodium_millimolar: float,
    magnesium_millimolar: float,
    dntp_millimolar: float,
    primer_nanomolar: float,
) -> ThermodynamicPrimer:
    oligo = clean_dna(sequence)
    gc = 100 * (oligo.count("G") + oligo.count("C")) / len(oligo)
    gc_clamp = sum(1 for base in oligo[-5:] if base in "GC")
    self_comp = _longest_complementarity(oligo, oligo)
    three_prime = _longest_complementarity(oligo, oligo, three_prime_only=True)
    hairpin = self_comp
    warnings = []
    if gc_clamp == 0:
        warnings.append("No 3′ GC clamp")
    if gc_clamp >= 4:
        warnings.append("Strong 3′ GC clamp")
    if _max_homopolymer(oligo) >= 5:
        warnings.append("Long homopolymer")
    if self_comp >= 7:
        warnings.append("Self-dimer risk")
    if three_prime >= 4:
        warnings.append("3′ self-complementarity")
    return ThermodynamicPrimer(
        sequence=oligo,
        start=int(start),
        end=int(start + len(oligo)),
        strand=strand,
        length=len(oligo),
        gc_percent=round(gc, 2),
        tm_celsius=nearest_neighbor_tm(
            oligo,
            sodium_millimolar=sodium_millimolar,
            magnesium_millimolar=magnesium_millimolar,
            dntp_millimolar=dntp_millimolar,
            primer_nanomolar=primer_nanomolar,
        ),
        gc_clamp=gc_clamp,
        homopolymer=_max_homopolymer(oligo),
        self_complementarity=self_comp,
        three_prime_complementarity=three_prime,
        hairpin_proxy=hairpin,
        warnings=tuple(warnings),
    )


def design_primer_pairs_advanced(
    sequence: str,
    *,
    minimum_product: int = 100,
    maximum_product: int = 500,
    minimum_length: int = 18,
    maximum_length: int = 24,
    minimum_tm: float = 57.0,
    maximum_tm: float = 63.0,
    minimum_gc: float = 35.0,
    maximum_gc: float = 65.0,
    target_start: int | None = None,
    target_end: int | None = None,
    assay_mode: str = "standard_pcr",
    sodium_millimolar: float = 50.0,
    magnesium_millimolar: float = 1.5,
    dntp_millimolar: float = 0.2,
    primer_nanomolar: float = 250.0,
    maximum_pairs: int = 100,
    search_mode: str = "balanced",
    progress_callback: Callable[[str, float], None] | None = None,
) -> list[AdvancedPrimerPair]:
    """Design ranked PCR primer pairs with bounded, transparent search modes.

    ``balanced`` preserves exact nearest-neighbour thermodynamics while pruning
    clearly inferior length/pair combinations before expensive dimer checks.
    ``exhaustive`` retains the historical full search for small templates.
    """

    seq = clean_dna(sequence)
    if minimum_product > maximum_product:
        raise ValueError("Minimum product size cannot exceed maximum product size.")
    if minimum_length > maximum_length:
        raise ValueError("Minimum primer length cannot exceed maximum primer length.")
    if minimum_tm > maximum_tm:
        raise ValueError("Minimum Tm cannot exceed maximum Tm.")
    if minimum_gc > maximum_gc:
        raise ValueError("Minimum GC cannot exceed maximum GC.")
    if maximum_pairs < 1:
        raise ValueError("Maximum pairs must be at least one.")
    if len(seq) < minimum_product:
        raise ValueError("Template is shorter than the requested minimum product size.")
    if target_start is not None and target_end is not None:
        if not 0 <= target_start < target_end <= len(seq):
            raise ValueError("Target coordinates are outside the sequence.")
    if assay_mode == "qpcr":
        maximum_product = min(maximum_product, 250)
        minimum_product = max(minimum_product, 60)
    normalized_mode = str(search_mode).strip().lower()
    if normalized_mode not in {"fast", "balanced", "exhaustive"}:
        raise ValueError("Search mode must be fast, balanced or exhaustive.")

    exact_lengths = {
        "fast": 2,
        "balanced": 3,
        "exhaustive": maximum_length - minimum_length + 1,
    }[normalized_mode]
    pair_candidates_per_forward: int | None = {
        "fast": 12,
        "balanced": 36,
        "exhaustive": None,
    }[normalized_mode]
    reverse_sequence = str(Seq(seq).reverse_complement())
    target_tm = (minimum_tm + maximum_tm) / 2

    def emit(label: str, progress: float) -> None:
        if progress_callback is not None:
            progress_callback(label, float(np.clip(progress, 0.0, 1.0)))

    def best_candidates_per_start(
        working: str,
        *,
        strand: str,
        progress_start: float,
        progress_span: float,
    ) -> list[ThermodynamicPrimer]:
        selected: list[ThermodynamicPrimer] = []
        total_starts = max(1, len(working) - minimum_length + 1)
        for local_start in range(total_starts):
            approximate: list[tuple[float, str]] = []
            for length in range(minimum_length, maximum_length + 1):
                oligo = working[local_start : local_start + length]
                if len(oligo) != length or "N" in oligo:
                    continue
                gc = 100 * (oligo.count("G") + oligo.count("C")) / len(oligo)
                if not minimum_gc <= gc <= maximum_gc or _max_homopolymer(oligo) > 4:
                    continue
                simple_tm = 64.9 + 41 * ((oligo.count("G") + oligo.count("C")) - 16.4) / len(oligo)
                if simple_tm < minimum_tm - 12 or simple_tm > maximum_tm + 12:
                    continue
                approximate.append((abs(simple_tm - target_tm), oligo))

            best: tuple[float, ThermodynamicPrimer] | None = None
            for _, oligo in sorted(approximate, key=lambda item: item[0])[:exact_lengths]:
                genomic_start = (
                    local_start if strand == "+" else len(seq) - (local_start + len(oligo))
                )
                candidate = primer_candidate_advanced(
                    oligo,
                    start=genomic_start,
                    strand=strand,
                    sodium_millimolar=sodium_millimolar,
                    magnesium_millimolar=magnesium_millimolar,
                    dntp_millimolar=dntp_millimolar,
                    primer_nanomolar=primer_nanomolar,
                )
                if not minimum_tm <= candidate.tm_celsius <= maximum_tm:
                    continue
                rank = (
                    abs(candidate.tm_celsius - target_tm)
                    + 2 * len(candidate.warnings)
                    + 0.5 * candidate.three_prime_complementarity
                )
                if best is None or rank < best[0]:
                    best = (rank, candidate)
            if best is not None:
                selected.append(best[1])
            if local_start % 100 == 0 or local_start + 1 == total_starts:
                emit(
                    f"Enumerating {'forward' if strand == '+' else 'reverse'} oligos",
                    progress_start + progress_span * ((local_start + 1) / total_starts),
                )
        return selected

    emit("Validating template and reaction constraints", 0.08)
    candidates_forward = best_candidates_per_start(
        seq, strand="+", progress_start=0.10, progress_span=0.25
    )
    candidates_reverse = best_candidates_per_start(
        reverse_sequence, strand="-", progress_start=0.35, progress_span=0.25
    )
    if not candidates_forward or not candidates_reverse:
        return []

    from bisect import bisect_left, bisect_right

    candidates_reverse.sort(key=lambda item: item.end)
    reverse_ends = [item.end for item in candidates_reverse]
    midpoint = (minimum_product + maximum_product) / 2
    pair_heap: list[tuple[float, int, AdvancedPrimerPair]] = []
    counter = 0
    total_forward = max(1, len(candidates_forward))

    for forward_index, forward in enumerate(candidates_forward):
        lower_end = forward.start + minimum_product
        upper_end = forward.start + maximum_product
        left = bisect_left(reverse_ends, lower_end)
        right = bisect_right(reverse_ends, upper_end)
        reverse_window = [
            reverse
            for reverse in candidates_reverse[left:right]
            if reverse.start > forward.end
            and (
                target_start is None
                or target_end is None
                or (forward.end <= target_start and reverse.start >= target_end)
            )
        ]
        if pair_candidates_per_forward is not None and len(reverse_window) > pair_candidates_per_forward:
            reverse_window = sorted(
                reverse_window,
                key=lambda reverse: (
                    abs(forward.tm_celsius - reverse.tm_celsius) * 5
                    + abs((reverse.end - forward.start) - midpoint) / max(midpoint, 1) * 20
                    + 4 * (len(forward.warnings) + len(reverse.warnings))
                ),
            )[:pair_candidates_per_forward]

        for reverse in reverse_window:
            product = reverse.end - forward.start
            tm_difference = abs(forward.tm_celsius - reverse.tm_celsius)
            heterodimer = _longest_complementarity(forward.sequence, reverse.sequence)
            warnings = list(forward.warnings + reverse.warnings)
            if tm_difference > 3:
                warnings.append("Primer Tm mismatch")
            if heterodimer >= 7:
                warnings.append("Heterodimer risk")
            score = (
                100
                - 5 * tm_difference
                - abs(product - midpoint) / max(midpoint, 1) * 20
                - 4 * max(0, heterodimer - 3)
                - 4 * len(warnings)
            )
            pair = AdvancedPrimerPair(
                forward=forward,
                reverse=reverse,
                product_size=product,
                tm_difference=round(tm_difference, 2),
                heterodimer_proxy=heterodimer,
                score=round(score, 2),
                warnings=tuple(dict.fromkeys(warnings)),
            )
            counter += 1
            heap_item = (pair.score, counter, pair)
            if len(pair_heap) < maximum_pairs:
                heapq.heappush(pair_heap, heap_item)
            elif pair.score > pair_heap[0][0]:
                heapq.heapreplace(pair_heap, heap_item)

        if forward_index % 50 == 0 or forward_index + 1 == total_forward:
            emit(
                "Ranking compatible primer pairs",
                0.60 + 0.38 * ((forward_index + 1) / total_forward),
            )

    emit("Finalizing primer-pair ranking", 0.99)
    return [item[2] for item in sorted(pair_heap, key=lambda item: item[0], reverse=True)]


def _pam_matches(sequence: str, pattern: str) -> bool:
    if len(sequence) != len(pattern):
        return False
    return all(base in IUPAC.get(symbol, {symbol}) for base, symbol in zip(sequence.upper(), pattern.upper()))


def _guide_efficiency(guide: str, nuclease: str) -> float:
    gc = 100 * (guide.count("G") + guide.count("C")) / len(guide)
    score = 100 - abs(gc - 50) * 1.35
    score += 4 if guide[-1] in "GC" else 0
    score -= 15 if "TTTT" in guide else 0
    score -= 8 * max(0, _max_homopolymer(guide) - 4)
    if nuclease.endswith("Cas12a"):
        score += 3 if guide[:3].count("T") <= 1 else -3
    return float(np.clip(score, 0, 100))


def scan_guide_offtargets(
    guide: str,
    reference_sequences: Iterable[str],
    *,
    maximum_mismatches: int = 3,
    seed_length: int = 10,
) -> dict[str, object]:
    query = clean_dna(guide)
    hits = []
    for reference_index, reference in enumerate(reference_sequences):
        ref = clean_dna(reference)
        for strand, working in (("+", ref), ("-", str(Seq(ref).reverse_complement()))):
            for start in range(0, len(working) - len(query) + 1):
                target = working[start : start + len(query)]
                mismatches = sum(a != b for a, b in zip(query, target))
                if mismatches > maximum_mismatches:
                    continue
                seed_mismatches = sum(a != b for a, b in zip(query[-seed_length:], target[-seed_length:]))
                hits.append({
                    "reference_index": reference_index,
                    "strand": strand,
                    "start": start,
                    "target": target,
                    "mismatches": mismatches,
                    "seed_mismatches": seed_mismatches,
                    "risk_score": max(0.0, 100 - 25 * seed_mismatches - 10 * (mismatches - seed_mismatches)),
                })
    hits = sorted(hits, key=lambda row: (-row["risk_score"], row["mismatches"]))
    non_self = [row for row in hits if row["mismatches"] > 0]
    specificity = max(0.0, 100 - sum(row["risk_score"] / 100 for row in non_self[:20]) * 8)
    return {"specificity_score": round(specificity, 2), "off_target_count": len(non_self), "hits": hits}


def find_crispr_guides_advanced(
    sequence: str,
    *,
    nuclease: str = "SpCas9",
    reference_sequences: Iterable[str] | None = None,
    maximum_mismatches: int = 3,
) -> list[AdvancedGuide]:
    seq = clean_dna(sequence)
    config = NUCLEASES.get(nuclease)
    if config is None:
        raise ValueError("Unsupported nuclease. Available: " + ", ".join(sorted(NUCLEASES)))
    pam_pattern = str(config["pam"])
    guide_length = int(config["guide_length"])
    pam_length = len(pam_pattern)
    rows: list[AdvancedGuide] = []
    for strand, working in (("+", seq), ("-", str(Seq(seq).reverse_complement()))):
        if config["pam_side"] == "3prime":
            for pam_start in range(guide_length, len(working) - pam_length + 1):
                pam = working[pam_start : pam_start + pam_length]
                if not _pam_matches(pam, pam_pattern):
                    continue
                guide = working[pam_start - guide_length : pam_start]
                local_start = pam_start - guide_length
                cut_local = pam_start - 3
                rows.append(_make_guide(guide, pam, nuclease, strand, local_start, cut_local, len(seq), reference_sequences, maximum_mismatches, int(config["seed_length"])))
        else:
            for pam_start in range(0, len(working) - pam_length - guide_length + 1):
                pam = working[pam_start : pam_start + pam_length]
                if not _pam_matches(pam, pam_pattern):
                    continue
                guide = working[pam_start + pam_length : pam_start + pam_length + guide_length]
                local_start = pam_start + pam_length
                cut_local = local_start + 18
                rows.append(_make_guide(guide, pam, nuclease, strand, local_start, cut_local, len(seq), reference_sequences, maximum_mismatches, int(config["seed_length"])))
    return sorted(rows, key=lambda item: (item.specificity_score if item.specificity_score is not None else 100, item.efficiency_score), reverse=True)


def _make_guide(
    guide: str,
    pam: str,
    nuclease: str,
    strand: str,
    local_start: int,
    cut_local: int,
    sequence_length: int,
    reference_sequences: Iterable[str] | None,
    maximum_mismatches: int,
    seed_length: int,
) -> AdvancedGuide:
    start = local_start if strand == "+" else sequence_length - local_start - len(guide)
    end = start + len(guide)
    cut_site = cut_local if strand == "+" else sequence_length - cut_local
    gc = 100 * (guide.count("G") + guide.count("C")) / len(guide)
    flags = []
    if gc < 35 or gc > 70:
        flags.append("GC outside preferred range")
    if _max_homopolymer(guide) >= 5:
        flags.append("Long homopolymer")
    if "TTTT" in guide:
        flags.append("Pol III termination motif")
    specificity = None
    off_target_count = None
    if reference_sequences is not None:
        audit = scan_guide_offtargets(guide, reference_sequences, maximum_mismatches=maximum_mismatches, seed_length=seed_length)
        specificity = float(audit["specificity_score"])
        off_target_count = int(audit["off_target_count"])
        if specificity < 70:
            flags.append("Low in-silico specificity")
    return AdvancedGuide(
        guide=guide,
        pam=pam,
        nuclease=nuclease,
        strand=strand,
        start=int(start),
        end=int(end),
        cut_site=int(cut_site),
        gc_percent=round(gc, 2),
        efficiency_score=round(_guide_efficiency(guide, nuclease), 2),
        specificity_score=specificity,
        off_target_count=off_target_count,
        risk_flags=tuple(flags),
    )


def result_dict(item) -> dict:
    return asdict(item)


def in_silico_pcr(
    primer_pairs: Iterable[AdvancedPrimerPair],
    reference_sequences: Iterable[str],
    *,
    circular: bool = False,
    maximum_products_per_pair: int = 100,
) -> list[dict[str, object]]:
    """Exact local in-silico PCR against a compact reference panel.

    This intentionally provides a transparent deterministic screen. Genome-wide
    mismatch-tolerant specificity should use Primer-BLAST or an indexed aligner.
    """
    references = [clean_dna(sequence) for sequence in reference_sequences]
    rows: list[dict[str, object]] = []
    for pair_index, pair in enumerate(primer_pairs, start=1):
        forward = pair.forward.sequence
        reverse_binding = str(Seq(pair.reverse.sequence).reverse_complement())
        products_for_pair = 0
        for reference_index, reference in enumerate(references, start=1):
            working = reference + reference if circular else reference
            maximum_start = len(reference) if circular else len(working)
            forward_starts = [match.start() for match in re.finditer(f"(?={re.escape(forward)})", working[: maximum_start + len(forward) - 1])]
            reverse_starts = [match.start() for match in re.finditer(f"(?={re.escape(reverse_binding)})", working)]
            for forward_start in forward_starts:
                for reverse_start in reverse_starts:
                    if reverse_start <= forward_start:
                        continue
                    product_end = reverse_start + len(reverse_binding)
                    product_size = product_end - forward_start
                    if circular and product_size > len(reference):
                        continue
                    rows.append(
                        {
                            "pair_index": pair_index,
                            "reference_index": reference_index,
                            "forward_start": forward_start % len(reference),
                            "reverse_binding_start": reverse_start % len(reference),
                            "product_size": product_size,
                            "circular_origin_crossing": bool(circular and product_end > len(reference)),
                            "product_sequence": working[forward_start:product_end],
                        }
                    )
                    products_for_pair += 1
                    if products_for_pair >= maximum_products_per_pair:
                        break
                if products_for_pair >= maximum_products_per_pair:
                    break
            if products_for_pair >= maximum_products_per_pair:
                break
    return rows


def multiplex_compatibility(primer_pairs: Iterable[AdvancedPrimerPair]) -> list[dict[str, object]]:
    """Audit cross-pair complementarity for multiplex PCR planning."""
    pairs = list(primer_pairs)
    rows: list[dict[str, object]] = []
    for left_index, left in enumerate(pairs, start=1):
        left_oligos = {"F": left.forward.sequence, "R": left.reverse.sequence}
        for right_index in range(left_index + 1, len(pairs) + 1):
            right = pairs[right_index - 1]
            right_oligos = {"F": right.forward.sequence, "R": right.reverse.sequence}
            scores = {
                f"{left_name}-{right_name}": _longest_complementarity(left_seq, right_seq)
                for left_name, left_seq in left_oligos.items()
                for right_name, right_seq in right_oligos.items()
            }
            maximum = max(scores.values(), default=0)
            rows.append(
                {
                    "pair_a": left_index,
                    "pair_b": right_index,
                    "maximum_cross_complementarity": maximum,
                    "risk": "High" if maximum >= 8 else "Review" if maximum >= 6 else "Low",
                    "worst_interaction": max(scores, key=scores.get) if scores else "",
                    **{f"score_{key}": value for key, value in scores.items()},
                }
            )
    return rows


def base_editing_window(
    guide: AdvancedGuide | str,
    *,
    editor: str = "CBE",
    window_start: int = 4,
    window_end: int = 8,
) -> dict[str, object]:
    """Annotate editable protospacer positions for common base-editor planning."""
    sequence = guide.guide if isinstance(guide, AdvancedGuide) else clean_dna(guide)
    if not 1 <= window_start <= window_end <= len(sequence):
        raise ValueError("Editing window must fall inside the guide sequence.")
    editor_key = editor.upper()
    editable_base, product_base = {"CBE": ("C", "T"), "ABE": ("A", "G")}.get(editor_key, (None, None))
    if editable_base is None:
        raise ValueError("Editor must be CBE or ABE.")
    positions = [index for index in range(window_start, window_end + 1) if sequence[index - 1] == editable_base]
    return {
        "editor": editor_key,
        "guide": sequence,
        "window_start": int(window_start),
        "window_end": int(window_end),
        "editable_base": editable_base,
        "product_base": product_base,
        "editable_positions": positions,
        "editable_count": len(positions),
        "bystander_editing_risk": len(positions) > 1,
    }


def deletion_guide_pairs(
    guides: Iterable[AdvancedGuide],
    *,
    target_start: int,
    target_end: int,
    minimum_flank: int = 0,
    maximum_flank: int = 500,
    maximum_pairs: int = 100,
) -> list[dict[str, object]]:
    """Rank guide pairs flanking a requested deletion interval."""
    if target_start >= target_end:
        raise ValueError("Deletion target start must be smaller than target end.")
    guide_list = list(guides)
    upstream = [guide for guide in guide_list if target_start - maximum_flank <= guide.cut_site <= target_start - minimum_flank]
    downstream = [guide for guide in guide_list if target_end + minimum_flank <= guide.cut_site <= target_end + maximum_flank]
    rows = []
    for left in upstream:
        for right in downstream:
            deletion_size = right.cut_site - left.cut_site
            combined_efficiency = (left.efficiency_score + right.efficiency_score) / 2
            specificity_values = [value for value in (left.specificity_score, right.specificity_score) if value is not None]
            combined_specificity = float(np.mean(specificity_values)) if specificity_values else None
            rows.append(
                {
                    "upstream_guide": left.guide,
                    "downstream_guide": right.guide,
                    "upstream_cut": left.cut_site,
                    "downstream_cut": right.cut_site,
                    "predicted_deletion_size": deletion_size,
                    "combined_efficiency": combined_efficiency,
                    "combined_specificity": combined_specificity,
                    "risk_flags": "; ".join(sorted(set(left.risk_flags + right.risk_flags))),
                }
            )
    return sorted(rows, key=lambda row: (row["combined_specificity"] if row["combined_specificity"] is not None else 100, row["combined_efficiency"]), reverse=True)[:maximum_pairs]
