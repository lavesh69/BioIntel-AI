# DTI Feature Builder — Local Data Starter Kit

    This kit is bundled inside BioIntel AI and works offline.

    ## Recommended workflow

    1. Download the blank template or the complete starter-kit ZIP.
    2. Keep required column names unchanged.
    3. Replace demo rows with your own data.
    4. Save in one of the accepted formats: **CSV**.
    5. Upload the completed file in the current module.
    6. Review the module's validation messages before running analysis.

    ## Required structure

    - ``canonical_smiles``
- ``protein_sequence``
- `For classification: `label`; for regression: `p_activity``

    ## Notes

    - Use `label` values 0/1 for classification.
- Use numeric `p_activity` for regression.
- Protein sequences must contain standard amino-acid symbols.

    > DEMO / SYNTHETIC DATA — NOT FOR CLINICAL OR SCIENTIFIC VALIDATION.
