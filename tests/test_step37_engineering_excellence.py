from __future__ import annotations

from pathlib import Path

from biointel.engineering import build_engineering_readiness, run_engineering_gates
from biointel.engineering.release import build_reproducible_release, verify_release_bundle
from biointel.production.scaling import validate_horizontal_scaling

ROOT = Path(__file__).resolve().parents[1]


def test_engineering_readiness_is_complete() -> None:
    report = build_engineering_readiness(ROOT)
    failed = {
        a["label"]: a["failed_controls"] for a in report["areas"] if a["implementation_score"] < 10
    }
    assert report["all_targets_complete"], failed
    assert report["implementation_average"] == 10.0


def test_engineering_quality_gates_pass() -> None:
    report = run_engineering_gates(ROOT)
    assert report["passed"], report


def test_reproducible_release_bundle(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "a.txt").write_text("alpha")
    (source / "b.txt").write_text("beta")
    one = build_reproducible_release(source, tmp_path / "one.zip")
    two = build_reproducible_release(source, tmp_path / "two.zip")
    assert one.read_bytes() == two.read_bytes()
    assert verify_release_bundle(one)["valid"]


def test_horizontal_scaling_contract() -> None:
    report = validate_horizontal_scaling()
    assert report["ready"]
    assert report["profile"]["api_max_replicas"] >= 20


def test_architecture_rules_are_valid() -> None:
    gates = run_engineering_gates(ROOT)
    item = next(x for x in gates["results"] if x["name"] == "architecture_boundaries")
    assert item["passed"], item
