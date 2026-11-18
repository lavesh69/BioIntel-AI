from __future__ import annotations
import argparse, json, py_compile
from pathlib import Path
from biointel.priority_v166 import ensure_step166_assets, six_module_matrix
from biointel.scientific_depth import native_input_template, run_native_workflow

TARGETS=("epigenomics_chromatin","long_read_core","one_health_environmental","pangenome_core","strain_microbiome","structural_variant_repeat")
EXPECTED={
"epigenomics_chromatin":"step166_epigenomics_consensus_peaks",
"long_read_core":"step166_long_read_read_quality_summary",
"one_health_environmental":"step166_one_health_contamination_screen",
"pangenome_core":"step166_pangenome_input_and_graph_readiness",
"strain_microbiome":"step166_strain_confidence_and_contamination",
"structural_variant_repeat":"step166_structural_variant_evidence_summary",
}

def main() -> int:
    parser=argparse.ArgumentParser();parser.add_argument('--root',default='.');args=parser.parse_args();root=Path(args.root).resolve()
    ensure_step166_assets(root); failures=[]; runs=[]
    for key in TARGETS:
        try:
            result=run_native_workflow(key,native_input_template(key,demonstration=True),metadata={'project_root':str(root)})
            ok=('step166_six_module_excellence_gate' in result.tables and EXPECTED[key] in result.tables and result.summary.get('step166_six_module_software_score')==10.0 and result.summary.get('step166_native_research_depth_score')==10.0)
            runs.append({'module_key':key,'status':result.status,'passed':ok,'tables':len(result.tables)})
            if not ok: failures.append(f'{key}: missing Step 166 focused outputs')
        except Exception as exc: failures.append(f'{key}: {type(exc).__name__}: {exc}')
    compile_fail=[]
    paths=sorted([*root.joinpath('src').rglob('*.py'),*root.joinpath('pages').glob('*.py')])
    for path in paths:
        try: py_compile.compile(str(path),doraise=True)
        except Exception as exc: compile_fail.append({'path':str(path.relative_to(root)),'error':str(exc)})
    matrix=six_module_matrix(root)
    payload={'schema':'biointel.step166.validation.v1','status':'passed' if not failures and not compile_fail else 'failed','priority_modules':6,'software_10of10':int((matrix.software_score==10).sum()),'native_depth_10of10':int((matrix.native_research_depth_score==10).sum()),'module_runs':runs,'python_files_compiled':len(paths),'module_failures':failures,'compile_failures':compile_fail,'external_evidence_not_inferred':True}
    reports=root/'reports';reports.mkdir(exist_ok=True);(reports/'step166_validation.json').write_text(json.dumps(payload,indent=2)+'\n')
    print(json.dumps(payload,indent=2));return 0 if payload['status']=='passed' else 1
if __name__=='__main__':raise SystemExit(main())
