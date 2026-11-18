from __future__ import annotations
import argparse,json,py_compile
from pathlib import Path
from biointel.target_modules_v178 import TARGET_MODULES,TARGET_PROFILES,qualification_matrix

def main(root:Path)->int:
    frame=qualification_matrix(root);reports=root/'reports';reports.mkdir(exist_ok=True);frame.to_csv(reports/'step178_19_module_qualification.csv',index=False);(reports/'step178_19_module_qualification.json').write_text(json.dumps(frame.to_dict('records'),indent=2,default=str),encoding='utf-8')
    compile_errors=[]
    for path in [root/'src/biointel/target_modules_v178/catalog.py',root/'src/biointel/target_modules_v178/runtime.py',root/'src/biointel/target_modules_v178/qualification.py',root/'src/biointel/target_modules_v178/ui.py',root/'pages/248_Step178_19_Module_Assurance_Center.py']+[root/TARGET_PROFILES[k].page for k in TARGET_MODULES]:
        try:py_compile.compile(str(path),doraise=True)
        except Exception as exc:compile_errors.append(f'{path}:{exc}')
    required=['workflow_contract_complete','quality_gate_contract_complete','acceptance_contract_complete','output_contract_complete','risk_contract_complete','monitoring_contract_complete','ui_hook_present','engine_plan_complete','reference_plan_complete','model_plan_complete','cohort_plan_complete','governance_plan_complete']
    ok=len(frame)==19 and frame.internal_after_rating.eq(10).all() and all(frame[c].all() for c in required) and not compile_errors
    print(frame[['module_key','baseline_rating','internal_after_rating','rating_improvement','decision']].to_string(index=False));print(f'INTERNAL_10OF10={ok}; CONTROLLED_RELEASE={int(frame.controlled_release_eligible.sum())}/19; COMPILE_ERRORS={len(compile_errors)}')
    if compile_errors:print('\n'.join(compile_errors))
    return 0 if ok else 1
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);args=parser.parse_args();raise SystemExit(main(args.root.resolve()))
