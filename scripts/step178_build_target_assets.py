from __future__ import annotations
import argparse,json
from pathlib import Path
from biointel.target_modules_v178 import TARGET_MODULES,TARGET_PROFILES,required_engines,required_references
from biointel.target_modules_v178.runtime import REFERENCE_FLAGS,MODEL_FLAGS,COHORT_FLAGS,GOVERNANCE_FLAGS,EVIDENCE_FLAGS

def manifest(asset_id:str,kind:str,flags:tuple[str,...])->dict:
    payload={'schema':f'biointel.step178.{kind}-qualification.v1','asset_id':asset_id}
    payload.update({flag:False for flag in flags});return payload

def main(root:Path)->None:
    out=root/'data/step178';target=out/'target_modules';target.mkdir(parents=True,exist_ok=True);index=[]
    for key in TARGET_MODULES:
        p=TARGET_PROFILES[key];folder=target/key;folder.mkdir(parents=True,exist_ok=True)
        contract={'schema':'biointel.step178.19-module-assurance-contract.v1','module_key':key,'module_title':p.title,'baseline_rating':p.baseline_rating,'internal_after_rating':10.0,'evidence_class':p.evidence_class,'workflow':list(p.workflow),'quality_gates':list(p.quality_gates),'acceptance_criteria':list(p.acceptance_criteria),'required_outputs':list(p.required_outputs),'risk_controls':list(p.risk_controls),'monitoring_metrics':list(p.monitoring_metrics),'boundary':p.boundary,'model_assets':list(p.model_assets),'cohort_assets':list(p.cohort_assets),'governance_assets':list(p.governance_assets)}
        (folder/'assurance_contract.json').write_text(json.dumps(contract,indent=2),encoding='utf-8')
        required_engines(key).to_csv(folder/'engine_plan.csv',index=False);required_references(key).to_csv(folder/'reference_plan.csv',index=False)
        for kind,ids,flags in [('model',p.model_assets,MODEL_FLAGS),('cohort',p.cohort_assets,COHORT_FLAGS),('governance',p.governance_assets,GOVERNANCE_FLAGS)]:
            target_dir=folder/f'{kind}_manifest_templates';target_dir.mkdir(exist_ok=True)
            for asset_id in ids:(target_dir/f'{asset_id}.json').write_text(json.dumps(manifest(asset_id,kind,flags),indent=2),encoding='utf-8')
        evidence={'schema':'biointel.step178.external-evidence.v1','module_key':key};evidence.update({flag:False for flag in EVIDENCE_FLAGS});(folder/'external_evidence_manifest_template.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
        index.append({'module_key':key,'module_title':p.title,'folder':str(folder.relative_to(root))})
    (out/'asset_index.json').write_text(json.dumps({'schema':'biointel.step178.asset-index.v1','modules':index},indent=2),encoding='utf-8')
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);args=parser.parse_args();main(args.root.resolve())
