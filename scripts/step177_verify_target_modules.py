from __future__ import annotations
import argparse,json
from pathlib import Path
from biointel.target_modules_v177 import qualification_matrix

def main(root:Path)->int:
    frame=qualification_matrix(root);reports=root/'reports';reports.mkdir(exist_ok=True);frame.to_csv(reports/'step177_21_module_qualification.csv',index=False);(reports/'step177_21_module_qualification.json').write_text(json.dumps(frame.to_dict('records'),indent=2,default=str),encoding='utf-8')
    ok=len(frame)==21 and frame.internal_upgrade_rating.eq(10).all() and frame.workflow_contract_complete.all() and frame.quality_gate_contract_complete.all() and frame.output_contract_complete.all() and frame.ui_hook_present.all() and frame.engine_plan_complete.all() and frame.reference_plan_complete.all() and frame.model_plan_complete.all() and frame.cohort_plan_complete.all()
    print(frame[['module_key','internal_upgrade_rating','decision']].to_string(index=False));print(f'INTERNAL_10OF10={ok}; CONTROLLED_RELEASE={int(frame.controlled_release_eligible.sum())}/21')
    return 0 if ok else 1
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);a=ap.parse_args();raise SystemExit(main(a.root.resolve()))
