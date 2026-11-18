from __future__ import annotations

import hashlib
import io
import json
import math
import random
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .base import (
    Missing,
    PermissionDenied,
    PlatformStore,
    ResearchPlatformError,
    canonical_json,
    new_id,
    now_utc,
)

TWIN_CLASSIFICATIONS = {
    "Educational Synthetic Twin",
    "Reference Population Twin",
    "Molecular Pathway Twin",
    "Disease-Mechanism Twin",
    "Pharmacology Learning Twin",
    "Patient-Derived Research Twin",
}
UNSUPPORTED_CLASSIFICATION = "Clinical-Grade Twin"
VALIDATION_CATEGORIES = {
    "Not Validated",
    "Internal Technical Validation",
    "Synthetic Benchmark Validation",
    "Literature Comparison",
    "Retrospective Research Validation",
    "Prospective Research Validation",
}
MODEL_TYPES = {
    "rule_based",
    "pathway_graph",
    "ordinary_differential_equation",
    "state_transition",
    "probabilistic",
    "agent_based_educational",
    "statistical_surrogate",
    "imported_definition",
}
VARIABLE_CLASSES = {
    "gene",
    "transcript",
    "protein",
    "metabolite",
    "pathway",
    "cell_type",
    "tissue",
    "organ",
    "phenotype",
    "environmental_exposure",
    "intervention",
}
INTEGRATION_TARGETS = {
    "shiro",
    "science_pulse",
    "virtual_science_lab",
    "classroom",
    "academy",
    "examination",
    "intelligence_hub",
    "research_compute",
    "studio",
    "portfolio",
    "research_projects",
    "scientific_discovery_agents",
}
IDENTITY_FIELDS = {
    "name",
    "full_name",
    "email",
    "phone",
    "address",
    "date_of_birth",
    "dob",
    "national_id",
    "medical_record_number",
    "mrn",
}

BUILTIN_MODELS: dict[str, dict[str, Any]] = {
    "glucose_regulation_v1": {
        "name": "Glucose regulation learning model",
        "domain": "glucose regulation and insulin resistance",
        "model_type": "ordinary_differential_equation",
        "variables": {"glucose": 110.0, "insulin": 10.0},
        "parameters": {
            "hepatic_input": 1.2,
            "uptake_rate": 0.012,
            "insulin_sensitivity": 1.0,
            "insulin_secretion": 0.35,
            "insulin_clearance": 0.08,
        },
        "units": {"glucose": "mg/dL", "insulin": "arbitrary learning units"},
        "uncertainty_fraction": 0.12,
        "assumptions": [
            "Two-state educational approximation",
            "No individual physiology or clinical calibration",
            "Parameters are synthetic reference values",
        ],
        "boundaries": ["Not diagnostic", "Not treatment guidance", "Not patient outcome prediction"],
    },
    "inflammation_response_v1": {
        "name": "Inflammation response learning model",
        "domain": "inflammation and immune response concepts",
        "model_type": "ordinary_differential_equation",
        "variables": {"mediator": 0.25, "regulation": 0.15, "tissue_stress": 0.10},
        "parameters": {
            "stimulus": 0.08,
            "mediator_decay": 0.12,
            "regulation_gain": 0.07,
            "stress_gain": 0.05,
            "repair_rate": 0.04,
        },
        "units": {
            "mediator": "normalized",
            "regulation": "normalized",
            "tissue_stress": "normalized",
        },
        "uncertainty_fraction": 0.18,
        "assumptions": ["Normalized states", "No cell-specific or clinical calibration"],
        "boundaries": ["Conceptual pathway dynamics only"],
    },
    "tumour_growth_concept_v1": {
        "name": "Tumour growth concept model",
        "domain": "tumour growth and immune interaction concepts",
        "model_type": "ordinary_differential_equation",
        "variables": {"tumour_burden": 0.08, "immune_pressure": 0.20},
        "parameters": {
            "growth_rate": 0.09,
            "carrying_capacity": 1.0,
            "immune_clearance": 0.035,
            "immune_activation": 0.04,
            "immune_decay": 0.03,
        },
        "units": {"tumour_burden": "normalized", "immune_pressure": "normalized"},
        "uncertainty_fraction": 0.25,
        "assumptions": ["Logistic conceptual growth", "Not a tumour-response predictor"],
        "boundaries": ["Educational/reference use only"],
    },
    "pharmacokinetic_concept_v1": {
        "name": "One-compartment pharmacokinetic learning model",
        "domain": "pharmacokinetic concepts",
        "model_type": "ordinary_differential_equation",
        "variables": {"concentration": 0.0},
        "parameters": {"elimination_rate": 0.12, "input_rate": 0.0},
        "units": {"concentration": "simulated concentration units"},
        "uncertainty_fraction": 0.20,
        "assumptions": ["One compartment", "Synthetic dose-like input"],
        "boundaries": ["Not dosing advice", "Not a prescription"],
    },
}


@dataclass(frozen=True)
class SimulationOutput:
    simulation_id: str
    trajectory: list[dict[str, float]]
    uncertainty: list[dict[str, float]]
    sensitivity: list[dict[str, float | str]]
    warnings: list[str]
    sha256: str


class DigitalTwinLab:
    def __init__(self, database: str | Path, storage_root: str | Path):
        self.store = PlatformStore(database)
        self.storage_root = Path(storage_root).resolve() / "phase33-digital-twin"
        self.storage_root.mkdir(parents=True, exist_ok=True)

    def _project(self, project_id: str) -> dict[str, Any]:
        row = self.store.one(
            "SELECT * FROM education_p33_twin_projects WHERE project_id=?",
            (project_id,),
        )
        if not row or row["state"] == "deleted":
            raise Missing("Digital Twin project not found.")
        return row

    def _audit(
        self,
        project_id: str,
        actor_id: str,
        action: str,
        object_type: str,
        object_id: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        with self.store.connection() as connection:
            connection.execute(
                """INSERT INTO education_p33_twin_audit VALUES(?,?,?,?,?,?,?,?)""",
                (
                    new_id("twinaudit"),
                    project_id,
                    actor_id,
                    action,
                    object_type,
                    object_id,
                    canonical_json(details or {}),
                    now_utc(),
                ),
            )

    def create_project(
        self,
        tenant_id: str,
        owner_id: str,
        institution_id: str,
        *,
        title: str,
        purpose: str,
        classification: str = "Educational Synthetic Twin",
        consent_status: str = "synthetic_not_applicable",
        deidentification_status: str = "synthetic",
        provenance: dict[str, Any] | None = None,
        ethics_record_reference: str = "",
        retention_until_utc: str | None = None,
    ) -> dict[str, Any]:
        if classification == UNSUPPORTED_CLASSIFICATION:
            raise PermissionDenied(
                "Clinical-Grade Twin is unsupported without formal clinical and regulatory validation."
            )
        if classification not in TWIN_CLASSIFICATIONS:
            raise ResearchPlatformError("Unsupported Digital Twin classification.")
        if classification == "Patient-Derived Research Twin" and consent_status not in {
            "documented_research_consent",
            "institutionally_governed_research",
        }:
            raise PermissionDenied("Patient-derived research requires documented consent governance.")
        if not title.strip() or not purpose.strip():
            raise ResearchPlatformError("Project title and purpose are required.")
        project_id = new_id("twin")
        timestamp = now_utc()
        with self.store.connection() as connection:
            connection.execute(
                """INSERT INTO education_p33_twin_projects
                (project_id,tenant_id,owner_id,institution_id,title,purpose,classification,
                 consent_status,deidentification_status,provenance_json,ethics_record_reference,
                 state,retention_until_utc,created_at_utc,updated_at_utc)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,? ,?,?,?)""",
                (
                    project_id,
                    tenant_id,
                    owner_id,
                    institution_id,
                    title[:300],
                    purpose[:5000],
                    classification,
                    consent_status[:120],
                    deidentification_status[:120],
                    canonical_json(provenance or {}),
                    ethics_record_reference[:1000],
                    "active",
                    retention_until_utc,
                    timestamp,
                    timestamp,
                ),
            )
            connection.execute(
                """INSERT INTO education_p33_twin_collaborators VALUES(?,?,?,?,?)""",
                (project_id, owner_id, "owner", timestamp, owner_id),
            )
        self._audit(project_id, owner_id, "project_created", "project", project_id)
        return self._project(project_id)

    def add_collaborator(
        self,
        project_id: str,
        actor_id: str,
        user_id: str,
        role: str,
    ) -> dict[str, Any]:
        project = self._project(project_id)
        if actor_id != project["owner_id"]:
            raise PermissionDenied("Only the project owner may manage collaborators.")
        if role not in {"viewer", "researcher", "educator", "reviewer"}:
            raise ResearchPlatformError("Unsupported collaborator role.")
        with self.store.connection() as connection:
            connection.execute(
                """INSERT INTO education_p33_twin_collaborators VALUES(?,?,?,?,?)
                ON CONFLICT(project_id,user_id) DO UPDATE SET
                 role=excluded.role,added_at_utc=excluded.added_at_utc,added_by=excluded.added_by""",
                (project_id, user_id, role, now_utc(), actor_id),
            )
        self._audit(project_id, actor_id, "collaborator_added", "user", user_id, {"role": role})
        return {"project_id": project_id, "user_id": user_id, "role": role}

    def ingest_observations(
        self,
        project_id: str,
        actor_id: str,
        *,
        source_type: str,
        source_label: str,
        source_reference: str,
        records: list[dict[str, Any]],
        provenance: dict[str, Any],
        schema_version: str = "1.0",
        deidentification_status: str = "synthetic",
        consent_status: str = "synthetic_not_applicable",
        synthetic: bool = False,
    ) -> dict[str, Any]:
        project = self._project(project_id)
        if not records:
            raise ResearchPlatformError("At least one observation is required.")
        for record in records:
            identity = IDENTITY_FIELDS.intersection(str(key).lower() for key in record)
            if identity:
                raise PermissionDenied(
                    "Direct identity fields are not accepted by Digital Twin ingestion."
                )
            required = {"variable_class", "variable_name", "observed_at_utc", "unit"}
            if not required.issubset(record):
                raise ResearchPlatformError("Observation schema is incomplete.")
            if record["variable_class"] not in VARIABLE_CLASSES:
                raise ResearchPlatformError("Unsupported biological variable class.")
            if "value" not in record and record.get("missing_status", "present") == "present":
                raise ResearchPlatformError("Present observations require a value.")
        content = canonical_json(records)
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        existing = self.store.one(
            """SELECT source_id FROM education_p33_twin_data_sources
            WHERE project_id=? AND content_sha256=?""",
            (project_id, digest),
        )
        if existing:
            return {"source_id": existing["source_id"], "duplicate": True, "records": 0}
        scores = [float(record.get("quality_score", 1.0)) for record in records]
        if any(score < 0 or score > 1 for score in scores):
            raise ResearchPlatformError("Quality score must be between zero and one.")
        source_id = new_id("twinsource")
        units = {str(row["variable_name"]): str(row["unit"]) for row in records}
        ranges = {
            str(row["variable_name"]): [row.get("reference_low"), row.get("reference_high")]
            for row in records
        }
        missing_count = sum(row.get("missing_status", "present") != "present" for row in records)
        timestamp = now_utc()
        with self.store.connection() as connection:
            connection.execute(
                """INSERT INTO education_p33_twin_data_sources
                (source_id,project_id,source_type,source_label,source_reference,provenance_json,
                 schema_version,units_json,reference_ranges_json,missing_data_status,
                 deidentification_status,consent_status,quality_score,content_sha256,synthetic,
                 created_at_utc,created_by)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    source_id,
                    project_id,
                    source_type[:100],
                    source_label[:300],
                    source_reference[:1000],
                    canonical_json(provenance),
                    schema_version[:80],
                    canonical_json(units),
                    canonical_json(ranges),
                    f"{missing_count}/{len(records)} missing",
                    deidentification_status[:120],
                    consent_status[:120],
                    sum(scores) / len(scores),
                    digest,
                    int(synthetic),
                    timestamp,
                    actor_id,
                ),
            )
            for record in records:
                value = record.get("value")
                numeric = float(value) if isinstance(value, (int, float)) else None
                text = None if numeric is not None or value is None else str(value)
                connection.execute(
                    """INSERT INTO education_p33_twin_observations
                    (observation_id,project_id,source_id,variable_class,variable_name,
                     observed_at_utc,value_numeric,value_text,unit,reference_low,reference_high,
                     missing_status,quality_score,provenance_json,synthetic,created_at_utc)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        new_id("observation"),
                        project_id,
                        source_id,
                        record["variable_class"],
                        str(record["variable_name"])[:200],
                        str(record["observed_at_utc"]),
                        numeric,
                        text,
                        str(record["unit"])[:80],
                        record.get("reference_low"),
                        record.get("reference_high"),
                        str(record.get("missing_status", "present"))[:80],
                        float(record.get("quality_score", 1.0)),
                        canonical_json(record.get("provenance", provenance)),
                        int(synthetic),
                        timestamp,
                    ),
                )
            connection.execute(
                "UPDATE education_p33_twin_projects SET updated_at_utc=? WHERE project_id=?",
                (timestamp, project_id),
            )
        self._audit(
            project_id,
            actor_id,
            "observations_ingested",
            "data_source",
            source_id,
            {"records": len(records), "synthetic": synthetic},
        )
        return {
            "source_id": source_id,
            "duplicate": False,
            "records": len(records),
            "sha256": digest,
            "synthetic": synthetic,
            "project_classification": project["classification"],
        }

    def generate_synthetic_profile(
        self,
        project_id: str,
        actor_id: str,
        *,
        seed: int,
        time_points: int = 12,
    ) -> dict[str, Any]:
        self._project(project_id)
        rng = random.Random(seed)
        records = []
        for index in range(max(3, min(time_points, 500))):
            glucose = 95.0 + 8.0 * math.sin(index / 2.0) + rng.gauss(0, 2.0)
            records.extend(
                [
                    {
                        "variable_class": "phenotype",
                        "variable_name": "synthetic_glucose",
                        "observed_at_utc": f"synthetic-t{index:04d}",
                        "value": round(glucose, 4),
                        "unit": "mg/dL",
                        "reference_low": 70,
                        "reference_high": 140,
                        "missing_status": "present",
                        "quality_score": 1.0,
                    },
                    {
                        "variable_class": "phenotype",
                        "variable_name": "synthetic_insulin",
                        "observed_at_utc": f"synthetic-t{index:04d}",
                        "value": round(8 + 0.2 * max(glucose - 90, 0) + rng.gauss(0, 0.5), 4),
                        "unit": "arbitrary learning units",
                        "missing_status": "present",
                        "quality_score": 1.0,
                    },
                ]
            )
        result = self.ingest_observations(
            project_id,
            actor_id,
            source_type="synthetic_generator",
            source_label="Explicit synthetic learning profile",
            source_reference="BioIntel deterministic synthetic generator",
            records=records,
            provenance={"seed": seed, "generator_version": "1.0.0"},
            synthetic=True,
        )
        generation_id = new_id("generation")
        with self.store.connection() as connection:
            connection.execute(
                """INSERT INTO education_p33_synthetic_generations
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    generation_id,
                    project_id,
                    seed,
                    "1.0.0",
                    canonical_json(["educational variability", "not a patient"]),
                    canonical_json({"noise": "Gaussian", "seasonality": "sine"}),
                    canonical_json({"time_points": time_points}),
                    len(records),
                    result["sha256"],
                    "SYNTHETIC DATA",
                    "NON-CLINICAL EDUCATION/RESEARCH SIMULATION",
                    now_utc(),
                    actor_id,
                ),
            )
        return {**result, "generation_id": generation_id, "seed": seed}

    def register_model(
        self,
        project_id: str,
        actor_id: str,
        *,
        model_key: str,
        model_name: str = "",
        model_type: str = "imported_definition",
        model_version: str = "1.0.0",
        definition: dict[str, Any] | None = None,
        assumptions: list[str] | None = None,
        boundaries: list[str] | None = None,
        parameter_sources: list[dict[str, Any]] | None = None,
        uncertainty: dict[str, Any] | None = None,
        evidence_references: list[str] | None = None,
    ) -> dict[str, Any]:
        self._project(project_id)
        builtin = BUILTIN_MODELS.get(model_key)
        if builtin:
            definition = builtin
            model_name = builtin["name"]
            model_type = builtin["model_type"]
            assumptions = list(builtin["assumptions"])
            boundaries = list(builtin["boundaries"])
            uncertainty = {"fraction": builtin["uncertainty_fraction"]}
        if model_type not in MODEL_TYPES:
            raise ResearchPlatformError("Unsupported Digital Twin model type.")
        if not definition:
            raise ResearchPlatformError("A model definition is required.")
        model_id = new_id("twinmodel")
        executable = int(model_key in BUILTIN_MODELS)
        with self.store.connection() as connection:
            connection.execute(
                """INSERT INTO education_p33_twin_models
                (model_id,project_id,model_key,model_name,model_type,model_version,
                 definition_json,assumptions_json,boundaries_json,parameter_sources_json,
                 uncertainty_json,evidence_references_json,validation_status,executable,
                 created_at_utc,created_by)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    model_id,
                    project_id,
                    model_key[:160],
                    (model_name or model_key)[:300],
                    model_type,
                    model_version[:80],
                    canonical_json(definition),
                    canonical_json(assumptions or []),
                    canonical_json(boundaries or []),
                    canonical_json(parameter_sources or []),
                    canonical_json(uncertainty or {}),
                    canonical_json(evidence_references or []),
                    "Not Validated",
                    executable,
                    now_utc(),
                    actor_id,
                ),
            )
        self._audit(
            project_id,
            actor_id,
            "model_registered",
            "model",
            model_id,
            {"executable": bool(executable), "validation": "Not Validated"},
        )
        return self.model(model_id)

    def model(self, model_id: str) -> dict[str, Any]:
        row = self.store.one(
            "SELECT * FROM education_p33_twin_models WHERE model_id=?",
            (model_id,),
        )
        if not row:
            raise Missing("Digital Twin model not found.")
        for field in (
            "definition_json",
            "assumptions_json",
            "boundaries_json",
            "parameter_sources_json",
            "uncertainty_json",
            "evidence_references_json",
        ):
            row[field.removesuffix("_json")] = json.loads(row.pop(field))
        return row

    def create_scenario(
        self,
        project_id: str,
        model_id: str,
        actor_id: str,
        *,
        name: str,
        baseline: dict[str, float] | None = None,
        time_steps: int = 48,
        step_size: float = 0.25,
        interventions: list[dict[str, Any]] | None = None,
        assumptions: list[str] | None = None,
        seed: int = 42,
        acknowledgement: bool = False,
    ) -> dict[str, Any]:
        project = self._project(project_id)
        model = self.model(model_id)
        if model["project_id"] != project_id:
            raise PermissionDenied("Model belongs to a different Digital Twin project.")
        if not 2 <= time_steps <= 20_000 or not 0 < step_size <= 100:
            raise ResearchPlatformError("Temporal simulation bounds are invalid.")
        if project["classification"] == "Patient-Derived Research Twin" and not acknowledgement:
            raise PermissionDenied(
                "Patient-derived research simulation requires explicit non-clinical acknowledgement."
            )
        scenario_id = new_id("scenario")
        with self.store.connection() as connection:
            connection.execute(
                """INSERT INTO education_p33_twin_scenarios
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    scenario_id,
                    project_id,
                    model_id,
                    name[:300],
                    model["definition"].get("domain", "research simulation"),
                    canonical_json(baseline or {}),
                    time_steps,
                    step_size,
                    canonical_json(interventions or []),
                    canonical_json(assumptions or []),
                    seed,
                    int(acknowledgement),
                    now_utc(),
                    actor_id,
                ),
            )
        self._audit(project_id, actor_id, "scenario_created", "scenario", scenario_id)
        return self.store.one(
            "SELECT * FROM education_p33_twin_scenarios WHERE scenario_id=?",
            (scenario_id,),
        ) or {}

    @staticmethod
    def _derivatives(
        model_key: str,
        state: dict[str, float],
        parameters: dict[str, float],
    ) -> dict[str, float]:
        if model_key == "glucose_regulation_v1":
            return {
                "glucose": parameters["hepatic_input"]
                - parameters["uptake_rate"]
                * parameters["insulin_sensitivity"]
                * state["insulin"]
                * state["glucose"]
                / 100.0,
                "insulin": parameters["insulin_secretion"]
                * max(state["glucose"] - 90.0, 0.0)
                / 100.0
                - parameters["insulin_clearance"] * state["insulin"],
            }
        if model_key == "inflammation_response_v1":
            return {
                "mediator": parameters["stimulus"]
                - parameters["mediator_decay"] * state["mediator"]
                - parameters["regulation_gain"] * state["regulation"],
                "regulation": parameters["regulation_gain"] * state["mediator"]
                - 0.05 * state["regulation"],
                "tissue_stress": parameters["stress_gain"] * state["mediator"]
                - parameters["repair_rate"] * state["tissue_stress"],
            }
        if model_key == "tumour_growth_concept_v1":
            return {
                "tumour_burden": parameters["growth_rate"]
                * state["tumour_burden"]
                * (1 - state["tumour_burden"] / parameters["carrying_capacity"])
                - parameters["immune_clearance"]
                * state["immune_pressure"]
                * state["tumour_burden"],
                "immune_pressure": parameters["immune_activation"] * state["tumour_burden"]
                - parameters["immune_decay"] * state["immune_pressure"],
            }
        if model_key == "pharmacokinetic_concept_v1":
            return {
                "concentration": parameters["input_rate"]
                - parameters["elimination_rate"] * state["concentration"]
            }
        raise PermissionDenied("Imported model definitions are stored but not executable.")

    @classmethod
    def _simulate(
        cls,
        model_key: str,
        baseline: dict[str, float],
        parameters: dict[str, float],
        interventions: list[dict[str, Any]],
        time_steps: int,
        step_size: float,
    ) -> list[dict[str, float]]:
        state = {key: float(value) for key, value in baseline.items()}
        params = {key: float(value) for key, value in parameters.items()}
        trajectory: list[dict[str, float]] = []
        for index in range(time_steps + 1):
            current_time = round(index * step_size, 8)
            for intervention in interventions:
                if abs(float(intervention.get("time", -1)) - current_time) > step_size / 2:
                    continue
                target = str(intervention.get("target", ""))
                mode = intervention.get("mode", "set")
                value = float(intervention.get("value", 0))
                destination = params if target in params else state
                if target not in destination:
                    raise ResearchPlatformError(f"Intervention target is unknown: {target}")
                if mode == "set":
                    destination[target] = value
                elif mode == "add":
                    destination[target] += value
                elif mode == "multiply":
                    destination[target] *= value
                else:
                    raise ResearchPlatformError("Unsupported intervention mode.")
            trajectory.append({"time": current_time, **{key: round(value, 10) for key, value in state.items()}})
            if index == time_steps:
                break
            derivatives = cls._derivatives(model_key, state, params)
            state = {
                key: max(0.0, state[key] + step_size * derivatives[key])
                for key in state
            }
        return trajectory

    def run_scenario(
        self,
        scenario_id: str,
        actor_id: str,
        *,
        replay_of: str | None = None,
    ) -> SimulationOutput:
        scenario = self.store.one(
            "SELECT * FROM education_p33_twin_scenarios WHERE scenario_id=?",
            (scenario_id,),
        )
        if not scenario:
            raise Missing("Digital Twin scenario not found.")
        project = self._project(scenario["project_id"])
        if project["classification"] == "Patient-Derived Research Twin" and not scenario[
            "acknowledgement"
        ]:
            raise PermissionDenied("Non-clinical acknowledgement is required.")
        model = self.model(scenario["model_id"])
        if not model["executable"]:
            raise PermissionDenied(
                "Imported model definition is stored but cannot execute without an approved adapter."
            )
        definition = model["definition"]
        baseline = dict(definition["variables"])
        baseline.update(json.loads(scenario["baseline_json"]))
        parameters = dict(definition["parameters"])
        interventions = json.loads(scenario["interventions_json"])
        trajectory = self._simulate(
            model["model_key"],
            baseline,
            parameters,
            interventions,
            int(scenario["time_steps"]),
            float(scenario["step_size"]),
        )
        fraction = float(model["uncertainty"].get("fraction", 0.2))
        primary = next(iter(baseline))
        uncertainty = [
            {
                "time": row["time"],
                "variable": primary,
                "lower": round(max(0.0, row[primary] * (1 - fraction)), 10),
                "upper": round(row[primary] * (1 + fraction), 10),
            }
            for row in trajectory
        ]
        baseline_final = trajectory[-1][primary]
        sensitivity: list[dict[str, float | str]] = []
        for name, value in parameters.items():
            varied = {**parameters, name: value * 1.10 if value != 0 else 0.10}
            varied_final = self._simulate(
                model["model_key"],
                baseline,
                varied,
                interventions,
                int(scenario["time_steps"]),
                float(scenario["step_size"]),
            )[-1][primary]
            sensitivity.append(
                {
                    "parameter": name,
                    "relative_change": 0.10,
                    "final_output_change": round(varied_final - baseline_final, 10),
                }
            )
        warnings = [
            "RESEARCH/EDUCATION SIMULATION ONLY",
            "NOT MEDICAL ADVICE OR A PRESCRIPTION",
            "NOT A GUARANTEED OUTCOME",
            "OUTPUT DEPENDS ON MODEL ASSUMPTIONS AND SYNTHETIC/REFERENCE PARAMETERS",
        ]
        payload = {
            "trajectory": trajectory,
            "uncertainty": uncertainty,
            "sensitivity": sensitivity,
            "model_version": model["model_version"],
            "seed": scenario["seed"],
        }
        digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
        simulation_id = new_id("simulation")
        with self.store.connection() as connection:
            connection.execute(
                """INSERT INTO education_p33_twin_simulations
                (simulation_id,scenario_id,project_id,model_id,model_version,parameter_version,
                 seed,status,trajectory_json,uncertainty_json,sensitivity_json,output_sha256,
                 warnings_json,replay_of,created_at_utc,created_by)
                VALUES(?,?,?,?,?,?,?,'completed',?,?,?,?,?,?,?,?)""",
                (
                    simulation_id,
                    scenario_id,
                    scenario["project_id"],
                    scenario["model_id"],
                    model["model_version"],
                    project["parameter_version"],
                    scenario["seed"],
                    canonical_json(trajectory),
                    canonical_json(uncertainty),
                    canonical_json(sensitivity),
                    digest,
                    canonical_json(warnings),
                    replay_of,
                    now_utc(),
                    actor_id,
                ),
            )
        self._audit(
            scenario["project_id"],
            actor_id,
            "simulation_completed",
            "simulation",
            simulation_id,
            {"sha256": digest},
        )
        return SimulationOutput(
            simulation_id=simulation_id,
            trajectory=trajectory,
            uncertainty=uncertainty,
            sensitivity=sensitivity,
            warnings=warnings,
            sha256=digest,
        )

    def compare_simulations(self, simulation_ids: list[str]) -> dict[str, Any]:
        if len(simulation_ids) < 2 or len(simulation_ids) > 20:
            raise ResearchPlatformError("Compare between two and twenty simulations.")
        rows = []
        for simulation_id in simulation_ids:
            row = self.store.one(
                "SELECT * FROM education_p33_twin_simulations WHERE simulation_id=?",
                (simulation_id,),
            )
            if not row:
                raise Missing(f"Simulation not found: {simulation_id}")
            trajectory = json.loads(row["trajectory_json"])
            variables = [key for key in trajectory[-1] if key != "time"]
            rows.append(
                {
                    "simulation_id": simulation_id,
                    "model_version": row["model_version"],
                    "final_state": {key: trajectory[-1][key] for key in variables},
                    "sha256": row["output_sha256"],
                }
            )
        return {"simulations": rows, "computed": True}

    def record_validation(
        self,
        model_id: str,
        reviewer_id: str,
        *,
        category: str,
        benchmark_reference: str,
        expected_output: dict[str, Any],
        observed_output: dict[str, Any],
        calibration: dict[str, Any],
        sensitivity: dict[str, Any],
        uncertainty: dict[str, Any],
        reproducibility_seed: int,
        limitations: str,
        approved: bool,
    ) -> dict[str, Any]:
        model = self.model(model_id)
        if category == "Clinical Validation":
            raise PermissionDenied(
                "Clinical Validation cannot be selected in this release; formal evidence review is unavailable."
            )
        if category not in VALIDATION_CATEGORIES:
            raise ResearchPlatformError("Unsupported validation category.")
        evidence = {
            "benchmark_reference": benchmark_reference,
            "expected": expected_output,
            "observed": observed_output,
            "calibration": calibration,
            "sensitivity": sensitivity,
            "uncertainty": uncertainty,
            "seed": reproducibility_seed,
            "limitations": limitations,
        }
        digest = hashlib.sha256(canonical_json(evidence).encode("utf-8")).hexdigest()
        validation_id = new_id("validation")
        with self.store.connection() as connection:
            connection.execute(
                """INSERT INTO education_p33_twin_validations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    validation_id,
                    model_id,
                    category,
                    benchmark_reference[:1000],
                    canonical_json(expected_output),
                    canonical_json(observed_output),
                    canonical_json(calibration),
                    canonical_json(sensitivity),
                    canonical_json(uncertainty),
                    reproducibility_seed,
                    limitations[:10000],
                    digest,
                    reviewer_id,
                    int(approved),
                    now_utc(),
                ),
            )
            if approved:
                connection.execute(
                    """UPDATE education_p33_twin_models SET validation_status=?
                    WHERE model_id=?""",
                    (category, model_id),
                )
                connection.execute(
                    """UPDATE education_p33_twin_projects SET validation_status=?,
                    updated_at_utc=? WHERE project_id=?""",
                    (category, now_utc(), model["project_id"]),
                )
        self._audit(
            model["project_id"],
            reviewer_id,
            "validation_recorded",
            "validation",
            validation_id,
            {"category": category, "approved": approved},
        )
        return {
            "validation_id": validation_id,
            "category": category,
            "approved": approved,
            "evidence_sha256": digest,
        }

    def link_integration(
        self,
        project_id: str,
        actor_id: str,
        *,
        target_module: str,
        target_object_id: str,
        purpose: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        self._project(project_id)
        if target_module not in INTEGRATION_TARGETS:
            raise ResearchPlatformError("Unsupported Digital Twin integration target.")
        integration_id = new_id("twinlink")
        digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
        with self.store.connection() as connection:
            connection.execute(
                """INSERT INTO education_p33_twin_integrations VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    integration_id,
                    project_id,
                    target_module,
                    target_object_id[:200],
                    purpose[:2000],
                    digest,
                    "review_required",
                    now_utc(),
                    actor_id,
                ),
            )
        return {
            "integration_id": integration_id,
            "target_module": target_module,
            "state": "review_required",
            "payload_sha256": digest,
        }

    def shiro_model_explanation(self, model_id: str) -> dict[str, Any]:
        model = self.model(model_id)
        definition = model["definition"]
        return {
            "model_id": model_id,
            "explanation_source": "stored model definition",
            "purpose": f"Explain the stored {model['model_name']} learning model.",
            "model_type": model["model_type"],
            "variables": definition.get("state", []),
            "parameters": sorted(definition.get("parameters", {})),
            "assumptions": model["assumptions"],
            "boundaries": model["boundaries"],
            "uncertainty": (
                "Simulation uncertainty reflects parameter assumptions, not clinical confidence."
            ),
            "non_clinical": True,
            "external_ai_called": False,
        }

    def create_learning_activity(
        self,
        project_id: str,
        simulation_id: str,
        teacher_id: str,
        *,
        classroom_reference: str,
        interpretation_prompt: str,
    ) -> dict[str, Any]:
        self._project(project_id)
        simulation = self.store.one(
            """SELECT simulation_id FROM education_p33_twin_simulations
            WHERE simulation_id=? AND project_id=? AND status='completed'""",
            (simulation_id, project_id),
        )
        if not simulation:
            raise Missing("Completed simulation not found in this Digital Twin project.")
        if not interpretation_prompt.strip():
            raise ResearchPlatformError("Interpretation prompt is required.")
        activity_id = new_id("twinactivity")
        with self.store.connection() as connection:
            connection.execute(
                """INSERT INTO education_p33_twin_learning_activities
                VALUES(?,?,?,?,?,?,?,?)""",
                (
                    activity_id,
                    project_id,
                    simulation_id,
                    classroom_reference[:200],
                    teacher_id,
                    interpretation_prompt[:10_000],
                    "open",
                    now_utc(),
                ),
            )
        self._audit(
            project_id,
            teacher_id,
            "learning_activity_created",
            "learning_activity",
            activity_id,
        )
        return self.store.one(
            """SELECT * FROM education_p33_twin_learning_activities
            WHERE activity_id=?""",
            (activity_id,),
        ) or {}

    def submit_interpretation(
        self,
        activity_id: str,
        student_id: str,
        *,
        interpretation_text: str,
    ) -> dict[str, Any]:
        activity = self.store.one(
            """SELECT * FROM education_p33_twin_learning_activities
            WHERE activity_id=? AND state='open'""",
            (activity_id,),
        )
        if not activity:
            raise Missing("Open Digital Twin learning activity not found.")
        if len(interpretation_text.strip()) < 20:
            raise ResearchPlatformError("Interpretation must contain at least 20 characters.")
        submission_id = new_id("twininterpretation")
        digest = hashlib.sha256(interpretation_text.encode("utf-8")).hexdigest()
        with self.store.connection() as connection:
            connection.execute(
                """INSERT INTO education_p33_twin_learning_submissions
                VALUES(?,?,?,?,?,'submitted',NULL,'',0,'{}',?,NULL,NULL)""",
                (
                    submission_id,
                    activity_id,
                    student_id,
                    interpretation_text[:50_000],
                    digest,
                    now_utc(),
                ),
            )
        return self.store.one(
            """SELECT * FROM education_p33_twin_learning_submissions
            WHERE submission_id=?""",
            (submission_id,),
        ) or {}

    def review_interpretation(
        self,
        submission_id: str,
        teacher_id: str,
        *,
        score: float,
        feedback: str,
        revision_requested: bool = False,
    ) -> dict[str, Any]:
        submission = self.store.one(
            """SELECT s.*,a.project_id,a.teacher_id,a.simulation_id
            FROM education_p33_twin_learning_submissions s
            JOIN education_p33_twin_learning_activities a ON a.activity_id=s.activity_id
            WHERE s.submission_id=?""",
            (submission_id,),
        )
        if not submission:
            raise Missing("Digital Twin interpretation submission not found.")
        if submission["teacher_id"] != teacher_id:
            raise PermissionDenied("Only the assigned teacher may review this interpretation.")
        if not 0 <= score <= 100:
            raise ResearchPlatformError("Interpretation score must be between 0 and 100.")
        mastery_delta = max(-0.05, min(0.05, (score - 50.0) / 1000.0))
        portfolio = {
            "artifact_type": "digital_twin_interpretation",
            "simulation_id": submission["simulation_id"],
            "interpretation_sha256": submission["interpretation_sha256"],
            "score": score,
            "mastery_delta": mastery_delta,
            "reviewed_by": teacher_id,
            "non_clinical": True,
        }
        with self.store.connection() as connection:
            connection.execute(
                """UPDATE education_p33_twin_learning_submissions
                SET state=?,score=?,feedback=?,mastery_delta=?,
                portfolio_record_json=?,reviewed_at_utc=?,reviewed_by=?
                WHERE submission_id=?""",
                (
                    "revision_requested" if revision_requested else "reviewed",
                    score,
                    feedback[:10_000],
                    mastery_delta,
                    canonical_json(portfolio),
                    now_utc(),
                    teacher_id,
                    submission_id,
                ),
            )
        self._audit(
            submission["project_id"],
            teacher_id,
            "learning_interpretation_reviewed",
            "submission",
            submission_id,
            {"score": score, "mastery_delta": mastery_delta},
        )
        return self.store.one(
            """SELECT * FROM education_p33_twin_learning_submissions
            WHERE submission_id=?""",
            (submission_id,),
        ) or {}

    def export_result_bundle(self, simulation_id: str) -> bytes:
        simulation = self.store.one(
            "SELECT * FROM education_p33_twin_simulations WHERE simulation_id=?",
            (simulation_id,),
        )
        if not simulation:
            raise Missing("Simulation not found.")
        project = self._project(simulation["project_id"])
        model = self.model(simulation["model_id"])
        manifest = {
            "schema": "biointel.phase33.digital-twin-result.v1",
            "simulation_id": simulation_id,
            "classification": project["classification"],
            "validation_status": model["validation_status"],
            "output_sha256": simulation["output_sha256"],
            "watermark": "RESEARCH/EDUCATION SIMULATION — NON-CLINICAL",
            "limitations": model["boundaries"],
        }
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", json.dumps(manifest, indent=2))
            archive.writestr("trajectory.json", simulation["trajectory_json"])
            archive.writestr("uncertainty.json", simulation["uncertainty_json"])
            archive.writestr("sensitivity.json", simulation["sensitivity_json"])
            archive.writestr(
                "LIMITATIONS.txt",
                "\n".join(
                    [
                        "RESEARCH/EDUCATION SIMULATION — NON-CLINICAL",
                        "Not medical advice, a prescription, or a guaranteed outcome.",
                        *model["boundaries"],
                    ]
                ),
            )
        return stream.getvalue()

    def archive_or_delete_project(
        self,
        project_id: str,
        actor_id: str,
        *,
        delete: bool = False,
    ) -> dict[str, Any]:
        project = self._project(project_id)
        if actor_id != project["owner_id"]:
            raise PermissionDenied("Only the project owner may archive or delete the project.")
        state = "deleted" if delete else "archived"
        with self.store.connection() as connection:
            connection.execute(
                "UPDATE education_p33_twin_projects SET state=?,updated_at_utc=? WHERE project_id=?",
                (state, now_utc(), project_id),
            )
        self._audit(project_id, actor_id, f"project_{state}", "project", project_id)
        return {"project_id": project_id, "state": state}
