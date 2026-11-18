from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Mapping

from .constants import DATA_ORIGINS, PROJECT_STAGES, ROLE_PERMISSIONS, ROLES


class PlatformValidationError(ValueError):
    """A user-correctable platform validation failure."""


class PlatformConflictError(RuntimeError):
    """An operation conflicts with persisted lifecycle state."""


class PlatformPermissionError(PermissionError):
    """The current role cannot perform the requested action."""


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9]", "", prefix).upper()[:12] or "ITEM"
    return f"{clean}-{uuid.uuid4().hex[:16].upper()}"


def require_text(value: object, field_name: str, maximum: int = 4000) -> str:
    text = str(value or "").strip()
    if not text:
        raise PlatformValidationError(f"{field_name} is required")
    if len(text) > maximum:
        raise PlatformValidationError(f"{field_name} must be at most {maximum} characters")
    return text


def optional_text(value: object, maximum: int = 10000) -> str:
    return str(value or "").strip()[:maximum]


def validate_choice(value: str, choices: tuple[str, ...], field_name: str) -> str:
    if value not in choices:
        raise PlatformValidationError(f"Unsupported {field_name}: {value}")
    return value


def validate_date(value: str | None) -> str | None:
    if not value:
        return None
    return date.fromisoformat(str(value)).isoformat()


def validate_origin(value: str) -> str:
    return validate_choice(value, DATA_ORIGINS, "data origin")


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))


def payload_sha256(value: object) -> str:
    raw = value if isinstance(value, bytes) else canonical_json(value).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def check_permission(role: str, permission: str) -> None:
    validate_choice(role, ROLES, "role")
    allowed = ROLE_PERMISSIONS[role]
    if "*" not in allowed and permission not in allowed:
        raise PlatformPermissionError(f"Role {role} does not permit {permission}")


def safe_artifact_path(root: str | Path, *parts: str) -> Path:
    base = Path(root).resolve()
    candidate = base.joinpath(*(Path(part).name for part in parts)).resolve()
    if not candidate.is_relative_to(base):
        raise PlatformValidationError("Artifact path escaped the configured storage root")
    return candidate


@dataclass(frozen=True)
class ProvenanceRecord:
    origin: str
    source: str
    created_at_utc: str = field(default_factory=utc_now)
    software_version: str = ""
    generator_version: str = ""
    random_seed: int | None = None
    parent_ids: tuple[str, ...] = ()
    input_hashes: Mapping[str, str] = field(default_factory=dict)
    parameters: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        validate_origin(self.origin)
        require_text(self.source, "provenance source", 500)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProjectCreate:
    title: str
    research_question: str
    scientific_objective: str
    disease_context: str = ""
    organism: str = ""
    assay_types: tuple[str, ...] = ()
    principal_investigator: str = ""
    owner: str = "local_user"
    contributors: tuple[str, ...] = ()
    reviewers: tuple[str, ...] = ()
    start_date: str | None = None
    target_date: str | None = None
    current_stage: str = PROJECT_STAGES[0]
    data_origin: str = "user_entered_interpretation"
    is_synthetic: bool = False

    def normalized(self) -> "ProjectCreate":
        validate_choice(self.current_stage, PROJECT_STAGES, "project stage")
        validate_origin(self.data_origin)
        if self.is_synthetic and self.data_origin != "synthetic_demo_output":
            raise PlatformValidationError(
                "Synthetic projects must preserve synthetic_demo_output origin"
            )
        return ProjectCreate(
            title=require_text(self.title, "project title", 240),
            research_question=require_text(self.research_question, "research question", 4000),
            scientific_objective=require_text(
                self.scientific_objective, "scientific objective", 4000
            ),
            disease_context=optional_text(self.disease_context, 1000),
            organism=optional_text(self.organism, 200),
            assay_types=tuple(
                dict.fromkeys(
                    optional_text(value, 120)
                    for value in self.assay_types
                    if str(value).strip()
                )
            ),
            principal_investigator=optional_text(self.principal_investigator, 240),
            owner=optional_text(self.owner, 240) or "local_user",
            contributors=tuple(
                dict.fromkeys(
                    optional_text(value, 240)
                    for value in self.contributors
                    if str(value).strip()
                )
            ),
            reviewers=tuple(
                dict.fromkeys(
                    optional_text(value, 240)
                    for value in self.reviewers
                    if str(value).strip()
                )
            ),
            start_date=validate_date(self.start_date),
            target_date=validate_date(self.target_date),
            current_stage=self.current_stage,
            data_origin=self.data_origin,
            is_synthetic=bool(self.is_synthetic),
        )
