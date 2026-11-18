from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from biointel.dti.predictor import (
    _validated_interval,
    _validated_probability_output,
    _validated_regression_output,
    _validated_threshold,
)
from biointel.microbiology.metagenomics import (
    approximate_ani,
    beta_diversity,
    validate_abundance_frame,
)
from biointel.omics.integration import integrate_omics_advanced
from biointel.projects.cancer_genomics import validate_variant_table
from biointel.projects.single_cell import validate_count_matrix as validate_single_cell
from biointel.proteomics.advanced import (
    differential_protein_abundance,
    validate_quantitative_proteomics,
)
from biointel.structural.pdb_analysis import parse_structure
from biointel.transcriptomics.advanced import sample_diagnostics
from biointel.transcriptomics.expression import validate_count_matrix


def test_transcriptomics_rejects_zero_library_and_nonfinite():
    with pytest.raises(ValueError, match="positive total expression"):
        validate_count_matrix(pd.DataFrame({"gene":["A","B"],"S1":[0,0],"S2":[1,2]}))
    with pytest.raises(ValueError, match="non-numeric, missing or non-finite"):
        validate_count_matrix(pd.DataFrame({"gene":["A","B"],"S1":[1,np.inf],"S2":[1,2]}))

def test_transcriptomics_distance_is_finite_and_symmetric():
    frame=pd.DataFrame({"gene":["A","B","C"],"S1":[1,2,3],"S2":[2,2,4],"S3":[5,1,2]})
    _,_,distance=sample_diagnostics(frame)
    assert np.allclose(distance,distance.T)
    assert np.allclose(np.diag(distance),0.0)
    assert np.isfinite(distance.to_numpy()).all()

def test_omics_rejects_duplicate_features_and_inf():
    left=pd.DataFrame([["S1",1,2],["S2",2,3]],columns=["sample","x","x"])
    right=pd.DataFrame({"sample":["S1","S2"],"y":[1,2]})
    with pytest.raises(ValueError,match="duplicate feature"):
        integrate_omics_advanced({"left":left,"right":right})
    left=pd.DataFrame({"sample":["S1","S2"],"x":[1,np.inf]})
    with pytest.raises(ValueError,match="infinite"):
        integrate_omics_advanced({"left":left,"right":right})

def test_single_cell_rejects_zero_count_cell():
    frame=pd.DataFrame({"gene":["G1","G2"],**{f"C{i}":[1,1] for i in range(1,6)},"C6":[0,0]})
    with pytest.raises(ValueError,match="zero total counts"):
        validate_single_cell(frame)

def test_cancer_rejects_conflicting_duplicate_and_invalid_allele():
    base={"chromosome":"1","position":100,"ref":"A","alt":"T","gene":"TP53","consequence":"missense","vaf":0.2,"depth":100,"sample":"S1","filter":"PASS"}
    with pytest.raises(ValueError,match="Conflicting duplicate"):
        validate_variant_table(pd.DataFrame([base,{**base,"depth":120}]))
    with pytest.raises(ValueError,match="Alleles"):
        validate_variant_table(pd.DataFrame([{**base,"alt":"?"}]))

def test_microbiology_short_ani_and_nonfinite_abundance():
    with pytest.raises(ValueError,match="at least 15 bases"):
        approximate_ani("ACGT","ACGT")
    with pytest.raises(ValueError,match="finite"):
        validate_abundance_frame(pd.DataFrame({"taxon":["A","B"],"S1":[1,np.inf]}))
    d=beta_diversity(pd.DataFrame({"taxon":["A","B"],"S1":[1,2],"S2":[2,1]}))
    assert np.isfinite(d.to_numpy()).all() and np.allclose(np.diag(d),0.0)

def test_structural_parser_rejects_null_bytes():
    with pytest.raises(ValueError,match="null bytes"):
        parse_structure("ATOM\x00")

def test_proteomics_rejects_inf_and_marks_untestable():
    with pytest.raises(ValueError,match="finite"):
        validate_quantitative_proteomics(pd.DataFrame({"protein":["P1"],"sample":["S1"],"intensity":[np.inf]}))
    data=pd.DataFrame({"protein":["P1","P1","P1","P2","P2","P2","P2"],"sample":["A1","A2","B1","A1","A2","B1","B2"],"intensity":[10,11,12,4,5,8,9]})
    meta=pd.DataFrame({"sample":["A1","A2","B1","B2"],"group":["A","A","B","B"]})
    result=differential_protein_abundance(data,meta,group_a="A",group_b="B")
    p1=result.loc[result["protein"]=="P1"].iloc[0]
    assert not bool(p1["testable"]) and p1["p_value"]==1.0
    assert result["fdr_bh"].between(0,1).all()

def test_version_is_823():
    version = (Path(__file__).resolve().parents[1] / "VERSION").read_text().strip()
    assert tuple(map(int, version.split("."))) >= (8, 2, 6)


def test_dti_prediction_output_guards():
    assert _validated_threshold(None) == 0.5
    assert _validated_probability_output([[0.2, 0.8]]) == pytest.approx(0.8)
    assert _validated_regression_output([7.25]) == pytest.approx(7.25)
    assert _validated_interval(1.0, 2.0) == (1.0, 2.0)
    with pytest.raises(ValueError, match="between 0 and 1"):
        _validated_threshold(1.2)
    with pytest.raises(ValueError, match="invalid positive-class probability"):
        _validated_probability_output([[0.2, np.nan]])
    with pytest.raises(ValueError, match="malformed prediction"):
        _validated_regression_output([1.0, 2.0])
    with pytest.raises(ValueError, match="reversed"):
        _validated_interval(2.0, 1.0)
