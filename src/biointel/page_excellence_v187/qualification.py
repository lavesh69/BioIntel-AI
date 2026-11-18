from __future__ import annotations
from dataclasses import asdict
from pathlib import Path
import pandas as pd
from .catalog import TARGET_PAGES,TARGET_PROFILES
from .validators import validate_step187_page

def step187_rating_matrix(root:str|Path)->pd.DataFrame:
    rows=[]
    for file_name in TARGET_PAGES:
        p=TARGET_PROFILES[file_name];r=validate_step187_page(root,file_name)
        rows.append({"page_number":p.page_number,"page_title":p.page_title,"file_name":file_name,"category":p.category,"before_rating":p.before_rating,"after_step187_rating":r.rating if r.qualified_10_of_10 else p.before_rating,"improvement_points":round((r.rating if r.qualified_10_of_10 else p.before_rating)-p.before_rating,2),"qualified_10_of_10":r.qualified_10_of_10,"dimensions_passed":r.dimensions_passed,"dimensions_total":r.dimensions_total,"real_external_evidence_changed":False,"controlled_release_eligible":False,"blockers":list(r.blockers)})
    return pd.DataFrame(rows)

def step187_validation_matrix(root:str|Path)->pd.DataFrame:return pd.DataFrame([asdict(validate_step187_page(root,f)) for f in TARGET_PAGES])
__all__=["step187_rating_matrix","step187_validation_matrix"]
