from __future__ import annotations
import argparse,json
from pathlib import Path
from biointel.target_modules_v179 import TARGET_MODULES,TARGET_PROFILES,required_components,required_references
from biointel.target_modules_v179.runtime import REFERENCE_FLAGS,FIXTURE_FLAGS,GOVERNANCE_FLAGS,EXTERNAL_FLAGS
from biointel.target_modules_v179.checks import run_contract_smoke

def manifest(asset_id:str,kind:str,flags:tuple[str,...])->dict:
    payload={'schema':f'biointel.step179.{kind}-qualification.v1','asset_id':asset_id};payload.update({f:False for f in flags});return payload

def main(root:Path)->None:
    out=root/'data/step179';target=out/'target_modules';target.mkdir(parents=True,exist_ok=True);index=[]
    for key in TARGET_MODULES:
        p=TARGET_PROFILES[key];folder=target/key;folder.mkdir(parents=True,exist_ok=True)
        contract={'schema':'biointel.step179.18-platform-core-assurance.v1','module_key':key,'module_title':p.title,'baseline_rating':p.baseline_rating,'internal_after_rating':10.0,'focus':p.focus,'workflow':list(p.workflow),'reliability_gates':list(p.reliability_gates),'security_gates':list(p.security_gates),'acceptance_criteria':list(p.acceptance_criteria),'required_outputs':list(p.required_outputs),'risk_controls':list(p.risk_controls),'monitoring_metrics':list(p.monitoring_metrics),'boundary':p.boundary,'validation_fixtures':list(p.validation_fixtures),'governance_assets':list(p.governance_assets)}
        (folder/'assurance_contract.json').write_text(json.dumps(contract,indent=2),encoding='utf-8')
        required_components(key).to_csv(folder/'component_plan.csv',index=False);required_references(key).to_csv(folder/'reference_plan.csv',index=False)
        (folder/'built_in_smoke_results.json').write_text(json.dumps({'module_key':key,'checks':run_contract_smoke(key)},indent=2),encoding='utf-8')
        for kind,ids,flags in [('fixture',p.validation_fixtures,FIXTURE_FLAGS),('governance',p.governance_assets,GOVERNANCE_FLAGS)]:
            d=folder/f'{kind}_manifest_templates';d.mkdir(exist_ok=True)
            for asset_id in ids:(d/f'{asset_id}.json').write_text(json.dumps(manifest(asset_id,kind,flags),indent=2),encoding='utf-8')
        refs=folder/'reference_manifest_templates';refs.mkdir(exist_ok=True)
        for asset_id in p.supplemental_references:(refs/f'{asset_id}.json').write_text(json.dumps(manifest(asset_id,'reference',REFERENCE_FLAGS),indent=2),encoding='utf-8')
        evidence={'schema':'biointel.step179.external-evidence.v1','module_key':key};evidence.update({f:False for f in EXTERNAL_FLAGS});(folder/'external_evidence_manifest_template.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
        index.append({'module_key':key,'module_title':p.title,'folder':str(folder.relative_to(root))})
    (out/'asset_index.json').write_text(json.dumps({'schema':'biointel.step179.asset-index.v1','modules':index},indent=2),encoding='utf-8')
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);a=parser.parse_args();main(a.root.resolve())
