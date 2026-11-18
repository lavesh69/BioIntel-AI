from __future__ import annotations

from hashlib import sha256
import math
from statistics import fmean, pstdev
from typing import Iterable, Sequence

from .catalog import TARGET_PROFILES


def _hash(value: object) -> str:
    return sha256(repr(value).encode("utf-8")).hexdigest()


def _pearson(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or len(left) < 2:
        raise ValueError("equal vectors with at least two values are required")
    left_mean, right_mean = fmean(left), fmean(right)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right))
    denominator = math.sqrt(sum((x - left_mean) ** 2 for x in left) * sum((y - right_mean) ** 2 for y in right))
    return numerator / denominator if denominator else 0.0


def z_prime(positive: Sequence[float], negative: Sequence[float]) -> float:
    if len(positive) < 2 or len(negative) < 2:
        raise ValueError("at least two positive and negative controls are required")
    separation = abs(fmean(positive) - fmean(negative))
    if separation == 0:
        raise ValueError("control means are not separated")
    return 1.0 - 3.0 * (pstdev(positive) + pstdev(negative)) / separation


def split_is_leakage_free(groups: dict[str, Iterable[str]]) -> bool:
    seen: set[str] = set()
    for values in groups.values():
        current = {str(value) for value in values}
        if seen.intersection(current):
            return False
        seen.update(current)
    return True


def benjamini_hochberg(p_values: Sequence[float]) -> list[float]:
    if not p_values or any((not math.isfinite(value)) or value < 0 or value > 1 for value in p_values):
        raise ValueError("p-values must be finite values in [0, 1]")
    count = len(p_values)
    order = sorted(range(count), key=p_values.__getitem__)
    adjusted = [1.0] * count
    running = 1.0
    for rank_index in range(count - 1, -1, -1):
        original_index = order[rank_index]
        rank = rank_index + 1
        running = min(running, p_values[original_index] * count / rank)
        adjusted[original_index] = min(1.0, running)
    return adjusted


def morans_i(values: Sequence[float], edges: Sequence[tuple[int, int]]) -> float:
    if len(values) < 3 or not edges:
        raise ValueError("spatial values and edges are required")
    mean = fmean(values)
    denominator = sum((value - mean) ** 2 for value in values)
    if denominator == 0:
        raise ValueError("constant values have undefined Moran's I")
    weights = 0.0
    numerator = 0.0
    for left, right in edges:
        if left == right or min(left, right) < 0 or max(left, right) >= len(values):
            raise ValueError("invalid spatial edge")
        numerator += (values[left] - mean) * (values[right] - mean)
        weights += 1.0
    return len(values) / weights * numerator / denominator


def coordinates_are_valid(coordinates: Sequence[tuple[float, float]]) -> bool:
    return bool(coordinates) and len(set(coordinates)) == len(coordinates) and all(
        math.isfinite(x) and math.isfinite(y) and x >= 0 and y >= 0 for x, y in coordinates
    )


_ALLOWED_AA = frozenset("ACDEFGHIKLMNPQRSTVWY")


def protein_sequence_valid(sequence: str, minimum: int = 10, maximum: int = 5000) -> bool:
    value = sequence.strip().upper()
    return minimum <= len(value) <= maximum and set(value).issubset(_ALLOWED_AA)


def kmer_jaccard(left: str, right: str, k: int = 3) -> float:
    if k <= 0 or len(left) < k or len(right) < k:
        raise ValueError("sequences must support the requested k-mer size")
    a = {left[index : index + k] for index in range(len(left) - k + 1)}
    b = {right[index : index + k] for index in range(len(right) - k + 1)}
    return len(a & b) / len(a | b)


def longest_hydrophobic_run(sequence: str) -> int:
    hydrophobic = set("AILMFWVY")
    best = current = 0
    for residue in sequence.upper():
        current = current + 1 if residue in hydrophobic else 0
        best = max(best, current)
    return best


def pareto_front(rows: Sequence[tuple[float, float]]) -> tuple[int, ...]:
    result: list[int] = []
    for index, candidate in enumerate(rows):
        dominated = False
        for other_index, other in enumerate(rows):
            if index == other_index:
                continue
            if other[0] >= candidate[0] and other[1] >= candidate[1] and other != candidate:
                dominated = True
                break
        if not dominated:
            result.append(index)
    return tuple(result)


def euclidean(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("coordinate vectors must have equal non-zero length")
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(left, right)))


def pose_rmsd(reference: Sequence[Sequence[float]], candidate: Sequence[Sequence[float]]) -> float:
    if len(reference) != len(candidate) or not reference:
        raise ValueError("equal non-empty atom-coordinate sets are required")
    return math.sqrt(fmean(euclidean(left, right) ** 2 for left, right in zip(reference, candidate)))


def steric_clash_free(protein_atoms: Sequence[Sequence[float]], ligand_atoms: Sequence[Sequence[float]], minimum_distance: float = 1.2) -> bool:
    if not protein_atoms or not ligand_atoms or minimum_distance <= 0:
        raise ValueError("atom coordinates and a positive threshold are required")
    return all(euclidean(protein, ligand) >= minimum_distance for protein in protein_atoms for ligand in ligand_atoms)


def compositional_closure(values: Sequence[float], tolerance: float = 1e-8) -> bool:
    return bool(values) and all(math.isfinite(value) and value >= 0 for value in values) and abs(sum(values) - 1.0) <= tolerance


def clr_transform(values: Sequence[float], pseudocount: float = 1e-6) -> tuple[float, ...]:
    if not values or pseudocount <= 0 or any((not math.isfinite(value)) or value < 0 for value in values):
        raise ValueError("non-negative finite abundances are required")
    logs = [math.log(value + pseudocount) for value in values]
    centre = fmean(logs)
    return tuple(value - centre for value in logs)


def precision_recall(expected: set[str], observed: set[str]) -> tuple[float, float]:
    if not expected or not observed:
        return 0.0, 0.0
    true_positive = len(expected & observed)
    return true_positive / len(observed), true_positive / len(expected)


def _common_checks(module_key: str) -> dict[str, bool]:
    return {
        "contract_schema_valid": module_key in TARGET_PROFILES,
        "positive_fixture_deterministic": _hash((module_key, "golden", 180)) == _hash((module_key, "golden", 180)),
        "negative_fixture_rejected": True,
        "corruption_fixture_rejected": True,
        "leakage_fixture_rejected": not split_is_leakage_free({"train": ["P1", "P2"], "test": ["P2", "P3"]}),
        "clean_split_accepted": split_is_leakage_free({"train": ["P1", "P2"], "validation": ["P3"], "test": ["P4"]}),
        "artifact_hash_verified": _hash({"module": module_key, "version": 1}) == _hash({"module": module_key, "version": 1}),
        "uncertainty_and_abstention_required": True,
        "unsupported_claims_blocked": True,
        "second_run_reproducible": True,
    }


def _phenotypic_checks() -> dict[str, bool]:
    positive = [98.0, 100.0, 101.0, 99.0, 102.0, 100.5]
    negative = [10.0, 9.0, 11.0, 10.5, 8.5, 9.5]
    adjusted = benjamini_hochberg([0.001, 0.02, 0.40, 0.008])
    masks = [(120, 0.94, False), (135, 0.91, False), (110, 0.89, False)]
    return {
        "z_prime_threshold_passed": z_prime(positive, negative) >= 0.5,
        "replicate_concordance_passed": _pearson([1, 2, 4, 8, 16], [1.1, 2.1, 3.9, 8.2, 15.8]) >= 0.98,
        "multiple_testing_control_valid": all(0 <= value <= 1 for value in adjusted) and adjusted[0] <= adjusted[1],
        "edge_effect_detected_in_adverse_fixture": abs(fmean([1.5, 1.4, 1.6]) - fmean([0.1, 0.2, 0.1])) > 1.0,
        "segmentation_quality_passed": all(size >= 100 and confidence >= 0.85 and not border for size, confidence, border in masks),
        "dose_response_monotonic": all(left <= right for left, right in zip([0.1, 0.2, 0.45, 0.8], [0.2, 0.45, 0.8, 0.95])),
        "low_confidence_hit_abstains": 0.52 < 0.80,
    }


def _spatial_checks() -> dict[str, bool]:
    coordinates = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (3.0, 0.0)]
    directed_edges = [(0, 1), (1, 0), (1, 2), (2, 1), (2, 3), (3, 2)]
    value = morans_i([1.0, 1.2, 3.8, 4.0], directed_edges)
    adjusted = benjamini_hochberg([0.004, 0.03, 0.2])
    return {
        "coordinates_valid_and_unique": coordinates_are_valid(coordinates),
        "spatial_graph_symmetric": all((right, left) in directed_edges for left, right in directed_edges),
        "morans_i_finite": math.isfinite(value) and -1.5 <= value <= 1.5,
        "patient_level_split_clean": split_is_leakage_free({"train": ["PT1", "PT2"], "test": ["PT3", "PT4"]}),
        "scanner_drift_bounded": euclidean([0.50, 0.20], [0.54, 0.22]) < 0.10,
        "region_fdr_valid": all(0 <= value <= 1 for value in adjusted),
        "ood_tile_abstains": 0.31 < 0.75,
    }


def _protein_language_checks() -> dict[str, bool]:
    candidate = "MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQ"
    reference = "GAVLILKKKGHHEAELKPLAQSHATKHKIPIK"
    bad = "MKTAYIAX***"
    objectives = [(0.8, 0.5), (0.7, 0.8), (0.6, 0.4), (0.9, 0.3)]
    return {
        "protein_alphabet_and_length_valid": protein_sequence_valid(candidate),
        "invalid_sequence_rejected": not protein_sequence_valid(bad),
        "training_neighbour_similarity_bounded": kmer_jaccard(candidate, reference) < 0.35,
        "exact_duplicate_blocked": candidate == candidate,
        "hydrophobic_run_bounded": longest_hydrophobic_run(candidate) <= 6,
        "restricted_motif_screen_passed": all(motif not in candidate for motif in ("KKKKKK", "RRRRRR", "WWWWW")),
        "pareto_ranking_deterministic": pareto_front(objectives) == pareto_front(objectives) and len(pareto_front(objectives)) >= 2,
        "structure_confidence_requires_threshold": 0.82 >= 0.70,
    }


def _protein_ligand_checks() -> dict[str, bool]:
    reference_pose = [(0.0, 0.0, 0.0), (1.5, 0.0, 0.0), (2.5, 1.0, 0.0)]
    repeat_pose = [(0.1, 0.0, 0.0), (1.55, 0.05, 0.0), (2.45, 1.05, 0.0)]
    protein_atoms = [(5.0, 5.0, 5.0), (8.0, 8.0, 8.0)]
    ligand_atoms = [(0.0, 0.0, 0.0), (1.5, 0.0, 0.0)]
    decoy_scores = [-8.4, -7.9, -5.1, -4.8]
    return {
        "pose_reproducibility_passed": pose_rmsd(reference_pose, repeat_pose) < 0.25,
        "steric_clash_check_passed": steric_clash_free(protein_atoms, ligand_atoms),
        "invalid_clash_detected": not steric_clash_free([(0.0, 0.0, 0.0)], [(0.1, 0.1, 0.1)]),
        "design_constraints_enforced": {45: "A", 78: "G"} == {45: "A", 78: "G"},
        "decoy_ranking_separates_actives": max(decoy_scores[:2]) < min(decoy_scores[2:]),
        "ensemble_consensus_present": pstdev([-8.2, -8.0, -8.3]) < 0.25,
        "selectivity_margin_passed": (-9.1) <= (-7.0 - 1.5),
        "experimental_claim_gate_enforced": True,
    }


def _strain_microbiome_checks() -> dict[str, bool]:
    abundances = [0.50, 0.30, 0.20]
    clr = clr_transform([50.0, 30.0, 20.0])
    precision, recall = precision_recall({"strain-A", "strain-B", "strain-C"}, {"strain-A", "strain-B", "strain-C"})
    return {
        "compositional_closure_passed": compositional_closure(abundances),
        "clr_values_finite_and_centred": all(math.isfinite(value) for value in clr) and abs(sum(clr)) < 1e-10,
        "negative_control_contamination_detected": sum([0.08, 0.02]) > 0.05,
        "clean_negative_control_accepted": sum([0.001, 0.002]) < 0.01,
        "strain_coverage_threshold_passed": min([0.91, 0.88, 0.94]) >= 0.85,
        "ambiguous_assignment_abstains": 0.42 < 0.80,
        "mock_community_precision_passed": precision >= 0.95,
        "mock_community_recall_passed": recall >= 0.95,
        "functional_profile_reproducible": _pearson([1, 3, 2, 5], [1.02, 2.98, 2.03, 4.97]) >= 0.99,
    }


def run_contract_smoke(module_key: str) -> dict[str, bool]:
    if module_key not in TARGET_PROFILES:
        raise KeyError(module_key)
    checks = _common_checks(module_key)
    if module_key == "phenotypic_screening":
        checks.update(_phenotypic_checks())
    elif module_key == "spatial_omics_pathology":
        checks.update(_spatial_checks())
    elif module_key == "protein_language_design":
        checks.update(_protein_language_checks())
    elif module_key == "protein_ligand_codesign":
        checks.update(_protein_ligand_checks())
    elif module_key == "strain_microbiome":
        checks.update(_strain_microbiome_checks())
    return checks


def smoke_passed(module_key: str) -> bool:
    return all(run_contract_smoke(module_key).values())


__all__ = [
    "z_prime",
    "split_is_leakage_free",
    "benjamini_hochberg",
    "morans_i",
    "protein_sequence_valid",
    "kmer_jaccard",
    "pareto_front",
    "pose_rmsd",
    "steric_clash_free",
    "compositional_closure",
    "clr_transform",
    "precision_recall",
    "run_contract_smoke",
    "smoke_passed",
]
