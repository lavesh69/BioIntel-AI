from __future__ import annotations

import base64
import json
import py_compile
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.io import mmwrite
from scipy.sparse import coo_matrix

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
import sys
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.native.engines import ENGINE_REGISTRY, build_engine_plan, engine_status_matrix, plan_catalog
from biointel.native.formats import NATIVE_FORMATS, parse_native_path
from biointel.native.viewers import build_native_viewer_visuals
from biointel.statistics.rigor import benjamini_hochberg, two_group_disclosure
from biointel.ui.viewer_sync import ViewerSelection, ViewerSyncStore, apply_selection_to_visual


def _write_fcs(path: Path) -> None:
    text = "|$TOT|3|$PAR|2|$DATATYPE|F|$BYTEORD|1,2,3,4|$P1B|32|$P2B|32|$P1N|FSC-A|$P2N|SSC-A|"
    text_start = 58
    text_end = text_start + len(text.encode("latin-1")) - 1
    data_start = text_end + 1
    data = np.asarray([[1, 2], [3, 4], [5, 6]], dtype="<f4").tobytes()
    data_end = data_start + len(data) - 1
    header = f"FCS3.0    {text_start:>8}{text_end:>8}{data_start:>8}{data_end:>8}{0:>8}{0:>8}".encode("ascii")
    path.write_bytes(header + text.encode("latin-1") + data)


def _encoded(values: list[float]) -> str:
    return base64.b64encode(np.asarray(values, dtype="<f8").tobytes()).decode("ascii")


def _fixtures(directory: Path) -> list[tuple[str, str, str]]:
    files: list[tuple[str, str, str]] = []
    def text(name: str, content: str, viewer: str, key: str) -> None:
        path = directory / name
        path.write_text(content, encoding="utf-8")
        files.append((name, viewer, key))

    text("sequence.fa", ">seq1\nACGTACGTNN\n", "sequence_track", "fasta")
    text("reads.fastq", "@r1\nACGT\n+\nIIII\n", "genome_browser", "fastq")
    text("variants.vcf", "##fileformat=VCFv4.2\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n1\t10\trs1\tA\tG\t50\tPASS\tAF=0.1;DP=30\n", "genome_browser", "vcf")
    text("regions.bed", "chr1\t0\t10\tregion1\t5\t+\n", "genome_browser", "bed")
    text("features.gff", "chr1\tsrc\tgene\t5\t15\t.\t+\t.\tID=g1;Name=GENE1\n", "genome_browser", "gff")
    text("alignments.sam", "@HD\tVN:1.6\n@SQ\tSN:chr1\tLN:100\nr1\t0\tchr1\t1\t60\t4M\t*\t0\t0\tACGT\tIIII\n", "genome_browser", "sam")
    (directory / "sample.bam").write_bytes(b"BAM\x01")
    files.append(("sample.bam", "genome_browser", "bam"))
    (directory / "sample.cram").write_bytes(b"CRAM\x03\x00")
    files.append(("sample.cram", "genome_browser", "cram"))
    text("structure.pdb", "ATOM      1  N   ALA A   1      11.104  13.207   9.173  1.00 20.00           N  \nATOM      2  CA  ALA A   1      12.560  13.307   9.173  1.00 21.00           C  \nEND\n", "molecular_3d", "pdb")
    text("structure.cif", """data_test
#
loop_
_atom_site.group_PDB
_atom_site.id
_atom_site.type_symbol
_atom_site.label_atom_id
_atom_site.label_alt_id
_atom_site.label_comp_id
_atom_site.label_asym_id
_atom_site.label_entity_id
_atom_site.label_seq_id
_atom_site.pdbx_PDB_ins_code
_atom_site.Cartn_x
_atom_site.Cartn_y
_atom_site.Cartn_z
_atom_site.occupancy
_atom_site.B_iso_or_equiv
_atom_site.pdbx_formal_charge
_atom_site.auth_seq_id
_atom_site.auth_comp_id
_atom_site.auth_asym_id
_atom_site.auth_atom_id
_atom_site.pdbx_PDB_model_num
ATOM 1 N N . ALA A 1 1 ? 11.104 13.207 9.173 1.00 20.00 ? 1 ALA A N 1
ATOM 2 C CA . ALA A 1 1 ? 12.560 13.307 9.173 1.00 21.00 ? 1 ALA A CA 1
#
""", "molecular_3d", "mmcif")

    from PIL import Image
    Image.fromarray(np.asarray([[0, 100], [200, 255]], dtype=np.uint8)).save(directory / "image.tif")
    files.append(("image.tif", "microscopy", "image"))
    _write_fcs(directory / "events.fcs")
    files.append(("events.fcs", "flow_gating", "fcs"))
    text("peaks.mzML", f'''<?xml version="1.0"?><mzML xmlns="http://psi.hupo.org/ms/mzml"><run><spectrumList count="1"><spectrum id="scan=1"><cvParam accession="MS:1000511" value="1"/><binaryDataArrayList count="2"><binaryDataArray><cvParam accession="MS:1000514"/><cvParam accession="MS:1000523"/><binary>{_encoded([100.0, 200.0])}</binary></binaryDataArray><binaryDataArray><cvParam accession="MS:1000515"/><cvParam accession="MS:1000523"/><binary>{_encoded([10.0, 20.0])}</binary></binaryDataArray></binaryDataArrayList></spectrum></spectrumList></run></mzML>''', "mass_spectrometry", "mzml")
    text("peaks.mgf", "BEGIN IONS\nTITLE=scan1\nPEPMASS=500.2\n100.0 10\n200.0 20\nEND IONS\n", "mass_spectrometry", "mgf")
    text("tree.nwk", "((A:0.1,B:0.2):0.1,C:0.3);", "phylogenetic_tree", "newick")
    text("tree.nex", "#NEXUS\nBegin trees;\nTree tree1 = ((A:0.1,B:0.2):0.1,C:0.3);\nEnd;\n", "phylogenetic_tree", "nexus")
    text("plate.csv", "well,sample,value\nA01,S1,1\nA02,S2,2\n", "plate_map", "plate")
    text("family.ped", "FAM I1 0 0 1 2\nFAM I2 0 0 2 1\n", "pedigree", "ped")
    text("graph.gfa", "S\tn1\tACGT\nS\tn2\tTTAA\nL\tn1\t+\tn2\t+\t0M\n", "pangenome_graph", "gfa")

    import h5py
    with h5py.File(directory / "cells.h5ad", "w") as h5:
        obs = h5.create_group("obs")
        obs.create_dataset("_index", data=np.asarray([b"c1", b"c2", b"c3"]))
        obs.create_dataset("cluster", data=np.asarray([b"A", b"B", b"A"]))
        var = h5.create_group("var")
        var.create_dataset("_index", data=np.asarray([b"g1", b"g2"]))
        obsm = h5.create_group("obsm")
        obsm.create_dataset("X_umap", data=np.asarray([[0.0, 0.1], [1.0, 1.1], [2.0, 2.1]]))
    files.append(("cells.h5ad", "single_cell", "h5ad"))

    mmwrite(directory / "matrix.mtx", coo_matrix(np.asarray([[1, 0], [0, 2], [3, 0]])))
    files.append(("matrix.mtx", "single_cell", "mtx"))
    text("workflow.json", json.dumps({"nodes": [{"id": "n1", "label": "Input"}, {"id": "n2", "label": "QC"}], "edges": [{"source": "n1", "target": "n2"}]}), "workflow_dag", "workflow_json")
    text("table.csv", "source,target,value\nGeneA,ProteinA,1.0\nProteinA,MetaboliteA,0.8\n", "multiomics", "tabular")
    return files


def run() -> dict[str, object]:
    generated = datetime.now(UTC).isoformat()
    checks: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="biointel-step111-verify-") as temp:
        directory = Path(temp)
        fixtures = _fixtures(directory)
        for name, viewer, expected in fixtures:
            entry: dict[str, object] = {"file": name, "viewer": viewer, "expected_format": expected}
            try:
                result = parse_native_path(directory / name, preferred_viewer=viewer)
                visuals = build_native_viewer_visuals(viewer, result)
                entry.update({
                    "passed": result.format_key == expected and bool(visuals),
                    "detected_format": result.format_key,
                    "native_level": result.native_level,
                    "engine_required": result.engine_required,
                    "records": result.record_count,
                    "visuals": len(visuals),
                    "sha256_length": len(result.sha256),
                    "warnings": result.warnings,
                })
            except Exception as exc:
                entry.update({"passed": False, "error": f"{type(exc).__name__}: {exc}"})
            checks.append(entry)

        plan_dir = directory / "engine"
        plan_dir.mkdir()
        (plan_dir / "sample.bam").write_bytes(b"BAM\x01")
        plan = build_engine_plan("samtools_index", workdir=plan_dir, alignment=plan_dir / "sample.bam", threads=2)

        stats = pd.DataFrame({"group": ["A", "A", "A", "B", "B", "B"], "value": [1.0, 1.3, 1.8, 2.8, 3.2, 3.7], "bio": ["a1", "a2", "a3", "b1", "b2", "b3"]})
        disclosure = two_group_disclosure(stats, value_column="value", group_column="group", biological_id_column="bio")

        sync = ViewerSyncStore(directory / "viewer_sync.sqlite3")
        event = ViewerSelection(event_id="verify-event", project_key="verify-project", source_viewer="genome_browser", entity_type="variant", entity_ids=("rs1",), coordinates={"start": 5, "end": 15}, filters={}, analysis_run_id="verify-run", created_at_utc=generated)
        sync.publish(event)
        sync.save_state(project_key="verify-project", viewer_key="genome_browser", state={"range": [5, 15]})

        compile_targets = [
            ROOT / "pages/166_Real_Engine_Native_Format_Integration.py",
            ROOT / "src/biointel/native/formats.py",
            ROOT / "src/biointel/native/engines.py",
            ROOT / "src/biointel/native/viewers.py",
            ROOT / "src/biointel/statistics/rigor.py",
            ROOT / "src/biointel/ui/viewer_sync.py",
            ROOT / "src/biointel/jobs/worker.py",
        ]
        compiled = []
        for target in compile_targets:
            py_compile.compile(str(target), doraise=True)
            compiled.append(str(target.relative_to(ROOT)))

        engine_status = engine_status_matrix()
        return {
            "schema": "biointel.step111.native-integration-verification.v1",
            "version": (ROOT / "VERSION").read_text(encoding="utf-8").strip(),
            "generated_at_utc": generated,
            "status": "PASS" if all(bool(item.get("passed")) for item in checks) else "FAIL",
            "native_format_catalog_count": len(NATIVE_FORMATS),
            "native_fixtures_tested": len(checks),
            "native_fixtures_passed": sum(bool(item.get("passed")) for item in checks),
            "native_checks": checks,
            "engine_registry_count": len(ENGINE_REGISTRY),
            "engine_plan_count": len(plan_catalog()),
            "engine_detection": engine_status.to_dict(orient="records"),
            "safe_plan": {"key": plan.plan_key, "command": list(plan.command), "cwd": plan.cwd, "shell_free": not any(token in {"|", ">", "&&", ";"} for token in plan.command)},
            "statistical_disclosure": disclosure.to_dict(),
            "bh_adjusted": benjamini_hochberg([0.001, 0.02, 0.04, 0.2]).tolist(),
            "viewer_sync": {"events": len(sync.history("verify-project")), "states": len(sync.states("verify-project"))},
            "compiled_targets": compiled,
        }


def main() -> int:
    result = run()
    output = ROOT / "reports" / "step111_native_integration_verification.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, default=str))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
