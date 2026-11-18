from __future__ import annotations
import argparse,json,py_compile
from pathlib import Path
from biointel.target_modules_v179 import TARGET_MODULES,TARGET_PROFILES,qualification_matrix

def main(root:Path)->int:
    frame=qualification_matrix(root);reports=root/'reports';reports.mkdir(exist_ok=True);frame.to_csv(reports/'step179_18_platform_core_qualification.csv',index=False);(reports/'step179_18_platform_core_qualification.json').write_text(json.dumps(frame.to_dict('records'),indent=2,default=str),encoding='utf-8')
    compile_errors=[]
    paths=[root/'src/biointel/target_modules_v179/catalog.py',root/'src/biointel/target_modules_v179/runtime.py',root/'src/biointel/target_modules_v179/checks.py',root/'src/biointel/target_modules_v179/qualification.py',root/'src/biointel/target_modules_v179/ui.py',root/'pages/249_Step179_18_Platform_Core_Assurance_Center.py']+[root/TARGET_PROFILES[k].page for k in TARGET_MODULES]
    for path in paths:
        try:py_compile.compile(str(path),doraise=True)
        except Exception as exc:compile_errors.append(f'{path}:{exc}')
    required=['workflow_contract_complete','reliability_contract_complete','security_contract_complete','acceptance_contract_complete','output_contract_complete','risk_contract_complete','monitoring_contract_complete','ui_hook_present','component_plan_complete','reference_plan_complete','fixture_plan_complete','governance_plan_complete','deterministic_smoke_passed']
    ok=len(frame)==18 and frame.internal_after_rating.eq(10).all() and all(frame[c].all() for c in required) and not compile_errors
    print(frame[['module_key','baseline_rating','internal_after_rating','rating_improvement','decision']].to_string(index=False));print(f'INTERNAL_10OF10={ok}; CONTROLLED_RELEASE={int(frame.controlled_release_eligible.sum())}/18; COMPILE_ERRORS={len(compile_errors)}')
    if compile_errors:print('\n'.join(compile_errors))
    return 0 if ok else 1
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);a=parser.parse_args();raise SystemExit(main(a.root.resolve()))
