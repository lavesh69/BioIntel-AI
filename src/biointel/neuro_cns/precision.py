from __future__ import annotations

from contextlib import nullcontext
import math
from typing import Any

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.impute import SimpleImputer
from scipy.stats import chi2_contingency
from sklearn.metrics import adjusted_rand_score, calinski_harabasz_score, davies_bouldin_score, silhouette_score
from sklearn.preprocessing import StandardScaler

try:
    from threadpoolctl import threadpool_limits
except Exception:  # pragma: no cover - sklearn normally provides threadpoolctl
    threadpool_limits = None

from biointel.neuro_cns.schemas import table_quality_report


def _prepare_matrix(frame: pd.DataFrame, identifier_column: str | None, maximum_missing_fraction: float, excluded_columns: tuple[str, ...] = ()) -> tuple[pd.Series, pd.DataFrame, np.ndarray, SimpleImputer, StandardScaler]:
    identifiers = (
        frame[identifier_column].astype(str).reset_index(drop=True)
        if identifier_column and identifier_column in frame.columns
        else pd.Series([f"sample_{index + 1}" for index in range(len(frame))], name="sample_id")
    )
    drop_columns = [column for column in (identifier_column, *excluded_columns) if column]
    working = frame.drop(columns=drop_columns, errors="ignore")
    numeric = working.select_dtypes(include=[np.number]).copy()
    if numeric.empty:
        numeric = working.apply(pd.to_numeric, errors="coerce").dropna(axis=1, how="all")
    numeric = numeric.loc[:, numeric.isna().mean() <= maximum_missing_fraction]
    numeric = numeric.loc[:, numeric.nunique(dropna=True) > 1]
    if numeric.shape[1] < 2:
        raise ValueError("At least two non-constant numeric research features passing the missingness threshold are required.")
    if len(numeric) < 6:
        raise ValueError("At least six samples are required for exploratory stratification and stability checks.")
    imputer = SimpleImputer(strategy="median")
    scaler = StandardScaler()
    matrix = scaler.fit_transform(imputer.fit_transform(numeric))
    return identifiers, numeric, matrix, imputer, scaler


def _thread_context():
    return threadpool_limits(limits=1) if threadpool_limits is not None else nullcontext()


def recommend_cluster_count(matrix: np.ndarray, *, max_clusters: int = 8, random_state: int = 42) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    maximum = min(max_clusters, len(matrix) - 1)
    for clusters in range(2, maximum + 1):
        model = KMeans(n_clusters=clusters, random_state=random_state, n_init=12, algorithm="lloyd")
        with _thread_context():
            labels = model.fit_predict(matrix)
        rows.append({
            "clusters": clusters,
            "silhouette_score": float(silhouette_score(matrix, labels)),
            "calinski_harabasz": float(calinski_harabasz_score(matrix, labels)),
            "davies_bouldin": float(davies_bouldin_score(matrix, labels)),
            "inertia": float(model.inertia_),
        })
    frame = pd.DataFrame(rows)
    if not frame.empty:
        frame["recommendation_score"] = (
            frame["silhouette_score"].rank(pct=True)
            + frame["calinski_harabasz"].rank(pct=True)
            + (1.0 - frame["davies_bouldin"].rank(pct=True))
        ) / 3.0
    return frame


def _bootstrap_stability(matrix: np.ndarray, base_labels: np.ndarray, clusters: int, random_state: int, iterations: int) -> float:
    rng = np.random.default_rng(random_state)
    scores: list[float] = []
    for iteration in range(max(5, iterations)):
        indices = rng.choice(len(matrix), size=len(matrix), replace=True)
        sample = matrix[indices]
        if len(np.unique(indices)) < clusters:
            continue
        model = KMeans(n_clusters=clusters, random_state=random_state + iteration + 1, n_init=8, algorithm="lloyd")
        with _thread_context():
            model.fit(sample)
            predicted = model.predict(matrix)
        scores.append(float(adjusted_rand_score(base_labels, predicted)))
    return float(np.mean(scores)) if scores else float("nan")


def stratify_research_cohort(
    frame: pd.DataFrame,
    *,
    identifier_column: str | None = None,
    cluster_count: int | None = 3,
    random_state: int = 42,
    maximum_missing_fraction: float = 0.40,
    bootstrap_iterations: int = 20,
    subgroup_column: str | None = None,
    outcome_column: str | None = None,
    exclude_columns: tuple[str, ...] = (),
) -> dict[str, Any]:
    if frame.empty:
        raise ValueError("Cohort table is empty.")
    quality = table_quality_report(frame, identifier_column)
    identifiers, numeric, matrix, imputer, scaler = _prepare_matrix(frame, identifier_column, maximum_missing_fraction, exclude_columns)
    candidate_metrics = recommend_cluster_count(matrix, max_clusters=min(8, len(matrix) - 1), random_state=random_state)
    if cluster_count is None:
        if candidate_metrics.empty:
            cluster_count = 2
        else:
            cluster_count = int(candidate_metrics.sort_values("recommendation_score", ascending=False).iloc[0]["clusters"])
    cluster_count = int(max(2, min(int(cluster_count), len(numeric) - 1, 10)))
    model = KMeans(n_clusters=cluster_count, random_state=random_state, n_init=16, algorithm="lloyd")
    pca = PCA(n_components=min(3, numeric.shape[1], len(numeric) - 1), random_state=random_state)
    with _thread_context():
        labels = model.fit_predict(matrix)
        coords = pca.fit_transform(matrix)
    assignments = pd.DataFrame({"sample_id": identifiers, "cluster": labels.astype(int) + 1})
    for index in range(coords.shape[1]):
        assignments[f"PC{index + 1}"] = coords[:, index]
    silhouette = float(silhouette_score(matrix, labels)) if len(set(labels)) > 1 and len(numeric) > cluster_count else float("nan")
    stability = _bootstrap_stability(matrix, labels, cluster_count, random_state, bootstrap_iterations)
    loadings = pd.DataFrame(pca.components_.T, index=numeric.columns, columns=[f"PC{index + 1}" for index in range(pca.n_components_)]).reset_index().rename(columns={"index": "feature"})
    centers_scaled = model.cluster_centers_
    centers_original = scaler.inverse_transform(centers_scaled)
    centers = pd.DataFrame(centers_original, columns=numeric.columns)
    centers.insert(0, "cluster", np.arange(1, cluster_count + 1))
    cluster_sizes = assignments["cluster"].value_counts().sort_index().rename_axis("cluster").reset_index(name="sample_count")

    subgroup_balance = pd.DataFrame()
    if subgroup_column and subgroup_column in frame.columns:
        subgroup_balance = pd.crosstab(assignments["cluster"], frame[subgroup_column].astype(str), normalize="index").reset_index()
    outcome_summary = pd.DataFrame()
    if outcome_column and outcome_column in frame.columns:
        outcome = pd.to_numeric(frame[outcome_column], errors="coerce")
        outcome_summary = pd.DataFrame({"cluster": assignments["cluster"], "outcome": outcome}).groupby("cluster", as_index=False)["outcome"].agg(["count", "mean", "median", "std"]).reset_index()

    missingness = frame[numeric.columns].isna().mean().rename("missing_fraction").reset_index().rename(columns={"index": "feature"})
    quality_band = "higher" if silhouette >= 0.50 and stability >= 0.75 else "moderate" if silhouette >= 0.25 and stability >= 0.55 else "low"
    warnings: list[str] = []
    if silhouette < 0.25:
        warnings.append("low silhouette separation")
    if np.isfinite(stability) and stability < 0.60:
        warnings.append("low bootstrap cluster stability")
    if cluster_sizes["sample_count"].min() < 3:
        warnings.append("at least one cluster has fewer than three samples")
    if numeric.shape[1] >= len(numeric):
        warnings.append("feature count is high relative to sample count")
    return {
        "assignments": assignments,
        "cluster_centers": centers,
        "cluster_sizes": cluster_sizes,
        "pca_loadings": loadings,
        "candidate_cluster_metrics": candidate_metrics,
        "feature_missingness": missingness,
        "subgroup_balance": subgroup_balance,
        "outcome_summary": outcome_summary,
        "explained_variance_ratio": [round(float(value), 6) for value in pca.explained_variance_ratio_],
        "quality_metrics": {
            "samples": len(numeric),
            "features": numeric.shape[1],
            "clusters": cluster_count,
            "silhouette_score": round(silhouette, 6) if np.isfinite(silhouette) else None,
            "bootstrap_stability": round(stability, 6) if np.isfinite(stability) else None,
            "calinski_harabasz": round(float(calinski_harabasz_score(matrix, labels)), 6),
            "davies_bouldin": round(float(davies_bouldin_score(matrix, labels)), 6),
            "inertia": round(float(model.inertia_), 6),
            "quality_band": quality_band,
            "input_fingerprint_sha256": quality.fingerprint_sha256,
        },
        "quality_warnings": warnings,
        "model_parameters": {"algorithm": "KMeans", "n_init": 16, "random_state": random_state, "maximum_missing_fraction": maximum_missing_fraction, "bootstrap_iterations": max(5, int(bootstrap_iterations)), "exclude_columns": list(exclude_columns)},
        "scientific_boundary": "Exploratory de-identified clustering with internal stability checks; not a treatment recommendation or clinical risk model.",
    }


def precision_neurology_workflow(
    frame: pd.DataFrame,
    *,
    identifier_column: str | None = None,
    cluster_count: int | None = None,
    subgroup_column: str | None = None,
    outcome_column: str | None = None,
    subject_column: str | None = None,
    time_column: str | None = None,
    confound_columns: tuple[str, ...] = (),
    maximum_missing_fraction: float = 0.40,
    bootstrap_iterations: int = 20,
    consensus_iterations: int = 20,
    random_state: int = 42,
) -> dict[str, Any]:
    """Run exploratory stratification with consensus, confound and trajectory review."""
    reserved = tuple(dict.fromkeys(
        column for column in (subgroup_column, outcome_column, subject_column, time_column, *confound_columns)
        if column and column != identifier_column and column in frame.columns
    ))
    base = stratify_research_cohort(
        frame,
        identifier_column=identifier_column,
        cluster_count=cluster_count,
        random_state=random_state,
        maximum_missing_fraction=maximum_missing_fraction,
        bootstrap_iterations=bootstrap_iterations,
        subgroup_column=subgroup_column,
        outcome_column=outcome_column,
        exclude_columns=reserved,
    )
    assignments = base["assignments"].copy()
    selected_clusters = int(base["quality_metrics"]["clusters"])
    _, numeric, matrix, _, _ = _prepare_matrix(frame, identifier_column, maximum_missing_fraction, reserved)
    base_labels = assignments["cluster"].to_numpy(int) - 1

    rng = np.random.default_rng(random_state)
    coassignment = np.zeros((len(matrix), len(matrix)), dtype=float)
    seed_scores: list[dict[str, Any]] = []
    iterations = max(5, int(consensus_iterations))
    for iteration in range(iterations):
        seed = int(rng.integers(1, 2_000_000_000))
        model = KMeans(n_clusters=selected_clusters, random_state=seed, n_init=10, algorithm="lloyd")
        with _thread_context():
            labels = model.fit_predict(matrix)
        coassignment += (labels[:, None] == labels[None, :]).astype(float)
        seed_scores.append({
            "iteration": iteration + 1,
            "random_state": seed,
            "adjusted_rand_vs_primary": round(float(adjusted_rand_score(base_labels, labels)), 6),
        })
    coassignment /= iterations
    consensus_rows: list[dict[str, Any]] = []
    for index, cluster in enumerate(base_labels):
        peers = np.flatnonzero(base_labels == cluster)
        others = np.flatnonzero(base_labels != cluster)
        within = float(coassignment[index, peers].mean()) if len(peers) else 0.0
        outside = float(coassignment[index, others].mean()) if len(others) else 0.0
        consensus_rows.append({
            "sample_id": str(assignments.iloc[index]["sample_id"]),
            "cluster": int(cluster + 1),
            "within_cluster_consensus": round(within, 6),
            "outside_cluster_consensus": round(outside, 6),
            "consensus_margin": round(within - outside, 6),
            "unstable_assignment": bool(within - outside < 0.25),
        })
    consensus = pd.DataFrame(consensus_rows)
    seed_stability = pd.DataFrame(seed_scores)

    confound_rows: list[dict[str, Any]] = []
    for column in confound_columns:
        if column not in frame.columns:
            continue
        series = frame[column]
        numeric_confound = pd.to_numeric(series, errors="coerce")
        if numeric_confound.notna().mean() >= 0.80:
            for component in [name for name in assignments.columns if name.startswith("PC")]:
                pair = pd.DataFrame({"x": numeric_confound, "y": assignments[component]}).dropna()
                correlation = float(pair.corr().iloc[0, 1]) if len(pair) >= 3 else np.nan
                confound_rows.append({
                    "confound": column,
                    "type": "numeric",
                    "comparison": component,
                    "association": round(correlation, 6) if np.isfinite(correlation) else None,
                    "warning": bool(np.isfinite(correlation) and abs(correlation) >= 0.35),
                })
        else:
            contingency = pd.crosstab(assignments["cluster"], series.fillna("Missing").astype(str))
            if contingency.shape[0] >= 2 and contingency.shape[1] >= 2:
                chi2, p_value, dof, _ = chi2_contingency(contingency)
                n = float(contingency.to_numpy().sum())
                denom = max(1.0, min(contingency.shape) - 1.0)
                cramers_v = math.sqrt(max(0.0, chi2 / max(n * denom, 1e-12)))
                confound_rows.append({
                    "confound": column,
                    "type": "categorical",
                    "comparison": "cluster",
                    "association": round(float(cramers_v), 6),
                    "p_value": float(p_value),
                    "degrees_of_freedom": int(dof),
                    "warning": bool(p_value < 0.05 and cramers_v >= 0.20),
                })
    confound_review = pd.DataFrame(confound_rows)

    subgroup_review = pd.DataFrame()
    if subgroup_column and subgroup_column in frame.columns:
        cross = pd.crosstab(assignments["cluster"], frame[subgroup_column].fillna("Missing").astype(str), normalize="index")
        rows = []
        for subgroup in cross.columns:
            values = cross[subgroup]
            rows.append({
                "subgroup": str(subgroup),
                "minimum_cluster_fraction": round(float(values.min()), 6),
                "maximum_cluster_fraction": round(float(values.max()), 6),
                "cluster_fraction_range": round(float(values.max() - values.min()), 6),
                "imbalance_warning": bool(values.max() - values.min() >= 0.35),
            })
        subgroup_review = pd.DataFrame(rows)

    trajectories = pd.DataFrame()
    transitions = pd.DataFrame()
    if subject_column and time_column and subject_column in frame.columns and time_column in frame.columns:
        trajectory = assignments.copy()
        trajectory["subject"] = frame[subject_column].astype(str).to_numpy()
        trajectory["time"] = pd.to_numeric(frame[time_column], errors="coerce").to_numpy()
        trajectory = trajectory.dropna(subset=["time"]).sort_values(["subject", "time"]).reset_index(drop=True)
        transition_rows: list[dict[str, Any]] = []
        for subject, group in trajectory.groupby("subject"):
            ordered = group.sort_values("time")
            clusters = ordered["cluster"].astype(int).tolist()
            for left, right in zip(clusters, clusters[1:]):
                transition_rows.append({"subject": subject, "from_cluster": left, "to_cluster": right, "changed_cluster": left != right})
        trajectories = trajectory
        transitions = pd.DataFrame(transition_rows)

    warnings = list(base.get("quality_warnings", []))
    if not consensus.empty and float(consensus["unstable_assignment"].mean()) > 0.20:
        warnings.append("More than 20% of samples have unstable consensus assignments.")
    if not confound_review.empty and bool(confound_review["warning"].fillna(False).any()):
        warnings.append("One or more supplied confounds are associated with clusters/components.")
    if not subgroup_review.empty and bool(subgroup_review["imbalance_warning"].fillna(False).any()):
        warnings.append("Subgroup representation differs substantially across clusters.")
    base.update({
        "consensus_assignments": consensus,
        "seed_stability": seed_stability,
        "consensus_matrix": pd.DataFrame(coassignment, index=assignments["sample_id"], columns=assignments["sample_id"]),
        "confound_review": confound_review,
        "subgroup_imbalance_review": subgroup_review,
        "longitudinal_trajectories": trajectories,
        "cluster_transitions": transitions,
        "feature_columns_used": list(numeric.columns),
        "reserved_columns_not_used_as_features": list(reserved),
        "quality_warnings": list(dict.fromkeys(warnings)),
        "scientific_boundary": "Exploratory consensus stratification with internal stability, confound, subgroup and longitudinal review; not a treatment recommendation or clinical risk model.",
    })
    return base
