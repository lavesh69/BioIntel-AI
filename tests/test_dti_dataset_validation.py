import pandas as pd

from biointel.dti.dataset_validation import validate_dti_dataset


def test_dataset_validator_isolates_invalid_rows():
    dataframe = pd.DataFrame(
        [
            {
                "canonical_smiles": "CCO",
                "protein_sequence": "MKWVTFISLLFLFSSAYSRG",
                "label": 1,
            },
            {
                "canonical_smiles": "broken(",
                "protein_sequence": "MKWVTFISLLFLFSSAYSRG",
                "label": 0,
            },
        ]
    )
    report = validate_dti_dataset(dataframe, "classification")
    assert report.total_rows == 2
    assert report.valid_rows == 1
    assert report.invalid_rows == 1
