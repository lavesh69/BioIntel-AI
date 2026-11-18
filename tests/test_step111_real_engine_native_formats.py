from __future__ import annotations

import base64
import json
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from biointel.native.engines import ENGINE_REGISTRY, build_engine_plan, detect_engine, plan_catalog
from biointel.native.formats import (
    NATIVE_FORMATS,
    detect_native_format,
    format_matrix,
    parse_native_path,
    supported_extensions_for_viewer,
)
from biointel.native.viewers import build_native_viewer_visuals
from biointel.statistics.rigor import (
    benjamini_hochberg,
    bootstrap_confidence_interval,
    dataframe_hash,
    infer_visual_statistics,
    two_group_disclosure,
)
from biointel.ui.navigation import PAGE_BY_KEY
from biointel.ui.viewer_sync import ViewerSelection, ViewerSyncStore, apply_selection_to_visual

ROOT = Path(__file__).resolve().parents[1]


def _fixture_directory() -> Path:
    return Path(tempfile.mkdtemp(prefix="biointel-step111-test-"))


def test_step111_version_and_navigation() -> None:
    version = tuple(int(part) for part in (ROOT / "VERSION").read_text(encoding="utf-8").strip().split("."))
    assert version >= (11, 1, 0)
    version_text = ".".join(str(part) for part in version)
    assert f'version = "{version_text}"' in (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert f'__version__ = "{version_text}"' in (ROOT / "src/biointel/__init__.py").read_text(encoding="utf-8")
    page = PAGE_BY_KEY["real_engine_native_formats"]
    assert page.path == "pages/166_Real_Engine_Native_Format_Integration.py"
    assert (ROOT / page.path).exists()


def test_native_format_catalog_and_detection() -> None:
    assert len(NATIVE_FORMATS) >= 20
    matrix = format_matrix()
    assert not matrix.empty
    assert {"Native level", "Optional engine", "Viewers"}.issubset(matrix.columns)
    assert detect_native_format("sample.vcf.gz", b"##fileformat=VCFv4.2") == "vcf"
    assert detect_native_format("sample.fcs", b"FCS3.0") == "fcs"
    assert "fcs" in supported_extensions_for_viewer("flow_gating")
    assert "mzml" in supported_extensions_for_viewer("mass_spectrometry")
    assert "bam" in supported_extensions_for_viewer("genome_browser")


def test_native_sequence_variant_structure_tree_and_graph_parsers() -> None:
    directory = _fixture_directory()
    fixtures = {
        "sequence.fa": (">seq1\nACGTACGTNN\n", "sequence_track", "fasta"),
        "variants.vcf": (
            "##fileformat=VCFv4.2\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
            "1\t10\trs1\tA\tG\t50\tPASS\tAF=0.1;DP=30\n",
            "genome_browser",
            "vcf",
        ),
        "features.gff": ("chr1\tsrc\tgene\t5\t15\t.\t+\t.\tID=g1;Name=GENE1\n", "genome_browser", "gff"),
        "structure.pdb": (
            "ATOM      1  N   ALA A   1      11.104  13.207   9.173  1.00 20.00           N  \n"
            "ATOM      2  CA  ALA A   1      12.560  13.307   9.173  1.00 21.00           C  \nEND\n",
            "molecular_3d",
            "pdb",
        ),
        "tree.nwk": ("((A:0.1,B:0.2):0.1,C:0.3);", "phylogenetic_tree", "newick"),
        "graph.gfa": ("S\tn1\tACGT\nS\tn2\tTTAA\nL\tn1\t+\tn2\t+\t0M\n", "pangenome_graph", "gfa"),
    }
    for name, (text, viewer, expected_format) in fixtures.items():
        path = directory / name
        path.write_text(text, encoding="utf-8")
        result = parse_native_path(path, preferred_viewer=viewer)
        assert result.format_key == expected_format
        assert not result.primary.empty
        assert len(result.sha256) == 64
        visuals = build_native_viewer_visuals(viewer, result)
        assert visuals
        assert all(not visual.data.empty for visual in visuals)


def test_native_fcs_and_mzml_parsers() -> None:
    directory = _fixture_directory()
    text = "|$TOT|3|$PAR|2|$DATATYPE|F|$BYTEORD|1,2,3,4|$P1B|32|$P2B|32|$P1N|FSC-A|$P2N|SSC-A|"
    text_start = 58
    text_end = text_start + len(text.encode("latin-1")) - 1
    data_start = text_end + 1
    data = np.array([[1, 2], [3, 4], [5, 6]], dtype="<f4").tobytes()
    data_end = data_start + len(data) - 1
    header = f"FCS3.0    {text_start:>8}{text_end:>8}{data_start:>8}{data_end:>8}{0:>8}{0:>8}".encode("ascii")
    fcs = directory / "events.fcs"
    fcs.write_bytes(header + text.encode("latin-1") + data)
    result = parse_native_path(fcs, preferred_viewer="flow_gating")
    assert result.primary.shape == (3, 2)
    assert result.metadata["events"] == 3
    assert build_native_viewer_visuals("flow_gating", result)

    def encoded(values: list[float]) -> str:
        return base64.b64encode(np.asarray(values, dtype="<f8").tobytes()).decode("ascii")

    mzml = directory / "peaks.mzML"
    mzml.write_text(
        f'''<?xml version="1.0"?><mzML xmlns="http://psi.hupo.org/ms/mzml"><run><spectrumList count="1"><spectrum id="scan=1"><cvParam accession="MS:1000511" value="1"/><binaryDataArrayList count="2"><binaryDataArray><cvParam accession="MS:1000514"/><cvParam accession="MS:1000523"/><binary>{encoded([100.0, 200.0])}</binary></binaryDataArray><binaryDataArray><cvParam accession="MS:1000515"/><cvParam accession="MS:1000523"/><binary>{encoded([10.0, 20.0])}</binary></binaryDataArray></binaryDataArrayList></spectrum></spectrumList></run></mzML>''',
        encoding="utf-8",
    )
    mass = parse_native_path(mzml, preferred_viewer="mass_spectrometry")
    assert mass.primary.shape[0] == 2
    assert {"mz", "intensity"}.issubset(mass.primary.columns)
    assert build_native_viewer_visuals("mass_spectrometry", mass)


def test_engine_registry_and_shell_free_plan() -> None:
    assert len(ENGINE_REGISTRY) >= 20
    assert len(plan_catalog()) >= 10
    status = detect_engine("samtools")
    assert status.key == "samtools"
    directory = _fixture_directory()
    alignment = directory / "sample.bam"
    alignment.write_bytes(b"BAM\x01")
    plan = build_engine_plan("samtools_index", workdir=directory, alignment=alignment, threads=2)
    assert plan.command[1] == "index"
    assert not any(token in {"|", ">", "&&", ";"} for token in plan.command)
    assert Path(plan.cwd) == directory.resolve()


def test_engine_plan_rejects_path_escape() -> None:
    directory = _fixture_directory()
    outside = directory.parent / "outside.bam"
    outside.write_bytes(b"BAM\x01")
    try:
        build_engine_plan("samtools_index", workdir=directory, alignment=outside)
    except ValueError as exc:
        assert "outside the protected" in str(exc)
    else:
        raise AssertionError("Path escape was not rejected")


def test_statistical_rigor_and_nested_hashing() -> None:
    frame = pd.DataFrame(
        {
            "group": ["A", "A", "A", "B", "B", "B"],
            "value": [1.0, 1.5, 2.0, 3.0, 3.5, 4.0],
            "biological_id": ["a1", "a2", "a3", "b1", "b2", "b3"],
            "nested": [[1], {"x": 2}, None, "a", (1, 2), {"z"}],
        }
    )
    digest = dataframe_hash(frame)
    assert len(digest) == 64
    disclosure = two_group_disclosure(
        frame,
        value_column="value",
        group_column="group",
        biological_id_column="biological_id",
    )
    assert disclosure.test_name == "Welch t-test"
    assert disclosure.effect_size is not None
    assert disclosure.confidence_interval[0] is not None
    assert disclosure.biological_replicates == 6
    footer = infer_visual_statistics(frame)
    assert footer["Displayed rows"] == 6
    adjusted = benjamini_hochberg([0.001, 0.02, 0.04, 0.2])
    assert np.all(np.diff(np.sort(adjusted)) >= -1e-12)
    low, high = bootstrap_confidence_interval(frame["value"], iterations=200, seed=7)
    assert low is not None and high is not None and low < high


def test_viewer_sync_store_persists_selection_and_state() -> None:
    directory = _fixture_directory()
    store = ViewerSyncStore(directory / "sync.sqlite3")
    selection = ViewerSelection(
        event_id="event-1",
        project_key="project-a",
        source_viewer="genome_browser",
        entity_type="variant",
        entity_ids=("v1", "v2"),
        coordinates={"chrom": "1", "start": 100, "end": 200},
        filters={"impact": "HIGH"},
        analysis_run_id="run-1",
        created_at_utc="2026-07-10T00:00:00+00:00",
    )
    store.publish(selection)
    latest = store.latest("project-a")
    assert latest is not None
    assert latest.entity_ids == ("v1", "v2")
    snapshot = store.save_state(project_key="project-a", viewer_key="genome_browser", state={"zoom": [100, 200]})
    assert snapshot.startswith("vstate-")
    assert len(store.history("project-a")) == 1
    assert len(store.states("project-a")) == 1


def test_viewer_selection_applies_focus_and_highlight() -> None:
    import plotly.express as px

    frame = pd.DataFrame({"variant_id": ["v1", "v2", "v3"], "position": [100, 200, 300], "score": [1.0, 2.0, 3.0]})
    figure = px.scatter(frame, x="position", y="score")
    selection = ViewerSelection(
        event_id="event-focus", project_key="p", source_viewer="pedigree", entity_type="variant",
        entity_ids=("v2",), coordinates={"start": 190, "end": 210}, filters={},
        analysis_run_id="", created_at_utc="2026-07-10T00:00:00+00:00",
    )
    focused, linked, note = apply_selection_to_visual(figure, frame, selection)
    assert "_linked_selection" in linked.columns
    assert int(linked["_linked_selection"].sum()) == 1
    assert note and "highlighted" in note
    assert focused.layout.xaxis.range is not None
