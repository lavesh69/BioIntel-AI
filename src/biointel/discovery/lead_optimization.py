from __future__ import annotations

from dataclasses import asdict, dataclass

from rdkit import Chem

from biointel.chemistry.standardization import standardize_molecule


@dataclass(frozen=True)
class SynthesisFeasibility:
    score: int
    tier: str
    molecular_complexity_flags: list[str]
    process_flags: list[str]
    recommendations: list[str]
    methodology: dict[str, object]


@dataclass(frozen=True)
class PatentEvidenceAssessment:
    status: str
    complete: bool
    missing_evidence: list[str]
    warnings: list[str]
    methodology: dict[str, object]


def optimization_recommendations(profile: dict[str, object]) -> list[dict[str, str]]:
    liabilities = {str(value).lower() for value in profile.get("modifiable_liabilities", [])}
    recommendations: list[dict[str, str]] = []

    def add(liability: str, strategy: str, validation: str) -> None:
        recommendations.append(
            {"liability": liability, "design_strategy": strategy, "required_validation": validation}
        )

    if any("lipophil" in value for value in liabilities):
        add("High lipophilicity", "Remove nonessential hydrophobes, reduce aromatic surface or introduce a solvent-exposed polar group.", "Re-measure potency, logD, solubility and permeability.")
    if any("solubility" in value for value in liabilities):
        add("Low solubility", "Explore ionizable handles, disrupt planarity/crystal packing and compare salt or formulation options.", "Measure kinetic/thermodynamic solubility and solid form.")
    if any("flexib" in value for value in liabilities):
        add("High flexibility", "Cyclize or shorten linkers and lock the bioactive conformation.", "Confirm target engagement and entropy/selectivity effects.")
    if any("aromatic" in value or "fsp3" in value for value in liabilities):
        add("Flat aromatic structure", "Introduce sp3-rich replacements or saturated bioisosteres.", "Recheck potency, selectivity, microsomal stability and solubility.")
    if any("hydrogen-bond" in value or "polar" in value for value in liabilities):
        add("Excess polarity", "Remove nonessential donors/acceptors or mask polarity with an intramolecular H-bond strategy.", "Measure permeability and aqueous solubility at assay pH.")
    if any("aggregation" in value for value in liabilities):
        add("Aggregation liability", "Reduce hydrophobic aromatic surface and test analogues with detergent-sensitive counterscreens.", "Run aggregation, DLS or orthogonal assay controls.")
    if any("synthesis" in value for value in liabilities):
        add("Synthetic complexity", "Prioritize modular analogues and common building blocks; reduce stereochemical and protecting-group burden.", "Document route, yield, purity and scalability.")
    if not recommendations:
        add("No major rule liability", "Optimize potency/selectivity while preserving the current property envelope.", "Run orthogonal potency, selectivity and developability experiments.")
    return recommendations


def assess_synthesis_feasibility(
    smiles: str,
    *,
    estimated_steps: int | None = None,
    commercially_available_building_blocks: bool | None = None,
    hazardous_steps: int = 0,
    protecting_groups: int = 0,
    precedent_documented: bool = False,
) -> SynthesisFeasibility:
    mol, _ = standardize_molecule(smiles)
    rings = int(Chem.rdMolDescriptors.CalcNumRings(mol))
    chiral = len(Chem.FindMolChiralCenters(mol, includeUnassigned=True))
    heavy = mol.GetNumHeavyAtoms()
    bridges = int(Chem.rdMolDescriptors.CalcNumBridgeheadAtoms(mol))
    spiro = int(Chem.rdMolDescriptors.CalcNumSpiroAtoms(mol))
    flags: list[str] = []
    process: list[str] = []
    penalty = 0
    if heavy > 50:
        flags.append("High heavy-atom count")
        penalty += 10
    if rings > 5:
        flags.append("High ring count")
        penalty += 8
    if chiral > 3:
        flags.append("Multiple stereocentres")
        penalty += min(15, chiral * 3)
    if bridges + spiro > 2:
        flags.append("Bridged/spiro complexity")
        penalty += min(12, (bridges + spiro) * 3)
    if estimated_steps is None:
        process.append("Route step count not provided")
        penalty += 10
    elif estimated_steps > 8:
        process.append("Long estimated route")
        penalty += min(20, (estimated_steps - 8) * 3)
    if commercially_available_building_blocks is not True:
        process.append("Building-block availability not confirmed")
        penalty += 8
    if hazardous_steps > 0:
        process.append("Hazardous transformation(s) reported")
        penalty += min(20, int(hazardous_steps) * 5)
    if protecting_groups > 2:
        process.append("Protecting-group burden")
        penalty += min(12, int(protecting_groups) * 3)
    if not precedent_documented:
        process.append("Synthetic precedent not documented")
        penalty += 8
    score = max(0, min(100, 100 - penalty))
    tier = "favourable" if score >= 80 else "review" if score >= 60 else "challenging"
    recommendations = [
        "Confirm route feasibility with a qualified chemist and reaction-level precedent.",
        "Record building blocks, hazards, yields, purification and scale assumptions.",
    ]
    if flags or process:
        recommendations.append("Compare simpler matched analogues before committing to scale-up.")
    return SynthesisFeasibility(
        score=score,
        tier=tier,
        molecular_complexity_flags=flags,
        process_flags=process,
        recommendations=recommendations,
        methodology={
            "type": "transparent structure/process checklist",
            "warning": "Not a retrosynthesis engine or manufacturing cost estimate.",
        },
    )


def assess_patent_evidence(
    *,
    exact_structure_search: bool,
    substructure_search: bool,
    similarity_search: bool,
    sequence_or_target_search: bool,
    jurisdiction_coverage: list[str] | None,
    family_status_reviewed: bool,
    claims_reviewed: bool,
    legal_reviewer: str = "",
) -> PatentEvidenceAssessment:
    required = {
        "Exact-structure search": exact_structure_search,
        "Substructure/Markush search": substructure_search,
        "Similarity search": similarity_search,
        "Target/sequence search": sequence_or_target_search,
        "Jurisdiction coverage": bool(jurisdiction_coverage),
        "Patent-family/legal-status review": family_status_reviewed,
        "Independent claim review": claims_reviewed,
        "Qualified legal reviewer": bool(legal_reviewer.strip()),
    }
    missing = [name for name, complete in required.items() if not complete]
    complete = not missing
    return PatentEvidenceAssessment(
        status="documented review complete" if complete else "incomplete / not legal clearance",
        complete=complete,
        missing_evidence=missing,
        warnings=[
            "Search results do not establish freedom to operate.",
            "Patent scope, ownership, legal status and jurisdiction require qualified legal review.",
        ],
        methodology={
            "type": "patent-evidence completeness gate",
            "jurisdictions": jurisdiction_coverage or [],
            "legal_reviewer": legal_reviewer,
        },
    )


def result_dict(result: SynthesisFeasibility | PatentEvidenceAssessment) -> dict[str, object]:
    return asdict(result)
