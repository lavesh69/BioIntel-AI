from __future__ import annotations
import argparse, json, py_compile
from pathlib import Path
from biointel.priority_v165 import ensure_step165_assets, priority_matrix
from biointel.scientific_depth import native_input_template, run_native_workflow
TARGETS=("amr_surveillance","protein_ligand_codesign","long_read_epigenome")
EXPECTED={"amr_surveillance":"step165_amr_confirmatory_metrics","protein_ligand_codesign":"step165_codesign_consensus_ranking","long_read_epigenome":"step165_long_read_input_readiness"}

def main()->int:
 p=argparse.ArgumentParser();p.add_argument('--root',default='.');a=p.parse_args();root=Path(a.root).resolve()
 ensure_step165_assets(root); failures=[]; runs=[]
 for key in TARGETS:
  try:
   result=run_native_workflow(key,native_input_template(key,demonstration=True),metadata={'project_root':str(root)})
   ok=('step165_priority_module_gate' in result.tables and EXPECTED[key] in result.tables and result.summary.get('step165_priority_module_software_score')==10.0)
   runs.append({'module_key':key,'status':result.status,'passed':ok,'tables':len(result.tables)})
   if not ok: failures.append(f'{key}: missing focused outputs')
  except Exception as exc: failures.append(f'{key}: {type(exc).__name__}: {exc}')
 compile_fail=[]
 for path in sorted([*root.joinpath('src').rglob('*.py'),*root.joinpath('pages').glob('*.py')]):
  try: py_compile.compile(str(path),doraise=True)
  except Exception as exc: compile_fail.append({'path':str(path.relative_to(root)),'error':str(exc)})
 matrix=priority_matrix(root)
 payload={'schema':'biointel.step165.validation.v1','status':'passed' if not failures and not compile_fail else 'failed','priority_modules':3,'software_10of10':int((matrix.software_score==10).sum()),'module_runs':runs,'python_files_compiled':len(list(root.joinpath('src').rglob('*.py')))+len(list(root.joinpath('pages').glob('*.py'))),'module_failures':failures,'compile_failures':compile_fail,'external_evidence_not_inferred':True}
 reports=root/'reports';reports.mkdir(exist_ok=True);(reports/'step165_validation.json').write_text(json.dumps(payload,indent=2)+'\n')
 print(json.dumps(payload,indent=2));return 0 if payload['status']=='passed' else 1
if __name__=='__main__':raise SystemExit(main())
