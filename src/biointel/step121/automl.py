from __future__ import annotations

import io
import json
from dataclasses import dataclass
from hashlib import sha256
from time import perf_counter
from typing import Any, Literal

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import ExtraTreesClassifier, ExtraTreesRegressor, RandomForestClassifier, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import ElasticNet, LogisticRegression, Ridge
from sklearn.metrics import (
    balanced_accuracy_score,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    r2_score,
    roc_auc_score,
)
from sklearn.model_selection import KFold, StratifiedKFold, cross_validate, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

Task = Literal["classification", "regression"]


@dataclass(frozen=True)
class AutoMLResult:
    task: Task
    leaderboard: pd.DataFrame
    feature_importance: pd.DataFrame
    holdout_predictions: pd.DataFrame
    model_card: dict[str, Any]
    search_manifest: dict[str, Any]
    artifact_bytes: bytes


def infer_task(target: pd.Series) -> Task:
    values = target.dropna()
    if values.empty:
        raise ValueError("Target contains no usable values.")
    if pd.api.types.is_bool_dtype(values) or values.nunique() <= max(12, int(np.sqrt(len(values)))):
        return "classification"
    return "regression"


def _preprocessor(frame: pd.DataFrame, *, dense: bool) -> ColumnTransformer:
    numeric = list(frame.select_dtypes(include=[np.number, "bool"]).columns)
    categorical = [column for column in frame.columns if column not in numeric]
    transformers: list[tuple[str, Any, list[str]]] = []
    if numeric:
        transformers.append(
            (
                "numeric",
                Pipeline([("imputer", SimpleImputer(strategy="median")), ("scale", StandardScaler())]),
                numeric,
            )
        )
    if categorical:
        transformers.append(
            (
                "categorical",
                Pipeline(
                    [
                        ("imputer", SimpleImputer(strategy="most_frequent")),
                        ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=not dense, max_categories=50)),
                    ]
                ),
                categorical,
            )
        )
    if not transformers:
        raise ValueError("No usable predictor columns were found.")
    return ColumnTransformer(transformers, remainder="drop", verbose_feature_names_out=False)


def _candidate_catalog(task: Task, random_state: int) -> list[tuple[str, Pipeline]]:
    if task == "classification":
        return [
            (
                "logistic_l2",
                Pipeline(
                    [
                        ("preprocessor", None),
                        ("model", LogisticRegression(max_iter=2000, class_weight="balanced", C=1.0, random_state=random_state)),
                    ]
                ),
            ),
            (
                "random_forest",
                Pipeline(
                    [
                        ("preprocessor", None),
                        (
                            "model",
                            RandomForestClassifier(
                                n_estimators=160,
                                max_depth=None,
                                min_samples_leaf=2,
                                class_weight="balanced_subsample",
                                n_jobs=1,
                                random_state=random_state,
                            ),
                        ),
                    ]
                ),
            ),
            (
                "extra_trees",
                Pipeline(
                    [
                        ("preprocessor", None),
                        (
                            "model",
                            ExtraTreesClassifier(
                                n_estimators=180,
                                min_samples_leaf=2,
                                class_weight="balanced",
                                n_jobs=1,
                                random_state=random_state,
                            ),
                        ),
                    ]
                ),
            ),
        ]
    return [
        (
            "ridge",
            Pipeline([("preprocessor", None), ("model", Ridge(alpha=1.0))]),
        ),
        (
            "elastic_net",
            Pipeline([("preprocessor", None), ("model", ElasticNet(alpha=0.01, l1_ratio=0.25, max_iter=5000, random_state=random_state))]),
        ),
        (
            "random_forest",
            Pipeline(
                [
                    ("preprocessor", None),
                    (
                        "model",
                        RandomForestRegressor(
                            n_estimators=160,
                            min_samples_leaf=2,
                            n_jobs=1,
                            random_state=random_state,
                        ),
                    ),
                ]
            ),
        ),
        (
            "extra_trees",
            Pipeline(
                [
                    ("preprocessor", None),
                    (
                        "model",
                        ExtraTreesRegressor(
                            n_estimators=180,
                            min_samples_leaf=2,
                            n_jobs=1,
                            random_state=random_state,
                        ),
                    ),
                ]
            ),
        ),
    ]


def _prepare_target(series: pd.Series, task: Task) -> tuple[pd.Series, dict[str, int] | None]:
    if task == "classification":
        labels = sorted(str(value) for value in series.dropna().unique())
        if len(labels) != 2:
            raise ValueError("Resource-bounded AutoML currently supports binary classification only.")
        mapping = {label: index for index, label in enumerate(labels)}
        return series.astype(str).map(mapping), mapping
    numeric = pd.to_numeric(series, errors="coerce")
    return numeric, None


def _scoring(task: Task) -> dict[str, str]:
    if task == "classification":
        return {
            "roc_auc": "roc_auc",
            "balanced_accuracy": "balanced_accuracy",
            "f1": "f1",
        }
    return {
        "rmse": "neg_root_mean_squared_error",
        "mae": "neg_mean_absolute_error",
        "r2": "r2",
    }


def _primary(task: Task) -> tuple[str, bool]:
    return ("mean_test_roc_auc", True) if task == "classification" else ("mean_test_rmse", False)


def _safe_feature_names(pipeline: Pipeline) -> list[str]:
    try:
        return list(pipeline.named_steps["preprocessor"].get_feature_names_out())
    except Exception:
        model = pipeline.named_steps["model"]
        count = len(getattr(model, "feature_importances_", getattr(model, "coef_", [])))
        return [f"feature_{index}" for index in range(count)]


def resource_bounded_automl(
    frame: pd.DataFrame,
    *,
    target_column: str,
    task: Task | None = None,
    max_rows: int = 20_000,
    cv_folds: int = 5,
    holdout_fraction: float = 0.20,
    random_state: int = 42,
    max_candidates: int = 4,
) -> AutoMLResult:
    if target_column not in frame.columns:
        raise ValueError(f"Target column not found: {target_column}")
    working = frame.dropna(subset=[target_column]).copy()
    if len(working) < 30:
        raise ValueError("At least 30 labelled rows are required for AutoML.")
    if len(working) > max_rows:
        working = working.sample(max_rows, random_state=random_state).sort_index().reset_index(drop=True)
    task = task or infer_task(working[target_column])
    y, label_mapping = _prepare_target(working[target_column], task)
    usable = y.notna()
    working = working.loc[usable].reset_index(drop=True)
    y = y.loc[usable].reset_index(drop=True)
    x = working.drop(columns=[target_column]).copy()
    if x.empty:
        raise ValueError("No predictor columns remain after removing the target.")
    if task == "classification" and y.value_counts().min() < 5:
        raise ValueError("Each class requires at least five rows for bounded cross-validation.")

    indices = np.arange(len(working))
    stratify = y if task == "classification" else None
    train_idx, test_idx = train_test_split(
        indices,
        test_size=holdout_fraction,
        random_state=random_state,
        stratify=stratify,
    )
    x_train, x_test = x.iloc[train_idx], x.iloc[test_idx]
    y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]
    if task == "classification":
        folds = min(cv_folds, int(y_train.value_counts().min()))
        splitter: Any = StratifiedKFold(n_splits=max(2, folds), shuffle=True, random_state=random_state)
    else:
        folds = min(cv_folds, max(2, len(y_train) // 10))
        splitter = KFold(n_splits=max(2, folds), shuffle=True, random_state=random_state)

    leaderboard_rows: list[dict[str, Any]] = []
    fitted_candidates: dict[str, Pipeline] = {}
    candidates = _candidate_catalog(task, random_state)[: max(1, max_candidates)]
    for name, pipeline in candidates:
        dense = name != "logistic_l2" and name not in {"ridge", "elastic_net"}
        pipeline.set_params(preprocessor=_preprocessor(x_train, dense=dense))
        started = perf_counter()
        result = cross_validate(
            pipeline,
            x_train,
            y_train,
            cv=splitter,
            scoring=_scoring(task),
            n_jobs=1,
            return_train_score=False,
            error_score="raise",
        )
        elapsed = perf_counter() - started
        row: dict[str, Any] = {
            "candidate": name,
            "cv_folds": splitter.n_splits,
            "fit_seconds": elapsed,
        }
        if task == "classification":
            for metric in ("roc_auc", "balanced_accuracy", "f1"):
                values = result[f"test_{metric}"]
                row[f"mean_test_{metric}"] = float(np.mean(values))
                row[f"std_test_{metric}"] = float(np.std(values, ddof=1)) if len(values) > 1 else 0.0
        else:
            rmse = -result["test_rmse"]
            mae = -result["test_mae"]
            row.update(
                {
                    "mean_test_rmse": float(np.mean(rmse)),
                    "std_test_rmse": float(np.std(rmse, ddof=1)) if len(rmse) > 1 else 0.0,
                    "mean_test_mae": float(np.mean(mae)),
                    "mean_test_r2": float(np.mean(result["test_r2"])),
                }
            )
        fitted_candidates[name] = pipeline.fit(x_train, y_train)
        leaderboard_rows.append(row)

    leaderboard = pd.DataFrame(leaderboard_rows)
    primary, descending = _primary(task)
    leaderboard = leaderboard.sort_values(primary, ascending=not descending).reset_index(drop=True)
    leaderboard["rank"] = np.arange(1, len(leaderboard) + 1)
    champion_name = str(leaderboard.iloc[0]["candidate"])
    champion = fitted_candidates[champion_name]

    if task == "classification":
        probabilities = champion.predict_proba(x_test)[:, 1]
        predictions = (probabilities >= 0.5).astype(int)
        holdout_metrics = {
            "roc_auc": float(roc_auc_score(y_test, probabilities)),
            "balanced_accuracy": float(balanced_accuracy_score(y_test, predictions)),
            "f1": float(f1_score(y_test, predictions, zero_division=0)),
        }
        prediction_frame = pd.DataFrame(
            {
                "row_index": test_idx,
                "observed": y_test.to_numpy(),
                "predicted": predictions,
                "probability_positive": probabilities,
            }
        )
        scoring = "roc_auc"
    else:
        predictions = champion.predict(x_test)
        holdout_metrics = {
            "rmse": float(np.sqrt(mean_squared_error(y_test, predictions))),
            "mae": float(mean_absolute_error(y_test, predictions)),
            "r2": float(r2_score(y_test, predictions)),
        }
        prediction_frame = pd.DataFrame(
            {
                "row_index": test_idx,
                "observed": y_test.to_numpy(),
                "predicted": predictions,
                "residual": y_test.to_numpy() - predictions,
            }
        )
        scoring = "neg_root_mean_squared_error"

    importance_result = permutation_importance(
        champion,
        x_test,
        y_test,
        scoring=scoring,
        n_repeats=5,
        random_state=random_state,
        n_jobs=1,
    )
    feature_importance = pd.DataFrame(
        {
            "feature": list(x.columns),
            "importance_mean": importance_result.importances_mean,
            "importance_std": importance_result.importances_std,
        }
    ).sort_values("importance_mean", ascending=False).reset_index(drop=True)

    buffer = io.BytesIO()
    joblib.dump(champion, buffer, compress=3)
    artifact_bytes = buffer.getvalue()
    digest = pd.util.hash_pandas_object(working.astype("string").fillna(""), index=True).values.tobytes()
    search_manifest = {
        "schema": "biointel.step121.automl_search.v1",
        "task": task,
        "target": target_column,
        "rows_used": len(working),
        "feature_count": len(x.columns),
        "candidate_count": len(candidates),
        "cv_folds": splitter.n_splits,
        "holdout_fraction": holdout_fraction,
        "random_state": random_state,
        "input_sha256": sha256(digest).hexdigest(),
        "champion": champion_name,
        "artifact_sha256": sha256(artifact_bytes).hexdigest(),
        "search_engine": "deterministic_bounded_catalog",
        "optuna_used": False,
        "onnx_exported": False,
    }
    model_card = {
        "schema": "biointel.step121.model_card.v1",
        "model_name": champion_name,
        "task": task,
        "target": target_column,
        "label_mapping": label_mapping,
        "training_rows": len(train_idx),
        "holdout_rows": len(test_idx),
        "features": list(x.columns),
        "holdout_metrics": holdout_metrics,
        "intended_use": "Research benchmarking and local decision support.",
        "limitations": [
            "No external validation cohort was used by this local search.",
            "Candidate catalog is deliberately bounded and is not an exhaustive hyperparameter search.",
            "Feature importance is predictive, not causal.",
            "Production deployment requires leakage review, subgroup review, calibration and independent validation.",
        ],
        "release_ready": False,
    }
    return AutoMLResult(
        task=task,
        leaderboard=leaderboard,
        feature_importance=feature_importance,
        holdout_predictions=prediction_frame,
        model_card=model_card,
        search_manifest=search_manifest,
        artifact_bytes=artifact_bytes,
    )


def model_card_json(result: AutoMLResult) -> str:
    return json.dumps(result.model_card, indent=2, sort_keys=True)
