from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class OmicsIntegrationResult:
    integrated: pd.DataFrame
    sample_audit: pd.DataFrame
    layer_summary: pd.DataFrame
    matched_samples: list[str]
    unmatched_samples: dict[str, list[str]]


def _validate_layer(name: str, frame: pd.DataFrame, sample_column: str) -> pd.DataFrame:
    if sample_column not in frame.columns:
        raise ValueError(f"{name} matrix lacks sample column '{sample_column}'.")
    sample_ids = frame[sample_column].astype(str).str.strip()
    if sample_ids.eq("").any():
        raise ValueError(f"{name} matrix contains empty sample identifiers.")
    duplicates = sorted(sample_ids[sample_ids.duplicated(keep=False)].unique())
    if duplicates:
        preview = ", ".join(duplicates[:8])
        raise ValueError(f"{name} matrix contains duplicate sample identifiers: {preview}")
    feature_columns = [str(column).strip() for column in frame.columns if column != sample_column]
    if not feature_columns or any(not column for column in feature_columns):
        raise ValueError(f"{name} matrix has missing feature names.")
    if len(set(feature_columns)) != len(feature_columns):
        raise ValueError(f"{name} matrix contains duplicate feature names.")
    numeric = frame.drop(columns=[sample_column]).copy()
    numeric.columns = feature_columns
    numeric = numeric.apply(pd.to_numeric, errors="coerce")
    if numeric.shape[1] == 0 or numeric.notna().sum().sum() == 0:
        raise ValueError(f"{name} matrix has no numeric measurements.")
    raw = numeric.to_numpy(dtype=float, na_value=np.nan)
    if np.isinf(raw).any():
        raise ValueError(f"{name} matrix contains infinite measurements.")
    all_missing = numeric.columns[numeric.isna().all(axis=0)].tolist()
    if all_missing:
        raise ValueError(f"{name} matrix contains all-missing features: " + ", ".join(all_missing[:8]))
    numeric.index = sample_ids
    numeric.index.name = sample_column
    return numeric


def audit_samples(
    matrices: Mapping[str, pd.DataFrame], *, sample_columns: Mapping[str, str] | None = None
) -> pd.DataFrame:
    if len(matrices) < 2:
        raise ValueError("At least two omics matrices are required.")
    sample_columns = sample_columns or {name: "sample" for name in matrices}
    sets: dict[str, set[str]] = {}
    for name, frame in matrices.items():
        column = sample_columns.get(name, "sample")
        validated = _validate_layer(name, frame, column)
        sets[name] = set(validated.index.astype(str))
    union = set().union(*sets.values())
    rows = []
    for sample in sorted(union):
        present = [name for name, values in sets.items() if sample in values]
        rows.append(
            {
                "sample": sample,
                "present_layers": ", ".join(present),
                "layer_count": len(present),
                "matched_all_layers": len(present) == len(sets),
                **{f"present_{name}": sample in sets[name] for name in sets},
            }
        )
    return pd.DataFrame(rows)


def _transform_layer(
    frame: pd.DataFrame,
    *,
    missing_policy: str,
    transform: str,
    feature_limit: int | None,
) -> pd.DataFrame:
    numeric = frame.copy()
    if missing_policy == "drop_features":
        numeric = numeric.dropna(axis=1)
    elif missing_policy == "median":
        numeric = numeric.fillna(numeric.median(numeric_only=True))
    elif missing_policy == "zero":
        numeric = numeric.fillna(0.0)
    elif missing_policy == "drop_samples":
        numeric = numeric.dropna(axis=0)
    else:
        raise ValueError(f"Unsupported missing-value policy: {missing_policy}")
    if numeric.empty:
        raise ValueError("Missing-value handling removed all data.")
    if numeric.isna().any().any():
        raise ValueError("Missing-value handling left unresolved values.")
    if not np.all(np.isfinite(numeric.to_numpy(dtype=float))):
        raise ValueError("Transformed omics matrix contains non-finite values.")
    if feature_limit and numeric.shape[1] > feature_limit:
        variances = numeric.var(axis=0).sort_values(ascending=False)
        numeric = numeric[variances.head(int(feature_limit)).index]
    if transform == "log1p_zscore":
        if (numeric < 0).any().any():
            raise ValueError("Log transformation requires non-negative values.")
        numeric = np.log2(numeric + 1.0)
    elif transform not in {"zscore", "none"}:
        raise ValueError(f"Unsupported transformation: {transform}")
    if transform in {"zscore", "log1p_zscore"}:
        numeric = (numeric - numeric.mean()) / numeric.std(ddof=0).replace(0, 1)
    return numeric


def integrate_omics_advanced(
    matrices: Mapping[str, pd.DataFrame],
    *,
    sample_columns: Mapping[str, str] | None = None,
    join: str = "inner",
    missing_policy: str = "median",
    transform: str = "zscore",
    feature_limit: int | None = 1000,
    layer_weights: Mapping[str, float] | None = None,
) -> OmicsIntegrationResult:
    if len(matrices) < 2:
        raise ValueError("At least two omics matrices are required.")
    if join not in {"inner", "outer"}:
        raise ValueError("Join must be 'inner' or 'outer'.")
    sample_columns = sample_columns or {name: "sample" for name in matrices}
    layer_weights = layer_weights or {}
    validated: dict[str, pd.DataFrame] = {}
    sample_sets: dict[str, set[str]] = {}
    summaries: list[dict[str, object]] = []
    for name, frame in matrices.items():
        sample_column = sample_columns.get(name, "sample")
        numeric = _validate_layer(name, frame, sample_column)
        sample_sets[name] = set(numeric.index.astype(str))
        transformed = _transform_layer(
            numeric,
            missing_policy=missing_policy if missing_policy != "drop_samples" else "median",
            transform=transform,
            feature_limit=feature_limit,
        )
        weight = float(layer_weights.get(name, 1.0))
        if weight <= 0:
            raise ValueError(f"Layer weight for {name} must be positive.")
        transformed *= np.sqrt(weight)
        transformed.columns = [f"{name}__{column}" for column in transformed.columns]
        validated[name] = transformed
        summaries.append(
            {
                "layer": name,
                "samples": len(transformed),
                "features": transformed.shape[1],
                "missing_before": int(numeric.isna().sum().sum()),
                "weight": weight,
                "sample_column": sample_column,
            }
        )

    integrated: pd.DataFrame | None = None
    for frame in validated.values():
        integrated = frame if integrated is None else integrated.join(frame, how=join)
    assert integrated is not None
    if missing_policy == "drop_samples":
        integrated = integrated.dropna(axis=0)
    elif missing_policy == "median":
        integrated = integrated.fillna(integrated.median(numeric_only=True))
    elif missing_policy == "zero":
        integrated = integrated.fillna(0.0)
    elif missing_policy == "drop_features":
        integrated = integrated.dropna(axis=1)
    if integrated.empty:
        raise ValueError("No usable samples or features remain after integration.")

    audit = audit_samples(matrices, sample_columns=sample_columns)
    matched = sorted(set.intersection(*sample_sets.values()))
    union = set.union(*sample_sets.values())
    unmatched = {name: sorted(union - values) for name, values in sample_sets.items()}
    sample_name = "sample"
    output = integrated.copy()
    output.insert(0, sample_name, output.index.astype(str))
    return OmicsIntegrationResult(
        integrated=output.reset_index(drop=True),
        sample_audit=audit,
        layer_summary=pd.DataFrame(summaries),
        matched_samples=matched,
        unmatched_samples=unmatched,
    )


def integrate_omics(
    matrices: dict[str, pd.DataFrame], *, sample_column: str = "sample"
) -> pd.DataFrame:
    result = integrate_omics_advanced(
        matrices,
        sample_columns={name: sample_column for name in matrices},
        join="inner",
        missing_policy="median",
        transform="zscore",
    )
    return result.integrated


def integrated_pca(
    frame: pd.DataFrame, sample_column: str = "sample", components: int = 2
) -> pd.DataFrame:
    from sklearn.decomposition import PCA
    from sklearn.preprocessing import StandardScaler

    data = frame.set_index(sample_column).apply(pd.to_numeric, errors="raise")
    if len(data) < 2 or data.shape[1] < 1:
        raise ValueError("Integrated PCA requires at least two samples and one feature.")
    n = max(1, min(int(components), len(data) - 1, data.shape[1]))
    model = PCA(n_components=n, random_state=42)
    values = model.fit_transform(StandardScaler().fit_transform(data))
    out = pd.DataFrame(values, index=data.index, columns=[f"PC{i + 1}" for i in range(n)])
    out.insert(0, "sample", out.index)
    out["variance_explained_total"] = float(model.explained_variance_ratio_.sum())
    return out.reset_index(drop=True)


def integrated_nmf(
    frame: pd.DataFrame,
    *,
    sample_column: str = "sample",
    components: int = 3,
    random_state: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    from sklearn.decomposition import NMF

    data = frame.set_index(sample_column).apply(pd.to_numeric, errors="raise")
    if len(data) < 2 or data.shape[1] < 2:
        raise ValueError("Integrated NMF requires at least two samples and two features.")
    shifted = data - data.min(axis=0)
    n = max(2, min(int(components), len(shifted), shifted.shape[1]))
    model = NMF(n_components=n, init="nndsvda", random_state=random_state, max_iter=1000)
    scores = model.fit_transform(shifted.to_numpy(float))
    sample_scores = pd.DataFrame(
        scores, index=data.index, columns=[f"Factor{i + 1}" for i in range(n)]
    )
    sample_scores.insert(0, "sample", sample_scores.index.astype(str))
    loadings = pd.DataFrame(
        model.components_.T, index=data.columns, columns=[f"Factor{i + 1}" for i in range(n)]
    )
    loadings.insert(0, "feature", loadings.index.astype(str))
    return sample_scores.reset_index(drop=True), loadings.reset_index(drop=True)


def canonical_correlation(
    left: pd.DataFrame,
    right: pd.DataFrame,
    *,
    left_sample_column: str = "sample",
    right_sample_column: str = "sample",
    components: int = 2,
    ridge: float = 1e-6,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    from sklearn.preprocessing import StandardScaler

    """Regularized CCA robust to collinearity and constant features."""
    left_numeric = _validate_layer("left", left, left_sample_column)
    right_numeric = _validate_layer("right", right, right_sample_column)
    shared = sorted(set(left_numeric.index) & set(right_numeric.index))
    if len(shared) < 3:
        raise ValueError("CCA requires at least three shared samples.")
    left_values = left_numeric.loc[shared].fillna(left_numeric.median(numeric_only=True))
    right_values = right_numeric.loc[shared].fillna(right_numeric.median(numeric_only=True))
    left_values = left_values.loc[:, left_values.std(ddof=0) > 1e-12]
    right_values = right_values.loc[:, right_values.std(ddof=0) > 1e-12]
    if left_values.empty or right_values.empty:
        raise ValueError("CCA requires at least one non-constant feature in each layer.")
    x = StandardScaler().fit_transform(left_values)
    y = StandardScaler().fit_transform(right_values)
    n_obs = len(shared)
    cxx = (x.T @ x) / max(n_obs - 1, 1) + float(ridge) * np.eye(x.shape[1])
    cyy = (y.T @ y) / max(n_obs - 1, 1) + float(ridge) * np.eye(y.shape[1])
    cxy = (x.T @ y) / max(n_obs - 1, 1)

    def inverse_sqrt(matrix: np.ndarray) -> np.ndarray:
        values, vectors = np.linalg.eigh(matrix)
        values = np.clip(values, float(ridge), None)
        return vectors @ np.diag(1.0 / np.sqrt(values)) @ vectors.T

    whitened = inverse_sqrt(cxx) @ cxy @ inverse_sqrt(cyy)
    u, singular, vt = np.linalg.svd(whitened, full_matrices=False)
    n = max(1, min(int(components), len(singular), n_obs - 1))
    wx = inverse_sqrt(cxx) @ u[:, :n]
    wy = inverse_sqrt(cyy) @ vt.T[:, :n]
    x_scores = x @ wx
    y_scores = y @ wy
    scores = pd.DataFrame({"sample": shared})
    correlations = []
    for index in range(n):
        scores[f"X_CC{index + 1}"] = x_scores[:, index]
        scores[f"Y_CC{index + 1}"] = y_scores[:, index]
        correlation = float(np.corrcoef(x_scores[:, index], y_scores[:, index])[0, 1])
        correlations.append(
            {
                "component": index + 1,
                "canonical_correlation": float(np.clip(correlation, -1.0, 1.0)),
                "regularization": float(ridge),
                "singular_value": float(singular[index]),
            }
        )
    return scores, pd.DataFrame(correlations)
