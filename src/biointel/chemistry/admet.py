from __future__ import annotations

from dataclasses import asdict, dataclass

from rdkit import Chem

from biointel import __version__
from biointel.chemistry.medicinal_chemistry import profile_medicinal_chemistry
from biointel.chemistry.standardization import standardization_dict, standardize_molecule
from biointel.discovery.admet_plugins import ENDPOINT_PLUGINS


@dataclass(frozen=True)
class AdmetProfile:
    # Backward-compatible core fields
    canonical_smiles: str
    molecular_weight: float
    logp: float
    tpsa: float
    hbd: int
    hba: int
    rotatable_bonds: int
    aromatic_rings: int
    fraction_csp3: float
    formal_charge: int
    lipinski_pass: bool
    veber_pass: bool
    bbb_likelihood: str
    solubility_class: str
    pains_alerts: list[str]
    structural_alerts: list[str]
    risk_score: int
    recommendations: list[str]
    # Expanded discovery-quality fields
    original_smiles: str
    standardized_smiles: str
    inchikey: str | None
    standardization: dict[str, object]
    qed: float
    synthetic_accessibility_heuristic: float
    molecular_complexity: float
    molar_refractivity: float
    ring_count: int
    scaffold_smiles: str
    esol_style_log_s: float
    aggregation_risk: str
    rule_results: list[dict[str, object]]
    alert_matches: list[dict[str, object]]
    developability_score: int
    risk_level: str
    confidence: str
    applicability_domain: str
    applicability_reasons: list[str]
    critical_blockers: list[str]
    modifiable_liabilities: list[str]
    endpoint_summary: list[dict[str, object]]
    methodology: dict[str, object]


_CUSTOM_ALERT_SMARTS = {
    "Michael acceptor": "[C,c]=[C,c][C,S](=O)",
    "Aldehyde": "[CX3H1](=O)[#6]",
    "Epoxide": "[C;r3]1[O;r3][C;r3]1",
    "Hydrazine/hydrazone motif": "[N;!$(N=*)]-[N;!$(N#*)]",
    "Polyhalogenated carbon": "[CX4](F)(F)(F)",
    "Acyl halide": "C(=O)[F,Cl,Br,I]",
    "Peroxide": "[O;X2]-[O;X2]",
    "Isocyanate": "N=C=O",
    "Alkylating sulfonate": "COS(=O)(=O)[#6]",
}
_CUSTOM_ALERT_PATTERNS = tuple(
    (name, pattern)
    for name, smarts in _CUSTOM_ALERT_SMARTS.items()
    if (pattern := Chem.MolFromSmarts(smarts)) is not None
)


def _custom_alerts(mol: Chem.Mol) -> list[str]:
    return [
        name
        for name, pattern in _CUSTOM_ALERT_PATTERNS
        if mol.HasSubstructMatch(pattern)
    ]


def _risk_level(risk: int) -> str:
    if risk <= 20:
        return "low"
    if risk <= 40:
        return "moderate"
    if risk <= 60:
        return "high"
    return "very high"


def _endpoint_summary(
    *,
    lipinski: bool,
    veber: bool,
    bbb: str,
    solubility: str,
    log_s: float,
    aggregation: str,
    smiles: str,
) -> list[dict[str, object]]:
    assessed = [
        {
            "domain": "Absorption",
            "endpoint": "Oral drug-likeness",
            "status": "favourable" if lipinski else "caution",
            "basis": "Lipinski rule-based screen",
            "value": lipinski,
        },
        {
            "domain": "Absorption",
            "endpoint": "Passive permeability",
            "status": "favourable" if veber else "caution",
            "basis": "Veber rule-based screen",
            "value": veber,
        },
        {
            "domain": "Absorption",
            "endpoint": "Aqueous solubility",
            "status": "heuristic",
            "basis": "ESOL-style descriptor estimate",
            "value": f"{solubility}; logS {log_s:.2f}",
        },
        {
            "domain": "Distribution",
            "endpoint": "Blood–brain barrier",
            "status": "heuristic",
            "basis": "Simple MW/TPSA/LogP/charge window",
            "value": bbb,
        },
        {
            "domain": "Assay behaviour",
            "endpoint": "Colloidal aggregation liability",
            "status": "heuristic",
            "basis": "Lipophilicity/aromaticity/charge flag",
            "value": aggregation,
        },
    ]
    not_assessed = {
        "Absorption": ["Caco-2 permeability", "Human intestinal absorption", "Oral bioavailability", "P-gp substrate/inhibition"],
        "Distribution": ["Plasma protein binding", "Volume of distribution", "Fraction unbound", "Quantitative brain penetration"],
        "Metabolism": ["CYP1A2 inhibition", "CYP2C9 inhibition", "CYP2C19 inhibition", "CYP2D6 inhibition", "CYP3A4 inhibition/substrate", "Metabolic stability", "Site of metabolism"],
        "Excretion": ["Total clearance", "Renal clearance", "Half-life"],
        "Toxicity": ["hERG", "Ames mutagenicity", "DILI/hepatotoxicity", "Skin sensitisation", "Carcinogenicity", "Acute toxicity", "Mitochondrial toxicity"],
    }
    for domain, endpoints in not_assessed.items():
        for endpoint in endpoints:
            plugin_result = ENDPOINT_PLUGINS.predict(endpoint, smiles)
            assessed.append(
                {
                    "domain": domain,
                    "endpoint": endpoint,
                    "status": plugin_result.get("status", "not assessed"),
                    "basis": plugin_result.get(
                        "basis",
                        (
                            f"Qualified endpoint plugin {plugin_result.get('model_id')} "
                            f"v{plugin_result.get('model_version')}"
                            if plugin_result.get("status") == "model"
                            else "No qualified endpoint model installed"
                        ),
                    ),
                    "value": plugin_result.get("value"),
                    "model_id": plugin_result.get("model_id"),
                    "model_version": plugin_result.get("model_version"),
                    "artifact_sha256": plugin_result.get("artifact_sha256"),
                    "training_dataset_sha256": plugin_result.get("training_dataset_sha256"),
                }
            )
    return assessed


def profile_admet(smiles: str) -> AdmetProfile:
    mol, standardization = standardize_molecule(smiles)
    medchem = profile_medicinal_chemistry(mol)
    rules = {rule.name: rule for rule in medchem.rules}
    lipinski = rules["Lipinski rule of five"].passed
    veber = rules["Veber"].passed

    if (
        medchem.molecular_weight < 450
        and medchem.tpsa < 90
        and -1 <= medchem.logp <= 5
        and abs(medchem.formal_charge) <= 1
    ):
        bbb = "higher rule-based likelihood"
    else:
        bbb = "lower/uncertain rule-based likelihood"

    pains = sorted({item.description for item in medchem.alerts if item.catalog == "PAINS"})
    catalog_alerts = sorted(
        {f"{item.catalog}: {item.description}" for item in medchem.alerts if item.catalog != "PAINS"}
    )
    custom_alerts = _custom_alerts(mol)
    structural_alerts = sorted(set(catalog_alerts + custom_alerts))

    applicability_reasons: list[str] = []
    allowed_elements = {1, 5, 6, 7, 8, 9, 14, 15, 16, 17, 35, 53}
    observed = {atom.GetAtomicNum() for atom in mol.GetAtoms()}
    if not observed.issubset(allowed_elements):
        applicability_reasons.append("Contains element(s) outside the conventional organic screening set.")
    if not 50 <= medchem.molecular_weight <= 800:
        applicability_reasons.append("Molecular weight is outside the 50–800 screening domain.")
    if not -5 <= medchem.logp <= 8:
        applicability_reasons.append("LogP is outside the −5 to 8 screening domain.")
    if not 3 <= medchem.heavy_atoms <= 100:
        applicability_reasons.append("Heavy-atom count is outside the 3–100 screening domain.")
    applicability = "inside screening domain" if not applicability_reasons else "outside/edge of screening domain"

    critical_blockers: list[str] = []
    liabilities: list[str] = []
    recommendations: list[str] = []
    if medchem.molecular_weight > 500:
        liabilities.append("High molecular weight")
        recommendations.append("Reduce molecular weight or remove nonessential substituents.")
    if medchem.logp > 5:
        liabilities.append("High lipophilicity")
        recommendations.append("Reduce lipophilicity while preserving target engagement.")
    if medchem.hbd > 5:
        liabilities.append("Excess hydrogen-bond donors")
        recommendations.append("Reduce exposed hydrogen-bond donors or consider intramolecular H-bonding strategies.")
    if medchem.hba > 10:
        liabilities.append("Excess hydrogen-bond acceptors")
        recommendations.append("Reduce nonessential hydrogen-bond acceptors.")
    if medchem.tpsa > 140:
        liabilities.append("High polar surface area")
        recommendations.append("Reduce exposed polar surface area for passive permeability.")
    if medchem.rotatable_bonds > 10:
        liabilities.append("High conformational flexibility")
        recommendations.append("Rigidify flexible linkers or reduce rotatable bonds.")
    if medchem.esol_style_log_s < -4:
        liabilities.append("Low predicted aqueous solubility")
        recommendations.append("Explore polarity, ionisation or crystal-packing changes to improve solubility.")
    if medchem.fraction_csp3 < 0.2 and medchem.aromatic_rings >= 3:
        liabilities.append("Low Fsp3/high aromaticity")
        recommendations.append("Increase three-dimensional character where compatible with potency.")
    if medchem.synthetic_accessibility_heuristic > 6:
        liabilities.append("Higher synthesis-complexity heuristic")
        recommendations.append("Prioritise simpler analogues or document a feasible synthetic route.")
    if medchem.aggregation_risk == "higher":
        liabilities.append("Possible colloidal aggregation liability")
        recommendations.append("Run detergent-sensitive counterscreens and aggregation controls.")
    if pains:
        recommendations.append("Review PAINS matches with orthogonal assays; do not reject solely by filter.")
    if structural_alerts:
        recommendations.append("Review reactive/toxicophore/filter alerts and inspect matched substructures.")
    if abs(medchem.formal_charge) > 1:
        liabilities.append("High formal charge")
        recommendations.append("Confirm protonation state and permeability implications at assay pH.")
    if standardization.warnings:
        recommendations.append("Review standardisation warnings and retain the submitted structure in provenance.")

    if medchem.esol_style_log_s < -6:
        critical_blockers.append("Very low descriptor-based solubility estimate")
    if len(pains) >= 3:
        critical_blockers.append("Multiple PAINS catalog matches")
    if len(structural_alerts) >= 8:
        critical_blockers.append("High structural-alert burden")

    rule_failures = sum(not item.passed for item in medchem.rules)
    penalty = 0
    penalty += min(28, len(rules["Lipinski rule of five"].failed_criteria) * 7)
    penalty += 8 if not veber else 0
    penalty += min(15, len(pains) * 5)
    penalty += min(18, len(structural_alerts) * 2)
    penalty += 10 if medchem.esol_style_log_s < -4 else 0
    penalty += 6 if medchem.qed < 0.35 else 0
    penalty += 7 if medchem.aggregation_risk == "higher" else 0
    penalty += 6 if medchem.synthetic_accessibility_heuristic > 6 else 0
    penalty += 5 if abs(medchem.formal_charge) > 1 else 0
    penalty += min(8, max(0, rule_failures - 2) * 2)
    penalty += 8 if applicability_reasons else 0
    risk = max(0, min(100, int(round(penalty))))
    developability = 100 - risk

    if not recommendations:
        recommendations.append(
            "No major rule-based liabilities detected; continue with endpoint-specific models and experimental validation."
        )

    confidence = (
        "screening-only; descriptor calculations reliable, biological endpoint confidence not established"
        if not applicability_reasons
        else "low; structure lies outside or at the edge of the screening domain"
    )

    return AdmetProfile(
        canonical_smiles=standardization.standardized_smiles,
        molecular_weight=medchem.molecular_weight,
        logp=medchem.logp,
        tpsa=medchem.tpsa,
        hbd=medchem.hbd,
        hba=medchem.hba,
        rotatable_bonds=medchem.rotatable_bonds,
        aromatic_rings=medchem.aromatic_rings,
        fraction_csp3=medchem.fraction_csp3,
        formal_charge=medchem.formal_charge,
        lipinski_pass=lipinski,
        veber_pass=veber,
        bbb_likelihood=bbb,
        solubility_class=medchem.solubility_class,
        pains_alerts=pains,
        structural_alerts=structural_alerts,
        risk_score=risk,
        recommendations=recommendations,
        original_smiles=standardization.original_smiles,
        standardized_smiles=standardization.standardized_smiles,
        inchikey=standardization.inchikey,
        standardization=standardization_dict(standardization),
        qed=medchem.qed,
        synthetic_accessibility_heuristic=medchem.synthetic_accessibility_heuristic,
        molecular_complexity=medchem.molecular_complexity,
        molar_refractivity=medchem.molar_refractivity,
        ring_count=medchem.ring_count,
        scaffold_smiles=medchem.scaffold_smiles,
        esol_style_log_s=medchem.esol_style_log_s,
        aggregation_risk=medchem.aggregation_risk,
        rule_results=[asdict(item) for item in medchem.rules],
        alert_matches=[asdict(item) for item in medchem.alerts],
        developability_score=developability,
        risk_level=_risk_level(risk),
        confidence=confidence,
        applicability_domain=applicability,
        applicability_reasons=applicability_reasons,
        critical_blockers=critical_blockers,
        modifiable_liabilities=sorted(set(liabilities)),
        endpoint_summary=_endpoint_summary(
            lipinski=lipinski,
            veber=veber,
            bbb=bbb,
            solubility=medchem.solubility_class,
            log_s=medchem.esol_style_log_s,
            aggregation=medchem.aggregation_risk,
            smiles=standardization.standardized_smiles,
        ),
        methodology={
            "type": "descriptor-and-rule-based early-discovery triage",
            "score_label": "rule-based prioritization score",
            "validated_endpoint_model": bool(ENDPOINT_PLUGINS.endpoints()),
            "qualified_endpoint_plugins": ENDPOINT_PLUGINS.endpoints(),
            "structure_basis": "standardized parent structure",
            "warning": "Not a clinical, toxicological or regulatory prediction.",
            "version": f"BioIntel Discovery {__version__}",
        },
    )


def profile_dict(result: AdmetProfile) -> dict[str, object]:
    return asdict(result)
