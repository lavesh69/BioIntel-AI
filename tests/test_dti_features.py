import numpy as np
import pytest

from biointel.dti.feature_combiner import combine_dti_features
from biointel.dti.protein_features import extract_protein_features
from biointel.utils.exceptions import InvalidSequenceError

PROTEIN = "MKWVTFISLLFLFSSAYSRGVFRRDTHKSEIAHRFKDLGE"


def test_protein_feature_order_and_dimension():
    result = extract_protein_features(PROTEIN)
    assert len(result.values) == 26
    assert len(result.names) == 26
    assert np.isfinite(result.values).all()


def test_dipeptide_features_add_400_columns():
    base = extract_protein_features(PROTEIN, include_dipeptides=False)
    extended = extract_protein_features(PROTEIN, include_dipeptides=True)
    assert len(extended.values) == len(base.values) + 400


def test_ambiguous_protein_is_rejected_for_dti():
    with pytest.raises(InvalidSequenceError):
        extract_protein_features("MKWVTX")


def test_combined_feature_schema_matches_vector():
    result = combine_dti_features("CCO", PROTEIN, n_bits=256)
    assert result.schema.feature_count == len(result.values)
    assert result.schema.feature_count == len(result.names)
    assert result.schema.fingerprint_bits == 256
    assert len(result.schema.feature_hash) == 64
