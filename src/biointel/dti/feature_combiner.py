from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from biointel.dti.drug_features import DrugFeatureSet, extract_drug_features
from biointel.dti.protein_features import ProteinFeatureSet, extract_protein_features


@dataclass(frozen=True)
class FeatureSchema:
    """Metadata needed to reproduce and validate a combined DTI feature vector."""

    schema_version: str
    feature_count: int
    feature_hash: str
    fingerprint_radius: int
    fingerprint_bits: int
    use_chirality: bool
    include_dipeptides: bool
    drug_feature_count: int
    protein_feature_count: int


@dataclass(frozen=True)
class CombinedFeatureSet:
    """Combined drug and target representation."""

    values: np.ndarray
    names: tuple[str, ...]
    drug: DrugFeatureSet
    protein: ProteinFeatureSet
    schema: FeatureSchema

    def to_dataframe(self) -> pd.DataFrame:
        """Return one row with stable feature column ordering."""

        return pd.DataFrame([self.values], columns=self.names)

    def schema_json(self) -> str:
        """Serialize reproducibility metadata as JSON."""

        return json.dumps(asdict(self.schema), indent=2)


def _feature_hash(names: tuple[str, ...]) -> str:
    joined = "\n".join(names).encode("utf-8")
    return hashlib.sha256(joined).hexdigest()


def combine_dti_features(
    smiles: str,
    protein_sequence: str,
    radius: int = 2,
    n_bits: int = 2048,
    use_chirality: bool = True,
    include_dipeptides: bool = False,
) -> CombinedFeatureSet:
    """Create a reproducible drug–target feature vector without making a prediction."""

    drug = extract_drug_features(smiles, radius, n_bits, use_chirality)
    protein = extract_protein_features(protein_sequence, include_dipeptides)
    names = drug.names + protein.names
    values = np.concatenate([drug.values, protein.values])
    schema = FeatureSchema(
        schema_version="2.0.0",
        feature_count=len(names),
        feature_hash=_feature_hash(names),
        fingerprint_radius=radius,
        fingerprint_bits=n_bits,
        use_chirality=use_chirality,
        include_dipeptides=include_dipeptides,
        drug_feature_count=len(drug.names),
        protein_feature_count=len(protein.names),
    )
    return CombinedFeatureSet(values, names, drug, protein, schema)
