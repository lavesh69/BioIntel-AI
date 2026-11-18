from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Callable

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class EndpointModelCard:
    model_id: str
    endpoint: str
    version: str
    artifact_sha256: str
    training_dataset_sha256: str
    licence: str
    endpoint_definition: str
    units: str
    split_strategies: list[str]
    metrics: dict[str, float]
    calibration: dict[str, Any]
    applicability_domain: dict[str, Any]
    independent_validation: dict[str, Any]
    intended_use: str
    limitations: list[str]


@dataclass(frozen=True)
class EndpointQualification:
    eligible: bool
    status: str
    blockers: list[str]
    warnings: list[str]
    required_controls: list[str]
    card: dict[str, object]


def qualify_endpoint_model(card: EndpointModelCard) -> EndpointQualification:
    blockers: list[str] = []
    warnings: list[str] = []
    if not card.model_id.strip() or not card.endpoint.strip() or not card.version.strip():
        blockers.append("Model ID, endpoint and version are required.")
    if not SHA256_RE.fullmatch(card.artifact_sha256.lower()):
        blockers.append("A valid model artifact SHA-256 is required.")
    if not SHA256_RE.fullmatch(card.training_dataset_sha256.lower()):
        blockers.append("A valid training-dataset SHA-256 is required.")
    if not card.licence.strip():
        blockers.append("Model and dataset licence must be documented.")
    split_names = {value.lower().replace("-", "_") for value in card.split_strategies}
    if not split_names & {"scaffold", "temporal", "external", "cold_drug", "cold_target"}:
        blockers.append("At least one leakage-resistant split is required.")
    if not card.independent_validation:
        blockers.append("Independent validation evidence is required.")
    if not card.applicability_domain:
        blockers.append("Applicability-domain definition is required.")
    if not card.metrics:
        blockers.append("Validation metrics are required.")
    if not card.calibration:
        warnings.append("No calibration assessment is documented.")
    if not card.limitations:
        warnings.append("Model limitations should be documented explicitly.")
    eligible = not blockers
    return EndpointQualification(
        eligible=eligible,
        status="qualified" if eligible else "blocked",
        blockers=blockers,
        warnings=warnings,
        required_controls=[
            "Schema and unit validation",
            "Model artifact checksum verification",
            "Applicability-domain check for every molecule",
            "Uncertainty/confidence output",
            "Versioned model card in every export",
            "Independent benchmark and drift monitoring",
        ],
        card=asdict(card),
    )


class EndpointPluginRegistry:
    """In-process endpoint-plugin registry with mandatory qualification metadata."""

    def __init__(self) -> None:
        self._plugins: dict[str, tuple[EndpointModelCard, Callable[[str], dict[str, Any]]]] = {}

    def register(
        self,
        card: EndpointModelCard,
        predictor: Callable[[str], dict[str, Any]],
    ) -> EndpointQualification:
        qualification = qualify_endpoint_model(card)
        if not qualification.eligible:
            raise ValueError("Endpoint model is not qualified: " + "; ".join(qualification.blockers))
        self._plugins[card.endpoint] = (card, predictor)
        return qualification

    def predict(self, endpoint: str, smiles: str) -> dict[str, Any]:
        if endpoint not in self._plugins:
            return {
                "endpoint": endpoint,
                "status": "not assessed",
                "value": None,
                "basis": "No qualified endpoint plugin is registered",
            }
        card, predictor = self._plugins[endpoint]
        result = dict(predictor(smiles))
        result.update(
            {
                "endpoint": endpoint,
                "status": "model",
                "model_id": card.model_id,
                "model_version": card.version,
                "artifact_sha256": card.artifact_sha256,
                "training_dataset_sha256": card.training_dataset_sha256,
            }
        )
        return result

    def endpoints(self) -> list[str]:
        return sorted(self._plugins)


ENDPOINT_PLUGINS = EndpointPluginRegistry()
