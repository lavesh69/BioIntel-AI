from __future__ import annotations

import hashlib
import io
import json
import pickletools
import zipfile
from dataclasses import dataclass
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
    roc_curve,
)
from sklearn.model_selection import StratifiedKFold, cross_val_predict, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

AMINO_ACIDS = "ACDEFGHIKLMNPQRSTVWY"
HYDROPHOBIC = set("AVILMFWY")
POSITIVE = set("KRH")
NEGATIVE = set("DE")
AROMATIC = set("FWY")

REQUIRED_COLUMNS = ("protein_a", "protein_b", "sequence_a", "sequence_b")
FEATURE_COLUMNS = (
    "length_a",
    "length_b",
    "length_ratio",
    "composition_cosine",
    "dipeptide_jaccard",
    "hydrophobic_difference",
    "charge_difference",
    "aromatic_difference",
    "entropy_difference",
    "shared_tripeptide_fraction",
)


@dataclass(frozen=True)
class PPIModelResult:
    algorithm: str
    metrics: dict[str, float]
    confusion: list[list[int]]
    roc_points: pd.DataFrame
    predictions: pd.DataFrame
    feature_importance: pd.DataFrame
    warning: str | None = None
    estimator: Any | None = None
    decision_threshold: float = 0.5
    model_fingerprint: str = ""


def _clean_sequence(value: Any) -> str:
    sequence = "".join(str(value).upper().split())
    invalid = sorted(set(sequence) - set(AMINO_ACIDS))
    if not sequence:
        raise ValueError("Protein sequence cannot be empty.")
    if invalid:
        raise ValueError(f"Unsupported amino-acid symbols: {', '.join(invalid)}")
    return sequence


def _canonical_pair_ids(frame: pd.DataFrame) -> pd.Series:
    return frame.apply(
        lambda row: "::".join(sorted((str(row["protein_a"]), str(row["protein_b"])))),
        axis=1,
    )


def _identifier_sequence_conflicts(frame: pd.DataFrame) -> dict[str, set[str]]:
    """Return protein identifiers that map to more than one sequence."""
    lookup: dict[str, set[str]] = {}
    for row in frame.itertuples(index=False):
        lookup.setdefault(str(row.protein_a), set()).add(str(row.sequence_a))
        lookup.setdefault(str(row.protein_b), set()).add(str(row.sequence_b))
    return {identifier: sequences for identifier, sequences in lookup.items() if len(sequences) > 1}


def validate_pair_table(
    frame: pd.DataFrame,
    *,
    require_label: bool = False,
    deduplicate: bool = True,
    allow_conflicting_labels: bool = False,
) -> pd.DataFrame:
    missing = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")
    cleaned = frame.copy()
    cleaned["protein_a"] = cleaned["protein_a"].astype(str).str.strip()
    cleaned["protein_b"] = cleaned["protein_b"].astype(str).str.strip()
    cleaned["sequence_a"] = cleaned["sequence_a"].map(_clean_sequence)
    cleaned["sequence_b"] = cleaned["sequence_b"].map(_clean_sequence)
    if (cleaned["protein_a"] == "").any() or (cleaned["protein_b"] == "").any():
        raise ValueError("Protein identifiers cannot be empty.")
    if require_label and "label" not in cleaned.columns:
        raise ValueError("Training data requires a binary label column.")
    if "label" in cleaned.columns:
        labels = pd.to_numeric(cleaned["label"], errors="coerce")
        if labels.isna().any() or not set(labels.astype(int).unique()).issubset({0, 1}):
            raise ValueError("label must contain only binary values 0 and 1.")
        cleaned["label"] = labels.astype(int)
    sequence_conflicts = _identifier_sequence_conflicts(cleaned)
    if sequence_conflicts:
        preview = ", ".join(sorted(sequence_conflicts)[:5])
        raise ValueError(
            "Protein identifiers must map to exactly one amino-acid sequence. "
            f"Conflicts found for: {preview}."
        )
    cleaned["pair_id"] = _canonical_pair_ids(cleaned)
    if "label" in cleaned.columns:
        conflicting = cleaned.groupby("pair_id")["label"].nunique()
        conflicting = conflicting[conflicting > 1]
        if not conflicting.empty and not allow_conflicting_labels:
            preview = ", ".join(conflicting.index.astype(str).tolist()[:5])
            raise ValueError(
                "Conflicting labels were found for the same unordered protein pair: "
                f"{preview}. Resolve these rows before model training."
            )
    if deduplicate:
        cleaned = cleaned.drop_duplicates("pair_id", keep="first")
    return cleaned.reset_index(drop=True)


def _training_fingerprint(
    frame: pd.DataFrame,
    *,
    algorithm: str,
    random_state: int,
    decision_threshold: float,
) -> str:
    canonical = validate_pair_table(frame, require_label=True).sort_values("pair_id")
    payload = canonical[[*REQUIRED_COLUMNS, "label", "pair_id"]].to_csv(index=False)
    configuration = f"{algorithm}|{random_state}|{decision_threshold:.8f}|{','.join(FEATURE_COLUMNS)}"
    return hashlib.sha256(f"{configuration}\n{payload}".encode("utf-8")).hexdigest()


def _composition(sequence: str) -> np.ndarray:
    counts = np.array([sequence.count(amino_acid) for amino_acid in AMINO_ACIDS], dtype=float)
    return counts / max(len(sequence), 1)


def _fraction(sequence: str, alphabet: set[str]) -> float:
    return sum(character in alphabet for character in sequence) / max(len(sequence), 1)


def _entropy(sequence: str) -> float:
    composition = _composition(sequence)
    nonzero = composition[composition > 0]
    return float(-(nonzero * np.log2(nonzero)).sum())


def _kmers(sequence: str, k: int) -> set[str]:
    if len(sequence) < k:
        return {sequence}
    return {sequence[index : index + k] for index in range(len(sequence) - k + 1)}


def _jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def pair_features(sequence_a: str, sequence_b: str) -> dict[str, float]:
    left = _clean_sequence(sequence_a)
    right = _clean_sequence(sequence_b)
    comp_left = _composition(left)
    comp_right = _composition(right)
    denominator = float(np.linalg.norm(comp_left) * np.linalg.norm(comp_right))
    cosine = float(np.dot(comp_left, comp_right) / denominator) if denominator else 0.0
    tri_left = _kmers(left, 3)
    tri_right = _kmers(right, 3)
    shared_tri = len(tri_left & tri_right) / max(min(len(tri_left), len(tri_right)), 1)
    return {
        "length_a": float(len(left)),
        "length_b": float(len(right)),
        "length_ratio": min(len(left), len(right)) / max(len(left), len(right)),
        "composition_cosine": cosine,
        "dipeptide_jaccard": _jaccard(_kmers(left, 2), _kmers(right, 2)),
        "hydrophobic_difference": abs(_fraction(left, HYDROPHOBIC) - _fraction(right, HYDROPHOBIC)),
        "charge_difference": abs(
            (_fraction(left, POSITIVE) - _fraction(left, NEGATIVE))
            - (_fraction(right, POSITIVE) - _fraction(right, NEGATIVE))
        ),
        "aromatic_difference": abs(_fraction(left, AROMATIC) - _fraction(right, AROMATIC)),
        "entropy_difference": abs(_entropy(left) - _entropy(right)),
        "shared_tripeptide_fraction": float(shared_tri),
    }


def build_feature_matrix(frame: pd.DataFrame) -> pd.DataFrame:
    cleaned = validate_pair_table(frame, require_label=False)
    records: list[dict[str, Any]] = []
    for row in cleaned.itertuples(index=False):
        features = pair_features(row.sequence_a, row.sequence_b)
        record: dict[str, Any] = {
            "pair_id": row.pair_id,
            "protein_a": row.protein_a,
            "protein_b": row.protein_b,
            **features,
        }
        if hasattr(row, "label"):
            record["label"] = int(row.label)
        records.append(record)
    return pd.DataFrame(records)


def _model_for_algorithm(algorithm: str, random_state: int) -> Any:
    if algorithm == "Logistic regression":
        return Pipeline(
            [
                ("scale", StandardScaler()),
                (
                    "model",
                    LogisticRegression(
                        max_iter=3000,
                        class_weight="balanced",
                        random_state=random_state,
                    ),
                ),
            ]
        )
    if algorithm == "Random forest":
        return RandomForestClassifier(
            n_estimators=350,
            min_samples_leaf=2,
            class_weight="balanced_subsample",
            random_state=random_state,
            n_jobs=-1,
        )
    if algorithm == "Calibrated random forest":
        base = RandomForestClassifier(
            n_estimators=300,
            min_samples_leaf=2,
            class_weight="balanced_subsample",
            random_state=random_state,
            n_jobs=-1,
        )
        return CalibratedClassifierCV(base, method="sigmoid", cv=3)
    raise ValueError(f"Unsupported algorithm: {algorithm}")


def train_ppi_classifier(
    frame: pd.DataFrame,
    *,
    algorithm: str = "Random forest",
    test_size: float = 0.25,
    random_state: int = 42,
    decision_threshold: float = 0.5,
) -> PPIModelResult:
    if not 0 < float(decision_threshold) < 1:
        raise ValueError("decision_threshold must be between 0 and 1.")
    cleaned = validate_pair_table(frame, require_label=True)
    if len(cleaned) < 20:
        raise ValueError("At least 20 labelled protein pairs are required for model training.")
    class_counts = cleaned["label"].value_counts()
    if len(class_counts) != 2 or int(class_counts.min()) < 5:
        raise ValueError("Both interaction classes need at least five examples.")
    matrix = build_feature_matrix(cleaned)
    x = matrix[list(FEATURE_COLUMNS)]
    y = matrix["label"].astype(int)
    train_x, test_x, train_y, test_y, train_index, test_index = train_test_split(
        x,
        y,
        np.arange(len(matrix)),
        test_size=float(test_size),
        stratify=y,
        random_state=random_state,
    )
    model = _model_for_algorithm(algorithm, random_state)
    model.fit(train_x, train_y)
    probabilities = model.predict_proba(test_x)[:, 1]
    predicted = (probabilities >= float(decision_threshold)).astype(int)
    metrics = {
        "roc_auc": float(roc_auc_score(test_y, probabilities)),
        "balanced_accuracy": float(balanced_accuracy_score(test_y, predicted)),
        "accuracy": float(accuracy_score(test_y, predicted)),
        "precision": float(precision_score(test_y, predicted, zero_division=0)),
        "recall": float(recall_score(test_y, predicted, zero_division=0)),
        "f1": float(f1_score(test_y, predicted, zero_division=0)),
        "test_pairs": float(len(test_y)),
        "training_pairs": float(len(train_y)),
    }
    fpr, tpr, thresholds = roc_curve(test_y, probabilities)
    roc_points = pd.DataFrame({"false_positive_rate": fpr, "true_positive_rate": tpr, "threshold": thresholds})
    predictions = matrix.iloc[test_index][["pair_id", "protein_a", "protein_b", "label"]].copy()
    predictions["interaction_probability"] = probabilities
    predictions["predicted_label"] = predicted
    predictions["decision_threshold"] = float(decision_threshold)
    predictions["correct"] = predictions["label"] == predictions["predicted_label"]

    importance = np.zeros(len(FEATURE_COLUMNS), dtype=float)
    estimator = model
    if isinstance(model, Pipeline):
        estimator = model.named_steps["model"]
    if hasattr(estimator, "feature_importances_"):
        importance = np.asarray(estimator.feature_importances_, dtype=float)
    elif hasattr(estimator, "coef_"):
        importance = np.abs(np.asarray(estimator.coef_[0], dtype=float))
    feature_importance = pd.DataFrame(
        {"feature": FEATURE_COLUMNS, "importance": importance}
    ).sort_values("importance", ascending=False)

    warning = (
        "This evaluation uses a stratified pair split. Protein-disjoint or species-disjoint external validation is still required before biological claims."
    )
    return PPIModelResult(
        algorithm=algorithm,
        metrics=metrics,
        confusion=confusion_matrix(test_y, predicted, labels=[0, 1]).astype(int).tolist(),
        roc_points=roc_points,
        predictions=predictions.reset_index(drop=True),
        feature_importance=feature_importance.reset_index(drop=True),
        warning=warning,
        estimator=model,
        decision_threshold=float(decision_threshold),
        model_fingerprint=_training_fingerprint(
            cleaned,
            algorithm=algorithm,
            random_state=random_state,
            decision_threshold=float(decision_threshold),
        ),
    )


def compare_algorithms(frame: pd.DataFrame, *, random_state: int = 42) -> pd.DataFrame:
    cleaned = validate_pair_table(frame, require_label=True)
    matrix = build_feature_matrix(cleaned)
    x = matrix[list(FEATURE_COLUMNS)]
    y = matrix["label"].astype(int)
    smallest_class = int(y.value_counts().min())
    folds = max(2, min(5, smallest_class))
    cv = StratifiedKFold(n_splits=folds, shuffle=True, random_state=random_state)
    rows = []
    for algorithm in ("Logistic regression", "Random forest"):
        model = _model_for_algorithm(algorithm, random_state)
        probabilities = cross_val_predict(model, x, y, cv=cv, method="predict_proba")[:, 1]
        predicted = (probabilities >= 0.5).astype(int)
        rows.append(
            {
                "algorithm": algorithm,
                "cv_folds": folds,
                "roc_auc": roc_auc_score(y, probabilities),
                "balanced_accuracy": balanced_accuracy_score(y, predicted),
                "f1": f1_score(y, predicted, zero_division=0),
                "precision": precision_score(y, predicted, zero_division=0),
                "recall": recall_score(y, predicted, zero_division=0),
            }
        )
    return pd.DataFrame(rows).sort_values("roc_auc", ascending=False).reset_index(drop=True)


def demo_ppi_pairs(n_pairs: int = 120, random_state: int = 17) -> pd.DataFrame:
    rng = np.random.default_rng(random_state)
    family_alphabets = (
        "AVLIMFWY",
        "KRHDE",
        "GSTNQ",
        "ACPG",
        "YFWHQL",
    )
    proteins: dict[str, tuple[str, int]] = {}
    members: dict[int, list[str]] = {index: [] for index in range(len(family_alphabets))}
    protein_count = max(50, n_pairs)
    for index in range(protein_count):
        family = index % len(family_alphabets)
        biased = list(family_alphabets[family])
        length = int(rng.integers(100, 240))
        choose_family = rng.random(length) < 0.72
        sequence = [
            str(rng.choice(biased if use_family else list(AMINO_ACIDS)))
            for use_family in choose_family
        ]
        identifier = f"P{index + 1:04d}"
        proteins[identifier] = ("".join(sequence), family)
        members[family].append(identifier)

    records = []
    seen: set[tuple[str, str]] = set()
    target_positive = n_pairs // 2
    target_negative = n_pairs - target_positive
    class_targets = [1] * target_positive + [0] * target_negative
    rng.shuffle(class_targets)
    for intended_label in class_targets:
        for _ in range(2000):
            family_left = int(rng.integers(0, len(family_alphabets)))
            family_right = family_left if intended_label else int(rng.choice([value for value in range(len(family_alphabets)) if value != family_left]))
            left = str(rng.choice(members[family_left]))
            right = str(rng.choice(members[family_right]))
            if left == right:
                continue
            pair = tuple(sorted((left, right)))
            if pair in seen:
                continue
            seen.add(pair)
            seq_left, _ = proteins[left]
            seq_right, _ = proteins[right]
            label = intended_label ^ int(rng.random() < 0.08)
            records.append(
                {
                    "protein_a": left,
                    "protein_b": right,
                    "sequence_a": seq_left,
                    "sequence_b": seq_right,
                    "label": label,
                    "source": "deterministic_demo",
                }
            )
            break
    return pd.DataFrame(records)


def score_candidate_pairs(model_result: PPIModelResult, frame: pd.DataFrame) -> pd.DataFrame:
    if model_result.estimator is None:
        raise ValueError("This model result does not contain a fitted estimator.")
    candidate_matrix = build_feature_matrix(validate_pair_table(frame, require_label=False))
    probabilities = model_result.estimator.predict_proba(candidate_matrix[list(FEATURE_COLUMNS)])[:, 1]
    scored = candidate_matrix[["pair_id", "protein_a", "protein_b"]].copy()
    scored["interaction_probability"] = probabilities
    scored["predicted_label"] = (probabilities >= model_result.decision_threshold).astype(int)
    scored["confidence_band"] = pd.cut(
        probabilities,
        bins=[-np.inf, 0.35, 0.65, np.inf],
        labels=["Low", "Uncertain", "High"],
    ).astype(str)
    scored["decision_threshold"] = model_result.decision_threshold
    scored["model_fingerprint"] = model_result.model_fingerprint
    return scored.sort_values("interaction_probability", ascending=False).reset_index(drop=True)


def _scan_ppi_pickle(payload: bytes) -> None:
    """Reject common arbitrary-code pickle gadgets before deserialization.

    Pickle cannot be made safe for arbitrary third-party input. This defensive
    inspection is therefore paired with a checksum-bound BioIntel bundle and an
    explicit trusted-export boundary in the UI.
    """

    allowed_prefixes = (
        "builtins",
        "collections",
        "copyreg",
        "joblib",
        "numpy",
        "scipy",
        "sklearn",
    )
    dangerous_opcodes = {"EXT1", "EXT2", "EXT4", "PERSID", "BINPERSID"}
    dangerous_pairs = {
        ("builtins", "eval"),
        ("builtins", "exec"),
        ("builtins", "compile"),
        ("builtins", "open"),
        ("os", "system"),
        ("posix", "system"),
        ("subprocess", "Popen"),
    }
    recent_strings: list[str] = []
    try:
        for opcode, argument, _position in pickletools.genops(payload):
            name = opcode.name
            if name in dangerous_opcodes:
                raise ValueError(f"Unsupported pickle opcode: {name}")
            if name == "GLOBAL":
                module, _, symbol = str(argument).partition(" ")
                if (module, symbol) in dangerous_pairs or not module.startswith(allowed_prefixes):
                    raise ValueError(f"Unsafe model global blocked: {module}.{symbol}")
            elif name in {"UNICODE", "BINUNICODE", "SHORT_BINUNICODE", "BINUNICODE8", "STRING"}:
                recent_strings.append(str(argument))
                recent_strings = recent_strings[-8:]
            elif name == "STACK_GLOBAL" and len(recent_strings) >= 2:
                module, symbol = recent_strings[-2], recent_strings[-1]
                if (module, symbol) in dangerous_pairs:
                    raise ValueError(f"Unsafe model global blocked: {module}.{symbol}")
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"The model payload failed pickle inspection: {exc}") from exc

    lowered = payload.lower()
    blocked_fragments = (
        b"os\nsystem",
        b"posix\nsystem",
        b"subprocess\npopen",
        b"builtins\neval",
        b"builtins\nexec",
    )
    if any(fragment in lowered for fragment in blocked_fragments):
        raise ValueError("The model payload contains a blocked executable pickle reference.")


def serialize_ppi_model(model_result: PPIModelResult) -> bytes:
    """Serialize a fitted PPI estimator inside a checksum-bound BioIntel bundle."""

    if model_result.estimator is None:
        raise ValueError("This model result does not contain a fitted estimator.")
    model_buffer = io.BytesIO()
    joblib.dump(
        {
            "schema_version": "2.0",
            "algorithm": model_result.algorithm,
            "feature_columns": list(FEATURE_COLUMNS),
            "decision_threshold": float(model_result.decision_threshold),
            "model_fingerprint": model_result.model_fingerprint,
            "metrics": model_result.metrics,
            "estimator": model_result.estimator,
        },
        model_buffer,
        compress=0,
    )
    model_bytes = model_buffer.getvalue()
    manifest = {
        "schema": "biointel.ppi_model_bundle.v2",
        "artifact_name": "model.joblib",
        "artifact_sha256": hashlib.sha256(model_bytes).hexdigest(),
        "artifact_size_bytes": len(model_bytes),
        "algorithm": model_result.algorithm,
        "feature_columns": list(FEATURE_COLUMNS),
        "decision_threshold": float(model_result.decision_threshold),
        "model_fingerprint": model_result.model_fingerprint,
        "metrics": model_result.metrics,
        "security_boundary": "Load only bundles exported by a trusted BioIntel AI installation.",
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True))
        archive.writestr("model.joblib", model_bytes)
    return output.getvalue()


def load_ppi_model(
    payload: bytes,
    *,
    allow_legacy: bool = False,
    max_size_mb: int = 250,
) -> PPIModelResult:
    """Load a checksum-bound PPI model bundle with contract and smoke validation."""

    raw = bytes(payload)
    if not raw:
        raise ValueError("The uploaded model file is empty.")
    if len(raw) > int(max_size_mb) * 1024 * 1024:
        raise ValueError(f"The model exceeds the {int(max_size_mb)} MB safety limit.")

    manifest: dict[str, Any]
    model_bytes: bytes
    if raw.startswith(b"PK"):
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                names = set(archive.namelist())
                if names != {"manifest.json", "model.joblib"}:
                    raise ValueError(
                        "The PPI bundle must contain exactly manifest.json and model.joblib."
                    )
                if any(".." in name.replace("\\", "/").split("/") for name in names):
                    raise ValueError("Unsafe archive paths are not allowed.")
                manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
                model_bytes = archive.read("model.joblib")
        except (zipfile.BadZipFile, KeyError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError("The PPI model bundle is corrupt or incomplete.") from exc
        if manifest.get("schema") != "biointel.ppi_model_bundle.v2":
            raise ValueError("The PPI model bundle schema is unsupported.")
        if int(manifest.get("artifact_size_bytes", -1)) != len(model_bytes):
            raise ValueError("The PPI model payload size does not match its manifest.")
        observed_digest = hashlib.sha256(model_bytes).hexdigest()
        if observed_digest != str(manifest.get("artifact_sha256", "")):
            raise ValueError("The PPI model payload checksum does not match its manifest.")
    else:
        if not allow_legacy:
            raise ValueError(
                "Legacy raw .joblib/.pkl uploads are blocked. Export a Step 97 .bioippimodel bundle, "
                "or explicitly enable legacy migration for a trusted local artifact."
            )
        manifest = {"schema": "legacy", "feature_columns": list(FEATURE_COLUMNS)}
        model_bytes = raw

    _scan_ppi_pickle(model_bytes)
    try:
        artifact = joblib.load(io.BytesIO(model_bytes))
    except Exception as exc:
        raise ValueError(f"The model payload could not be deserialized: {exc}") from exc
    if not isinstance(artifact, dict):
        raise ValueError("The model payload is not a compatible BioIntel PPI artifact.")
    if artifact.get("feature_columns") != list(FEATURE_COLUMNS):
        raise ValueError("The model feature contract is incompatible with this application version.")
    algorithm = str(artifact.get("algorithm", ""))
    if algorithm not in {"Logistic regression", "Random forest", "Calibrated random forest"}:
        raise ValueError(f"Unsupported PPI algorithm in model bundle: {algorithm or '(missing)'}")
    estimator = artifact.get("estimator")
    if estimator is None or not callable(getattr(estimator, "predict_proba", None)):
        raise ValueError("The model does not expose the required predict_proba interface.")
    threshold = float(artifact.get("decision_threshold", 0.5))
    if not 0.0 < threshold < 1.0:
        raise ValueError("The model decision threshold is outside the valid range (0, 1).")
    # Execute a one-row contract probe before accepting the artifact into the UI.
    probe = pd.DataFrame(np.zeros((1, len(FEATURE_COLUMNS))), columns=list(FEATURE_COLUMNS))
    try:
        probabilities = np.asarray(estimator.predict_proba(probe), dtype=float)
    except Exception as exc:
        raise ValueError(f"The model failed its inference contract probe: {exc}") from exc
    if probabilities.shape != (1, 2) or not np.isfinite(probabilities).all():
        raise ValueError("The model returned an invalid probability matrix during validation.")
    return PPIModelResult(
        algorithm=algorithm,
        metrics=dict(artifact.get("metrics", {})),
        confusion=[],
        roc_points=pd.DataFrame(),
        predictions=pd.DataFrame(),
        feature_importance=pd.DataFrame(),
        warning="Loaded checksum-bound inference bundle; evaluation tables are not embedded.",
        estimator=estimator,
        decision_threshold=threshold,
        model_fingerprint=str(artifact.get("model_fingerprint", "")),
    )


def train_and_score_ppi_classifier(
    training_frame: pd.DataFrame,
    candidate_frame: pd.DataFrame,
    *,
    algorithm: str = "Random forest",
    random_state: int = 42,
    test_size: float = 0.25,
    decision_threshold: float = 0.5,
) -> tuple[PPIModelResult, pd.DataFrame]:
    result = train_ppi_classifier(
        training_frame,
        algorithm=algorithm,
        random_state=random_state,
        test_size=test_size,
        decision_threshold=decision_threshold,
    )
    # Fit the deployable estimator on all validated training pairs after the held-out evaluation.
    training = validate_pair_table(training_frame, require_label=True)
    train_matrix = build_feature_matrix(training)
    deployable = _model_for_algorithm(algorithm, random_state)
    deployable.fit(train_matrix[list(FEATURE_COLUMNS)], train_matrix["label"].astype(int))
    result = PPIModelResult(
        algorithm=result.algorithm,
        metrics=result.metrics,
        confusion=result.confusion,
        roc_points=result.roc_points,
        predictions=result.predictions,
        feature_importance=result.feature_importance,
        warning=result.warning,
        estimator=deployable,
        decision_threshold=float(decision_threshold),
        model_fingerprint=result.model_fingerprint,
    )
    return result, score_candidate_pairs(result, candidate_frame)


def pair_dataset_qc(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, float | int]]:
    missing = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")
    cleaned = frame.copy()
    cleaned["protein_a"] = cleaned["protein_a"].astype(str).str.strip()
    cleaned["protein_b"] = cleaned["protein_b"].astype(str).str.strip()
    cleaned["sequence_a"] = cleaned["sequence_a"].map(_clean_sequence)
    cleaned["sequence_b"] = cleaned["sequence_b"].map(_clean_sequence)
    if "label" in cleaned.columns:
        labels = pd.to_numeric(cleaned["label"], errors="coerce")
        if labels.isna().any() or not set(labels.astype(int).unique()).issubset({0, 1}):
            raise ValueError("label must contain only binary values 0 and 1.")
        cleaned["label"] = labels.astype(int)
    cleaned["pair_id"] = _canonical_pair_ids(cleaned)
    canonical = cleaned.apply(lambda row: "|".join(sorted((str(row["protein_a"]), str(row["protein_b"])))), axis=1)
    sequence_lookup: dict[str, set[str]] = {}
    for row in cleaned.itertuples(index=False):
        sequence_lookup.setdefault(str(row.protein_a), set()).add(str(row.sequence_a))
        sequence_lookup.setdefault(str(row.protein_b), set()).add(str(row.sequence_b))
    inconsistent_ids = sum(1 for sequences in sequence_lookup.values() if len(sequences) > 1)
    duplicate_count = int(canonical.duplicated().sum())
    conflicting_label_pairs = 0
    if "label" in cleaned.columns:
        conflicting_label_pairs = int((cleaned.assign(_canonical=canonical).groupby("_canonical")["label"].nunique() > 1).sum())
    rows = [
        {"check": "Rows", "value": len(cleaned), "status": "Pass", "detail": "Validated protein-pair records"},
        {"check": "Unique proteins", "value": len(sequence_lookup), "status": "Pass", "detail": "Identifiers observed across both pair columns"},
        {"check": "Duplicate unordered pairs", "value": duplicate_count, "status": "Review" if duplicate_count else "Pass", "detail": "A-B and B-A are treated as the same pair"},
        {"check": "Conflicting pair labels", "value": conflicting_label_pairs, "status": "Fail" if conflicting_label_pairs else "Pass", "detail": "The same unordered pair must not have both class labels"},
        {"check": "Self interactions", "value": int((cleaned["protein_a"] == cleaned["protein_b"]).sum()), "status": "Review" if (cleaned["protein_a"] == cleaned["protein_b"]).any() else "Pass", "detail": "Self-pairs may be valid but need deliberate handling"},
        {"check": "Identifier/sequence conflicts", "value": inconsistent_ids, "status": "Fail" if inconsistent_ids else "Pass", "detail": "One protein identifier should map to one sequence"},
    ]
    if "label" in cleaned.columns:
        counts = cleaned["label"].value_counts()
        imbalance = float(counts.max() / max(counts.min(), 1)) if len(counts) == 2 else float("inf")
        rows.append({"check": "Class imbalance ratio", "value": imbalance, "status": "Review" if imbalance > 3 else "Pass", "detail": "Majority/minority class ratio"})
    summary = {
        "pairs": len(cleaned),
        "unique_proteins": len(sequence_lookup),
        "duplicate_pairs": duplicate_count,
        "conflicting_label_pairs": conflicting_label_pairs,
        "self_interactions": int((cleaned["protein_a"] == cleaned["protein_b"]).sum()),
        "identifier_sequence_conflicts": inconsistent_ids,
    }
    return pd.DataFrame(rows), summary


def precision_recall_points(predictions: pd.DataFrame) -> pd.DataFrame:
    from sklearn.metrics import precision_recall_curve

    required = {"label", "interaction_probability"}
    if not required.issubset(predictions.columns):
        raise ValueError("Predictions require label and interaction_probability columns.")
    precision, recall, thresholds = precision_recall_curve(
        predictions["label"].astype(int), predictions["interaction_probability"].astype(float)
    )
    aligned = np.append(thresholds, 1.0)
    return pd.DataFrame({"precision": precision, "recall": recall, "threshold": aligned})


def threshold_analysis(predictions: pd.DataFrame, *, steps: int = 41) -> pd.DataFrame:
    required = {"label", "interaction_probability"}
    if not required.issubset(predictions.columns):
        raise ValueError("Predictions require label and interaction_probability columns.")
    truth = predictions["label"].astype(int).to_numpy()
    probability = predictions["interaction_probability"].astype(float).to_numpy()
    rows = []
    for threshold in np.linspace(0.05, 0.95, steps):
        called = (probability >= threshold).astype(int)
        tp = int(((called == 1) & (truth == 1)).sum())
        tn = int(((called == 0) & (truth == 0)).sum())
        fp = int(((called == 1) & (truth == 0)).sum())
        fn = int(((called == 0) & (truth == 1)).sum())
        precision = tp / max(tp + fp, 1)
        recall = tp / max(tp + fn, 1)
        specificity = tn / max(tn + fp, 1)
        f1 = 2 * precision * recall / max(precision + recall, 1e-12)
        rows.append({
            "threshold": float(threshold),
            "precision": precision,
            "recall": recall,
            "specificity": specificity,
            "f1": f1,
            "balanced_accuracy": (recall + specificity) / 2,
            "predicted_positive": int(called.sum()),
        })
    return pd.DataFrame(rows)


def calibration_table(predictions: pd.DataFrame, *, bins: int = 8) -> pd.DataFrame:
    required = {"label", "interaction_probability"}
    if not required.issubset(predictions.columns):
        raise ValueError("Predictions require label and interaction_probability columns.")
    frame = predictions[["label", "interaction_probability"]].copy()
    frame["probability_bin"] = pd.cut(
        frame["interaction_probability"], bins=np.linspace(0, 1, bins + 1), include_lowest=True, duplicates="drop"
    )
    grouped = frame.groupby("probability_bin", observed=True).agg(
        mean_predicted_probability=("interaction_probability", "mean"),
        observed_interaction_rate=("label", "mean"),
        pairs=("label", "size"),
    ).reset_index()
    grouped["probability_bin"] = grouped["probability_bin"].astype(str)
    grouped["absolute_calibration_error"] = (
        grouped["mean_predicted_probability"] - grouped["observed_interaction_rate"]
    ).abs()
    return grouped


def split_leakage_audit(training_frame: pd.DataFrame, test_predictions: pd.DataFrame) -> pd.DataFrame:
    cleaned = validate_pair_table(training_frame, require_label=True)
    test_ids = set(test_predictions["pair_id"].astype(str))
    matrix = build_feature_matrix(cleaned)
    test_rows = matrix[matrix["pair_id"].isin(test_ids)]
    train_rows = matrix[~matrix["pair_id"].isin(test_ids)]
    train_proteins = set(train_rows["protein_a"]) | set(train_rows["protein_b"])
    test_proteins = set(test_rows["protein_a"]) | set(test_rows["protein_b"])
    overlap = train_proteins & test_proteins
    return pd.DataFrame(
        [
            {"measure": "Training proteins", "value": len(train_proteins), "interpretation": "Unique proteins in model-fitting pairs"},
            {"measure": "Held-out proteins", "value": len(test_proteins), "interpretation": "Unique proteins in evaluation pairs"},
            {"measure": "Proteins shared across split", "value": len(overlap), "interpretation": "Pair split permits protein identity overlap"},
            {"measure": "Held-out overlap percent", "value": 100 * len(overlap) / max(len(test_proteins), 1), "interpretation": "Use protein-disjoint external validation for stronger evidence"},
        ]
    )


def candidate_network_tables(scored: pd.DataFrame, *, threshold: float = 0.65) -> tuple[pd.DataFrame, pd.DataFrame]:
    required = {"protein_a", "protein_b", "interaction_probability"}
    if not required.issubset(scored.columns):
        raise ValueError("Candidate scores require protein_a, protein_b and interaction_probability.")
    edges = scored[scored["interaction_probability"] >= float(threshold)].copy()
    if edges.empty:
        return edges, pd.DataFrame(columns=["protein", "degree", "mean_probability", "max_probability"])
    endpoint_rows = []
    for row in edges.itertuples(index=False):
        endpoint_rows.append({"protein": row.protein_a, "probability": row.interaction_probability})
        endpoint_rows.append({"protein": row.protein_b, "probability": row.interaction_probability})
    endpoints = pd.DataFrame(endpoint_rows)
    nodes = endpoints.groupby("protein", as_index=False).agg(
        degree=("probability", "size"),
        mean_probability=("probability", "mean"),
        max_probability=("probability", "max"),
    ).sort_values(["degree", "max_probability"], ascending=False)
    return edges.reset_index(drop=True), nodes.reset_index(drop=True)


def cold_start_validation(
    frame: pd.DataFrame,
    *,
    algorithm: str = "Random forest",
    held_out_protein_fraction: float = 0.25,
    random_state: int = 42,
    decision_threshold: float = 0.5,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Evaluate generalization when proteins, rather than pairs, define the holdout."""
    if not 0 < float(decision_threshold) < 1:
        raise ValueError("decision_threshold must be between 0 and 1.")
    cleaned = validate_pair_table(frame, require_label=True)
    matrix = build_feature_matrix(cleaned)
    proteins = sorted(set(cleaned["protein_a"]) | set(cleaned["protein_b"]))
    if len(proteins) < 12:
        raise ValueError("Protein-disjoint validation requires at least 12 unique proteins.")
    selected = None
    for offset in range(50):
        rng = np.random.default_rng(random_state + offset)
        holdout_count = max(2, int(round(len(proteins) * held_out_protein_fraction)))
        held_out = set(rng.choice(proteins, size=holdout_count, replace=False).tolist())
        train_mask = ~matrix["protein_a"].isin(held_out) & ~matrix["protein_b"].isin(held_out)
        test_mask = matrix["protein_a"].isin(held_out) | matrix["protein_b"].isin(held_out)
        train = matrix[train_mask]
        test = matrix[test_mask]
        if len(train) >= 20 and len(test) >= 10 and train["label"].nunique() == 2 and test["label"].nunique() == 2:
            selected = (held_out, train, test)
            break
    if selected is None:
        raise ValueError("Could not construct a class-balanced protein-disjoint split for this dataset.")
    held_out, train, test = selected
    model = _model_for_algorithm(algorithm, random_state)
    model.fit(train[list(FEATURE_COLUMNS)], train["label"].astype(int))
    probability = model.predict_proba(test[list(FEATURE_COLUMNS)])[:, 1]
    called = (probability >= float(decision_threshold)).astype(int)
    predictions = test[["pair_id", "protein_a", "protein_b", "label"]].copy()
    predictions["interaction_probability"] = probability
    predictions["predicted_label"] = called
    predictions["decision_threshold"] = float(decision_threshold)
    predictions["cold_start_type"] = np.where(
        predictions["protein_a"].isin(held_out) & predictions["protein_b"].isin(held_out),
        "cold_both",
        "cold_one",
    )
    metrics = pd.DataFrame(
        [
            {
                "validation_scheme": "protein_disjoint",
                "algorithm": algorithm,
                "training_pairs": len(train),
                "held_out_pairs": len(test),
                "held_out_proteins": len(held_out),
                "decision_threshold": float(decision_threshold),
                "roc_auc": float(roc_auc_score(test["label"], probability)),
                "balanced_accuracy": float(balanced_accuracy_score(test["label"], called)),
                "precision": float(precision_score(test["label"], called, zero_division=0)),
                "recall": float(recall_score(test["label"], called, zero_division=0)),
                "f1": float(f1_score(test["label"], called, zero_division=0)),
            }
        ]
    )
    return metrics, predictions.reset_index(drop=True)


def bootstrap_classification_metrics(
    predictions: pd.DataFrame,
    *,
    samples: int = 500,
    random_state: int = 42,
    decision_threshold: float | None = None,
) -> pd.DataFrame:
    required = {"label", "interaction_probability"}
    if not required.issubset(predictions.columns):
        raise ValueError("Predictions require label and interaction_probability columns.")
    truth = predictions["label"].astype(int).to_numpy()
    probability = predictions["interaction_probability"].astype(float).to_numpy()
    if decision_threshold is None:
        threshold_values = pd.to_numeric(predictions.get("decision_threshold"), errors="coerce") if "decision_threshold" in predictions else pd.Series(dtype=float)
        decision_threshold = float(threshold_values.dropna().iloc[0]) if not threshold_values.dropna().empty else 0.5
    if not 0 < float(decision_threshold) < 1:
        raise ValueError("decision_threshold must be between 0 and 1.")
    rng = np.random.default_rng(random_state)
    rows: dict[str, list[float]] = {name: [] for name in ("roc_auc", "balanced_accuracy", "f1", "precision", "recall")}
    for _ in range(max(int(samples), 100)):
        index = rng.integers(0, len(truth), size=len(truth))
        y = truth[index]
        p = probability[index]
        if len(np.unique(y)) < 2:
            continue
        called = (p >= float(decision_threshold)).astype(int)
        rows["roc_auc"].append(float(roc_auc_score(y, p)))
        rows["balanced_accuracy"].append(float(balanced_accuracy_score(y, called)))
        rows["f1"].append(float(f1_score(y, called, zero_division=0)))
        rows["precision"].append(float(precision_score(y, called, zero_division=0)))
        rows["recall"].append(float(recall_score(y, called, zero_division=0)))
    records = []
    for metric, values in rows.items():
        array = np.asarray(values, dtype=float)
        records.append(
            {
                "metric": metric,
                "bootstrap_estimate": float(np.mean(array)) if len(array) else np.nan,
                "ci_95_lower": float(np.quantile(array, 0.025)) if len(array) else np.nan,
                "ci_95_upper": float(np.quantile(array, 0.975)) if len(array) else np.nan,
                "valid_resamples": int(len(array)),
                "decision_threshold": float(decision_threshold),
            }
        )
    return pd.DataFrame(records)


def candidate_ood_report(training_frame: pd.DataFrame, candidate_frame: pd.DataFrame) -> pd.DataFrame:
    training = build_feature_matrix(validate_pair_table(training_frame, require_label=True))
    candidates = build_feature_matrix(validate_pair_table(candidate_frame, require_label=False))
    x_train = training[list(FEATURE_COLUMNS)].astype(float)
    x_candidate = candidates[list(FEATURE_COLUMNS)].astype(float)
    mean = x_train.mean(axis=0)
    scale = x_train.std(axis=0, ddof=0).replace(0, 1.0)
    train_z = ((x_train - mean) / scale).to_numpy()
    candidate_z = ((x_candidate - mean) / scale).to_numpy()
    records = []
    for index, vector in enumerate(candidate_z):
        distance = np.sqrt(((train_z - vector) ** 2).sum(axis=1))
        outside = sum(
            float(x_candidate.iloc[index][feature]) < float(x_train[feature].min())
            or float(x_candidate.iloc[index][feature]) > float(x_train[feature].max())
            for feature in FEATURE_COLUMNS
        )
        nearest = float(distance.min()) if len(distance) else np.nan
        records.append(
            {
                "pair_id": candidates.iloc[index]["pair_id"],
                "nearest_training_distance": nearest,
                "features_outside_training_range": int(outside),
                "ood_status": "high" if outside >= 3 or nearest >= 5 else "review" if outside >= 1 or nearest >= 3 else "in_domain",
            }
        )
    return pd.DataFrame(records)


def decision_curve_analysis(predictions: pd.DataFrame, *, thresholds: int = 37) -> pd.DataFrame:
    truth = predictions["label"].astype(int).to_numpy()
    probability = predictions["interaction_probability"].astype(float).to_numpy()
    prevalence = float(truth.mean())
    rows = []
    for threshold in np.linspace(0.05, 0.95, thresholds):
        called = probability >= threshold
        tp = int((called & (truth == 1)).sum())
        fp = int((called & (truth == 0)).sum())
        odds = threshold / max(1.0 - threshold, 1e-12)
        net_benefit = tp / len(truth) - fp / len(truth) * odds
        treat_all = prevalence - (1.0 - prevalence) * odds
        rows.append({"threshold": threshold, "model_net_benefit": net_benefit, "treat_all_net_benefit": treat_all, "treat_none_net_benefit": 0.0})
    return pd.DataFrame(rows)


def network_topology_summary(edges: pd.DataFrame, nodes: pd.DataFrame) -> pd.DataFrame:
    if nodes.empty:
        return pd.DataFrame([{"measure": "Nodes", "value": 0.0}])
    node_count = len(nodes)
    edge_count = len(edges)
    possible = node_count * (node_count - 1) / 2
    degree = nodes["degree"].astype(float)
    return pd.DataFrame(
        [
            {"measure": "Nodes", "value": float(node_count)},
            {"measure": "Edges", "value": float(edge_count)},
            {"measure": "Network density", "value": float(edge_count / possible) if possible else 0.0},
            {"measure": "Mean degree", "value": float(degree.mean())},
            {"measure": "Maximum degree", "value": float(degree.max())},
            {"measure": "Isolated nodes", "value": float((degree == 0).sum())},
        ]
    )
