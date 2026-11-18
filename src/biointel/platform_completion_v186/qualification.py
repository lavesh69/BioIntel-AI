from __future__ import annotations
from dataclasses import asdict
from pathlib import Path
import pandas as pd
from .catalog import TARGET_MODULES,TARGET_PROFILES
from .validators import validate_step186_module

def step186_rating_matrix(root:str|Path)->pd.DataFrame:
    rows=[]
    for key in TARGET_MODULES:
        p=TARGET_PROFILES[key];r=validate_step186_module(root,key);after=r.rating if r.qualified_10_of_10 else p.before_demo_rating
        rows.append({'module_key':key,'module_title':p.title,'before_demo_rating':p.before_demo_rating,'after_platform_completion_rating':after,'improvement_points':round(after-p.before_demo_rating,2),'qualified_10_of_10':r.qualified_10_of_10,'dimensions_passed':r.dimensions_passed,'dimensions_total':r.dimensions_total,'real_external_rating':p.baseline_practical_rating,'real_external_rating_changed':False,'controlled_release_eligible':False,'blockers':list(r.blockers)})
    return pd.DataFrame(rows)
def step186_validation_matrix(root:str|Path)->pd.DataFrame:return pd.DataFrame([asdict(validate_step186_module(root,k)) for k in TARGET_MODULES])
__all__=['step186_rating_matrix','step186_validation_matrix']
