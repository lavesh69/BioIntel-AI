from __future__ import annotations

import importlib.util
from dataclasses import dataclass


@dataclass(frozen=True)
class OptionalCapability:
    key: str
    title: str
    available: bool
    required_packages: tuple[str, ...]
    purpose: str


def optional_capabilities() -> tuple[OptionalCapability, ...]:
    definitions = (
        (
            "optuna",
            "Automated hyperparameter optimization",
            ("optuna",),
            "Optuna search and pruning",
        ),
        (
            "onnx",
            "ONNX optimized inference",
            ("onnxruntime", "skl2onnx"),
            "Portable accelerated inference",
        ),
        ("gnn", "Graph neural networks", ("torch", "torch_geometric"), "Molecular graph encoders"),
        (
            "protein_lm",
            "Protein language models",
            ("torch", "transformers"),
            "ESM/ProtT5 embeddings",
        ),
        ("shap", "SHAP explanations", ("shap",), "Model-aware local explanations"),
        (
            "parquet",
            "Parquet/Arrow checkpoints",
            ("pyarrow",),
            "Columnar checkpoint and dataset I/O",
        ),
        (
            "postgres",
            "PostgreSQL production backend",
            ("sqlalchemy", "psycopg"),
            "Concurrent multi-user database",
        ),
    )
    return tuple(
        OptionalCapability(
            key=key,
            title=title,
            available=all(importlib.util.find_spec(package) is not None for package in packages),
            required_packages=packages,
            purpose=purpose,
        )
        for key, title, packages, purpose in definitions
    )
