from __future__ import annotations

from biointel.tools.runtime import tool_available
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class DockingReadiness:
    engines: dict[str, bool]
    preparation_tools: dict[str, bool]
    ready_for_execution: bool
    qualification_required: bool
    recommendations: list[str]


@dataclass(frozen=True)
class DockingQualification:
    status: str
    qualified: bool
    redocking_rmsd_angstrom: float | None
    enrichment_factor_1_percent: float | None
    blockers: list[str]
    warnings: list[str]
    locked_protocol: dict[str, object]


def external_docking_readiness() -> DockingReadiness:
    engines = {name: tool_available(name) for name in ("vina", "smina", "gnina")}
    preparation = {name: tool_available(name) for name in ("obabel", "prepare_receptor", "prepare_ligand", "fpocket")}
    ready = any(engines.values()) and any(preparation.values())
    recommendations = []
    if not any(engines.values()):
        recommendations.append("Install and version-lock a docking engine such as AutoDock Vina, smina or GNINA.")
    if not any(preparation.values()):
        recommendations.append("Install receptor/ligand preparation and pocket-definition tooling.")
    recommendations.extend(
        [
            "Qualify the protocol by redocking a reference ligand.",
            "Require pose review and decoy enrichment before screening claims.",
            "Record receptor, ligand, grid and engine checksums in every run.",
        ]
    )
    return DockingReadiness(engines, preparation, ready, True, recommendations)


def evaluate_docking_qualification(
    *,
    receptor_prepared: bool,
    ligand_prepared: bool,
    grid_defined: bool,
    reference_ligand_available: bool,
    redocking_rmsd_angstrom: float | None,
    enrichment_factor_1_percent: float | None,
    pose_review_completed: bool,
    protocol: dict[str, object] | None = None,
) -> DockingQualification:
    blockers: list[str] = []
    warnings: list[str] = []
    for passed, label in [
        (receptor_prepared, "Receptor preparation not documented"),
        (ligand_prepared, "Ligand preparation not documented"),
        (grid_defined, "Docking grid/pocket not defined"),
        (reference_ligand_available, "Reference ligand unavailable"),
        (pose_review_completed, "Expert pose review incomplete"),
    ]:
        if not passed:
            blockers.append(label)
    if redocking_rmsd_angstrom is None:
        blockers.append("Redocking RMSD not provided")
    elif redocking_rmsd_angstrom > 2.0:
        blockers.append("Redocking RMSD exceeds the 2.0 Å acceptance threshold")
    if enrichment_factor_1_percent is None:
        warnings.append("Decoy enrichment was not assessed.")
    elif enrichment_factor_1_percent < 2.0:
        blockers.append("Top-1% enrichment factor is below 2.0")
    qualified = not blockers
    return DockingQualification(
        status="qualified" if qualified else "blocked",
        qualified=qualified,
        redocking_rmsd_angstrom=redocking_rmsd_angstrom,
        enrichment_factor_1_percent=enrichment_factor_1_percent,
        blockers=blockers,
        warnings=warnings,
        locked_protocol=protocol or {},
    )


def readiness_dict(result: DockingReadiness | DockingQualification) -> dict[str, object]:
    return asdict(result)
