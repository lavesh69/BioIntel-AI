from __future__ import annotations

from pathlib import Path

import joblib

from biointel.discovery.preparation import prepare_molecular_states
from biointel.sequence.advanced import near_duplicate_clusters, semiglobal_alignment
from biointel.sequence.parser import ParsedSequence
from biointel.training.model_artifact import discover_compatible_model_artifacts
from biointel.ui.runtime_guard import _is_transient_key


def _brute_components(records: list[ParsedSequence], threshold: float, k: int = 7) -> list[int]:
    fps = []
    for record in records:
        seq = record.sequence.upper()
        fps.append({seq[i : i + k] for i in range(max(1, len(seq) - k + 1))})
    parent = list(range(len(records)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        a, b = find(a), find(b)
        if a != b:
            parent[b] = a

    for left in range(len(records)):
        for right in range(left + 1, len(records)):
            a, b = fps[left], fps[right]
            union_size = len(a | b)
            similarity = len(a & b) / union_size if union_size else 1.0
            if similarity >= threshold:
                union(left, right)
    return [find(i) for i in range(len(records))]


def test_indexed_near_duplicate_clustering_matches_bruteforce_partition() -> None:
    records = [
        ParsedSequence("a", "ACGTACGTACGT"),
        ParsedSequence("b", "ACGTACGTACGA"),
        ParsedSequence("c", "TTTTTTTTTTTT"),
        ParsedSequence("d", "ACGTACGTACGT"),
        ParsedSequence("e", "GGGGGGGGGGGG"),
    ]
    threshold = 0.70
    expected = _brute_components(records, threshold)
    actual = near_duplicate_clusters(records, identity_threshold=threshold)
    labels = actual["cluster"].tolist()
    for i in range(len(records)):
        for j in range(len(records)):
            assert (expected[i] == expected[j]) == (labels[i] == labels[j])


def test_semiglobal_alignment_returns_complete_metrics() -> None:
    result = semiglobal_alignment("ACGT", "TTACGTA")
    assert result["mode"] == "semi-global"
    assert result["alignment_length"] > 0
    assert result["identities"] >= 4
    assert result["query_coverage_percent"] >= 99.0
    assert result["aligned_query"]
    assert result["aligned_target"]


def test_assay_ph_is_applied_to_preparation_context() -> None:
    context = prepare_molecular_states(
        "CC(=O)O", mode="assay_context", ph=6.5, max_tautomers=4
    )
    assert context.requested_ph == 6.5
    assert context.mode == "assay_context"


def test_incompatible_plain_joblib_is_excluded(tmp_path: Path) -> None:
    joblib.dump({"plain": "benchmark"}, tmp_path / "benchmark.joblib")
    compatible, rejected = discover_compatible_model_artifacts(tmp_path)
    assert compatible == []
    assert "benchmark.joblib" in rejected


def test_release_healing_preserves_preferences_and_targets_results() -> None:
    assert not _is_transient_key("ui_palette")
    assert not _is_transient_key("active_project")
    assert _is_transient_key("step59_vcf_data")
    assert _is_transient_key("admet_profile_result")


def test_heavy_and_dynamic_pages_include_crash_guards() -> None:
    root = Path(__file__).resolve().parents[1]
    batch = (root / "pages/16_Batch_Sequence_Analysis.py").read_text(encoding="utf-8")
    primer = (root / "pages/58_Primer_CRISPR_Codon_Studio.py").read_text(encoding="utf-8")
    variant = (root / "pages/57_Variant_Annotation_Workbench.py").read_text(encoding="utf-8")
    comparison = (root / "pages/2_Sequence_Comparison.py").read_text(encoding="utf-8")
    assert "Run deduplication and near-duplicate clustering" in batch
    assert 'key="primer_target_start"' in primer
    assert 'if load_gff:' in variant
    assert "alignment_modes.index(default_mode)" in comparison
