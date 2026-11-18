from __future__ import annotations

import math
from typing import Any, Iterable

import numpy as np
import pandas as pd
from rdkit import Chem, DataStructs
from rdkit.Chem import Crippen, Descriptors, Lipinski, QED, rdFingerprintGenerator, rdMolDescriptors
from rdkit.Chem.Scaffolds import MurckoScaffold
from rdkit.Chem.MolStandardize import rdMolStandardize

from biointel.neuro_cns.schemas import concentration_to_nm, normalize_affinity_rows, validate_probability


def _clip(value: float, low: float, high: float) -> float:
    return float(min(high, max(low, value)))


def _linear_desirability(value: float, ideal_low: float, ideal_high: float, hard_low: float, hard_high: float) -> float:
    if ideal_low <= value <= ideal_high:
        return 1.0
    if value < ideal_low:
        if value <= hard_low:
            return 0.0
        return (value - hard_low) / max(ideal_low - hard_low, 1e-12)
    if value >= hard_high:
        return 0.0
    return (hard_high - value) / max(hard_high - ideal_high, 1e-12)


def parse_smiles(smiles: str, *, standardize: bool = True) -> Chem.Mol:
    text = str(smiles or "").strip()
    if not text:
        raise ValueError("SMILES is required.")
    mol = Chem.MolFromSmiles(text)
    if mol is None:
        raise ValueError("SMILES could not be parsed. Check atom symbols, ring closures and brackets.")
    if standardize:
        try:
            mol = rdMolStandardize.Cleanup(mol)
            mol = rdMolStandardize.FragmentParent(mol)
            mol = rdMolStandardize.Uncharger().uncharge(mol)
            Chem.SanitizeMol(mol)
        except Exception as exc:
            raise ValueError(f"Structure standardization failed: {exc}") from exc
    return mol


def molecular_descriptors(smiles: str) -> dict[str, Any]:
    original = str(smiles or "").strip()
    raw_mol = parse_smiles(original, standardize=False)
    mol = parse_smiles(original, standardize=True)
    canonical_raw = Chem.MolToSmiles(raw_mol, canonical=True)
    canonical = Chem.MolToSmiles(mol, canonical=True)
    mw = float(Descriptors.MolWt(mol))
    logp = float(Crippen.MolLogP(mol))
    tpsa = float(rdMolDescriptors.CalcTPSA(mol))
    hbd = int(Lipinski.NumHDonors(mol))
    hba = int(Lipinski.NumHAcceptors(mol))
    rotatable = int(Lipinski.NumRotatableBonds(mol))
    rings = int(rdMolDescriptors.CalcNumRings(mol))
    aromatic_rings = int(rdMolDescriptors.CalcNumAromaticRings(mol))
    fraction_csp3 = float(rdMolDescriptors.CalcFractionCSP3(mol))
    heavy_atoms = int(mol.GetNumHeavyAtoms())
    formal_charge = int(sum(atom.GetFormalCharge() for atom in mol.GetAtoms()))
    elements = sorted({atom.GetSymbol() for atom in mol.GetAtoms()})
    halogens = int(sum(atom.GetAtomicNum() in {9, 17, 35, 53} for atom in mol.GetAtoms()))
    return {
        "input_smiles": original,
        "canonical_input_smiles": canonical_raw,
        "canonical_smiles": canonical,
        "structure_standardized": canonical != canonical_raw,
        "molecular_weight": round(mw, 4),
        "exact_molecular_weight": round(float(Descriptors.ExactMolWt(mol)), 4),
        "logp": round(logp, 4),
        "molar_refractivity": round(float(Crippen.MolMR(mol)), 4),
        "tpsa": round(tpsa, 4),
        "hbd_count": hbd,
        "hba_count": hba,
        "rotatable_bonds": rotatable,
        "ring_count": rings,
        "aromatic_ring_count": aromatic_rings,
        "fraction_csp3": round(fraction_csp3, 4),
        "qed": round(float(QED.qed(mol)), 4),
        "heavy_atom_count": heavy_atoms,
        "formal_charge": formal_charge,
        "halogen_count": halogens,
        "elements": elements,
    }


def descriptor_applicability(descriptors: dict[str, Any]) -> dict[str, Any]:
    checks = {
        "molecular_weight_80_to_700": 80 <= float(descriptors["molecular_weight"]) <= 700,
        "tpsa_0_to_180": 0 <= float(descriptors["tpsa"]) <= 180,
        "logp_minus3_to_8": -3 <= float(descriptors["logp"]) <= 8,
        "heavy_atoms_3_to_80": 3 <= int(descriptors["heavy_atom_count"]) <= 80,
        "supported_elements": set(descriptors.get("elements", [])) <= {"H", "B", "C", "N", "O", "F", "P", "S", "Cl", "Br", "I", "Si", "Se"},
    }
    passed = sum(bool(value) for value in checks.values())
    return {
        "inside": passed == len(checks),
        "checks": checks,
        "checks_passed": passed,
        "checks_total": len(checks),
        "warning": None if passed == len(checks) else "Structure is outside one or more local screening-domain checks.",
    }


def cns_mpo_proxy(descriptors: dict[str, Any]) -> dict[str, Any]:
    """Transparent six-factor screening proxy inspired by CNS MPO concepts.

    The original CNS MPO framework includes measured/estimated properties such as
    logD and pKa. This local implementation deliberately uses only descriptors
    available deterministically from the submitted structure and labels the
    result as a proxy.
    """

    mw = float(descriptors["molecular_weight"])
    logp = float(descriptors["logp"])
    tpsa = float(descriptors["tpsa"])
    hbd = float(descriptors["hbd_count"])
    hba = float(descriptors["hba_count"])
    rot = float(descriptors["rotatable_bonds"])
    factors = {
        "molecular_weight": _linear_desirability(mw, 180, 360, 100, 520),
        "logp": _linear_desirability(logp, 1.0, 3.0, -1.0, 5.5),
        "tpsa": _linear_desirability(tpsa, 20, 70, 0, 120),
        "hbd_count": _linear_desirability(hbd, 0, 1, 0, 4),
        "hba_count": _linear_desirability(hba, 1, 6, 0, 11),
        "rotatable_bonds": _linear_desirability(rot, 0, 5, 0, 12),
    }
    score = float(sum(factors.values()))
    return {
        "score": round(score, 3),
        "maximum": 6.0,
        "factor_desirability": {key: round(value, 3) for key, value in factors.items()},
        "method": "BioIntel transparent six-descriptor CNS MPO proxy",
        "validated_cns_mpo": False,
    }


def bbb_permeability(smiles: str, compound_id: str | None = None) -> dict[str, Any]:
    descriptors = molecular_descriptors(smiles)
    domain = descriptor_applicability(descriptors)
    mpo = cns_mpo_proxy(descriptors)
    rules = {
        "mw_le_450": float(descriptors["molecular_weight"]) <= 450,
        "tpsa_le_90": float(descriptors["tpsa"]) <= 90,
        "hbd_le_3": int(descriptors["hbd_count"]) <= 3,
        "logp_in_screening_window": -0.5 <= float(descriptors["logp"]) <= 5.0,
        "rotatable_bonds_le_10": int(descriptors["rotatable_bonds"]) <= 10,
        "mpo_proxy_ge_4": float(mpo["score"]) >= 4.0,
        "absolute_formal_charge_le_1": abs(int(descriptors["formal_charge"])) <= 1,
    }
    positives = sum(bool(value) for value in rules.values())
    rule_likely = all((rules["mw_le_450"], rules["tpsa_le_90"], rules["hbd_le_3"])) and positives >= 6
    logit = (
        2.25
        + 0.48 * float(descriptors["logp"])
        - 0.026 * float(descriptors["tpsa"])
        - 0.0035 * max(float(descriptors["molecular_weight"]) - 300.0, 0.0)
        - 0.28 * float(descriptors["hbd_count"])
        - 0.18 * abs(float(descriptors["formal_charge"]))
    )
    probability_proxy = float(1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, logit)))))
    probabilistic_likely = probability_proxy >= 0.55
    consensus_votes = int(rule_likely) + int(probabilistic_likely) + int(float(mpo["score"]) >= 4.0)
    if not domain["inside"]:
        classification = "outside_applicability_domain"
        confidence = "low-outside-domain"
    elif consensus_votes >= 2:
        classification = "likely_permeable"
        confidence = "higher-screening-confidence" if consensus_votes == 3 and probability_proxy >= 0.70 else "moderate-screening-confidence"
    elif consensus_votes == 1:
        classification = "uncertain"
        confidence = "borderline"
    else:
        classification = "unlikely_or_uncertain"
        confidence = "lower-screening-confidence"
    warnings: list[str] = []
    if descriptors.get("structure_standardized"):
        warnings.append("Input was standardized to the largest neutral parent before descriptor calculation")
    if not domain["inside"]:
        warnings.append(str(domain["warning"]))
    if abs(int(descriptors["formal_charge"])) > 1:
        warnings.append("Multiple formal charges reduce confidence in passive-permeability screening")
    return {
        "compound_id": compound_id,
        "classification": classification,
        "screening_confidence": confidence,
        "consensus_votes": consensus_votes,
        "consensus_total": 3,
        "local_probability_proxy": round(probability_proxy, 4),
        "descriptors": descriptors,
        "applicability_domain": domain,
        "cns_mpo_proxy": mpo,
        "rule_results": rules,
        "rules_passed": positives,
        "rules_total": len(rules),
        "warnings": warnings,
        "scientific_boundary": "Descriptor-based research screen; not an experimental BBB measurement or externally calibrated probability.",
    }


def bbb_batch(rows: Iterable[dict[str, Any]]) -> pd.DataFrame:
    output: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        compound_id = str(row.get("compound_id") or row.get("id") or f"compound_{index + 1}")
        smiles = str(row.get("smiles") or row.get("compound_structure") or "")
        try:
            result = bbb_permeability(smiles, compound_id)
            flat = {
                "compound_id": compound_id,
                "input_smiles": smiles,
                "classification": result["classification"],
                "screening_confidence": result["screening_confidence"],
                "cns_mpo_proxy": result["cns_mpo_proxy"]["score"],
                "rules_passed": result["rules_passed"],
                **result["descriptors"],
                "error": None,
            }
        except Exception as exc:
            flat = {"compound_id": compound_id, "input_smiles": smiles, "error": str(exc)}
        output.append(flat)
    return pd.DataFrame(output)


def _pgp_efflux_proxy(desc: dict[str, Any]) -> float:
    tpsa = float(desc["tpsa"])
    hba = float(desc["hba_count"])
    rot = float(desc["rotatable_bonds"])
    mw = float(desc["molecular_weight"])
    raw = 0.20 + 0.0035 * max(tpsa - 45, 0) + 0.035 * max(hba - 4, 0) + 0.025 * max(rot - 4, 0) + 0.001 * max(mw - 350, 0)
    return _clip(raw, 0.05, 0.95)


def _metabolic_stability_proxy(desc: dict[str, Any]) -> float:
    logp = float(desc["logp"])
    rot = float(desc["rotatable_bonds"])
    aromatic = float(desc["aromatic_ring_count"])
    csp3 = float(desc["fraction_csp3"])
    liability = 0.08 * max(logp - 2.5, 0) + 0.04 * max(rot - 5, 0) + 0.035 * max(aromatic - 2, 0)
    stability = 0.72 + 0.20 * csp3 - liability
    return _clip(stability, 0.05, 0.95)


def cns_drug_likeness(smiles: str) -> dict[str, Any]:
    bbb = bbb_permeability(smiles)
    desc = bbb["descriptors"]
    mol = parse_smiles(smiles)
    qed = float(QED.qed(mol))
    pgp = _pgp_efflux_proxy(desc)
    stability = _metabolic_stability_proxy(desc)
    mpo_scaled = float(bbb["cns_mpo_proxy"]["score"]) / 6.0
    bbb_factor = 1.0 if bbb["classification"] == "likely_permeable" else 0.35
    factors = {
        "bbb_screen": {"value": bbb_factor, "weight": 0.28},
        "cns_mpo_proxy": {"value": mpo_scaled, "weight": 0.25},
        "qed": {"value": qed, "weight": 0.17},
        "non_pgp_proxy": {"value": 1.0 - pgp, "weight": 0.18},
        "metabolic_stability_proxy": {"value": stability, "weight": 0.12},
    }
    score = 100.0 * sum(item["value"] * item["weight"] for item in factors.values())
    warnings: list[str] = []
    if pgp >= 0.65:
        warnings.append("Elevated structural efflux/P-gp proxy")
    if stability <= 0.35:
        warnings.append("Low structural metabolic-stability proxy")
    if float(desc["tpsa"]) > 90:
        warnings.append("High polar surface area may limit passive CNS exposure")
    if abs(int(desc["formal_charge"])) >= 2:
        warnings.append("Multiple formal charges may limit passive CNS exposure")
    return {
        "composite_score": round(score, 2),
        "rating": "favourable" if score >= 70 else "borderline" if score >= 50 else "unfavourable",
        "factors": {key: {**value, "value": round(float(value["value"]), 4)} for key, value in factors.items()},
        "pgp_efflux_proxy": round(pgp, 4),
        "metabolic_stability_proxy": round(stability, 4),
        "warnings": warnings,
        "bbb_result": bbb,
        "scientific_boundary": "Transparent structural screening score; external calibration required.",
    }


def cns_adme_transporters(smiles: str) -> dict[str, Any]:
    desc = molecular_descriptors(smiles)
    mol = parse_smiles(smiles)
    pgp = _pgp_efflux_proxy(desc)
    bcrp = _clip(0.12 + 0.004 * max(float(desc["tpsa"]) - 55, 0) + 0.03 * max(float(desc["hba_count"]) - 5, 0), 0.05, 0.95)
    stability = _metabolic_stability_proxy(desc)
    logp = float(desc["logp"])
    aromatic = int(desc["aromatic_ring_count"])
    hba = int(desc["hba_count"])
    cyp_alerts = {
        "CYP1A2_structural_alert": bool(aromatic >= 3 and logp >= 2.0),
        "CYP2D6_structural_alert": bool(logp >= 2.0 and hba >= 2 and any(atom.GetAtomicNum() == 7 for atom in mol.GetAtoms())),
        "CYP3A4_structural_alert": bool(float(desc["molecular_weight"]) >= 350 and logp >= 3.0),
    }
    plasma_binding_proxy = _clip(0.35 + 0.10 * max(logp, 0) + 0.025 * aromatic, 0.10, 0.99)
    absorption_proxy = _clip(0.92 - 0.004 * max(float(desc["tpsa"]) - 60, 0) - 0.025 * max(float(desc["rotatable_bonds"]) - 8, 0), 0.05, 0.98)
    passive_permeability_proxy = _clip(0.82 + 0.07 * logp - 0.005 * float(desc["tpsa"]) - 0.035 * abs(float(desc["formal_charge"])), 0.02, 0.98)
    log_s_proxy = 0.5 - 1.05 * logp - 0.0062 * float(desc["molecular_weight"]) + 0.066 * float(desc["rotatable_bonds"]) + 0.066 * float(desc["aromatic_ring_count"])
    clearance_risk_proxy = _clip(1.0 - stability + 0.10 * max(logp - 3.0, 0), 0.02, 0.98)
    liabilities = [name.replace("_structural_alert", "") for name, flag in cyp_alerts.items() if flag]
    if pgp >= 0.65:
        liabilities.append("P-gp efflux")
    if bcrp >= 0.65:
        liabilities.append("BCRP efflux")
    return {
        "descriptors": desc,
        "pgp_substrate_proxy": round(pgp, 4),
        "bcrp_substrate_proxy": round(bcrp, 4),
        "metabolic_stability_proxy": round(stability, 4),
        "plasma_protein_binding_proxy": round(plasma_binding_proxy, 4),
        "oral_absorption_proxy": round(absorption_proxy, 4),
        "passive_permeability_proxy": round(passive_permeability_proxy, 4),
        "aqueous_solubility_logS_proxy": round(float(log_s_proxy), 4),
        "clearance_risk_proxy": round(clearance_risk_proxy, 4),
        "cyp_alerts": cyp_alerts,
        "liabilities": liabilities,
        "applicability_domain": descriptor_applicability(desc),
        "scientific_boundary": "Structure-derived alerts/proxies only; no measured ADME, transporter or metabolic values are inferred.",
    }


def blood_csf_barrier(smiles: str) -> dict[str, Any]:
    desc = molecular_descriptors(smiles)
    domain = descriptor_applicability(desc)
    score = (
        0.30 * _linear_desirability(float(desc["molecular_weight"]), 150, 380, 80, 520)
        + 0.30 * _linear_desirability(float(desc["tpsa"]), 15, 80, 0, 130)
        + 0.20 * _linear_desirability(float(desc["logp"]), 0.5, 3.5, -1.5, 6.0)
        + 0.10 * _linear_desirability(float(desc["hbd_count"]), 0, 2, 0, 5)
        + 0.10 * _linear_desirability(float(desc["rotatable_bonds"]), 0, 7, 0, 14)
    )
    if not domain["inside"]:
        classification = "outside_applicability_domain"
    elif score >= 0.72:
        classification = "provisionally_favourable"
    elif score >= 0.52:
        classification = "indeterminate"
    else:
        classification = "uncertain_or_unfavourable"
    return {
        "csf_permeability_classification": classification,
        "provisional_score": round(score, 4),
        "descriptor_values": desc,
        "applicability_domain": domain,
        "methodology_status": "exploratory_descriptor_proxy_fail_closed",
        "required_confirmation": ["approved blood-CSF reference method", "route-specific exposure data", "experimental CSF/plasma measurements"],
        "scientific_boundary": "Exploratory only; a validated blood-CSF methodology is not claimed.",
    }


def simulate_brain_exposure(
    *,
    initial_plasma_concentration: float,
    half_life_hours: float,
    duration_hours: float,
    passive_permeability_factor: float,
    efflux_ratio: float,
    fraction_unbound_plasma: float,
    fraction_unbound_brain: float,
    effective_threshold: float = 0.0,
    points: int = 121,
    route: str = "iv",
    absorption_half_life_hours: float | None = None,
    dose_count: int = 1,
    dosing_interval_hours: float = 24.0,
    brain_equilibration_half_life_hours: float = 0.5,
) -> dict[str, Any]:
    values = {
        "initial_plasma_concentration": initial_plasma_concentration,
        "half_life_hours": half_life_hours,
        "duration_hours": duration_hours,
        "passive_permeability_factor": passive_permeability_factor,
        "efflux_ratio": efflux_ratio,
        "fraction_unbound_plasma": fraction_unbound_plasma,
        "fraction_unbound_brain": fraction_unbound_brain,
        "dosing_interval_hours": dosing_interval_hours,
        "brain_equilibration_half_life_hours": brain_equilibration_half_life_hours,
    }
    if any(not math.isfinite(float(value)) for value in values.values()):
        raise ValueError("All PK parameters must be finite numbers.")
    if initial_plasma_concentration < 0 or half_life_hours <= 0 or duration_hours <= 0:
        raise ValueError("Concentration must be non-negative; half-life and duration must be positive.")
    if passive_permeability_factor <= 0 or efflux_ratio < 0:
        raise ValueError("Passive factor must be positive and efflux ratio cannot be negative.")
    if not 0 < fraction_unbound_plasma <= 1 or not 0 < fraction_unbound_brain <= 1:
        raise ValueError("Unbound fractions must be in (0, 1].")
    if dose_count < 1 or dosing_interval_hours <= 0 or brain_equilibration_half_life_hours <= 0:
        raise ValueError("Dose count, dosing interval and brain-equilibration half-life must be positive.")
    route_token = str(route).strip().lower()
    if route_token not in {"iv", "oral"}:
        raise ValueError("Route must be 'iv' or 'oral'.")
    if route_token == "oral":
        absorption_half_life_hours = float(absorption_half_life_hours or 1.0)
        if absorption_half_life_hours <= 0:
            raise ValueError("Oral absorption half-life must be positive.")

    times = np.linspace(0.0, float(duration_hours), int(max(20, points)))
    elimination = math.log(2.0) / float(half_life_hours)
    plasma_total = np.zeros_like(times)
    dose_times = [index * float(dosing_interval_hours) for index in range(int(dose_count)) if index * float(dosing_interval_hours) <= duration_hours]
    for dose_time in dose_times:
        elapsed = times - dose_time
        active = elapsed >= 0
        if route_token == "iv":
            plasma_total[active] += float(initial_plasma_concentration) * np.exp(-elimination * elapsed[active])
        else:
            absorption = math.log(2.0) / float(absorption_half_life_hours)
            if abs(absorption - elimination) < 1e-9:
                contribution = float(initial_plasma_concentration) * elimination * elapsed[active] * np.exp(-elimination * elapsed[active])
            else:
                contribution = float(initial_plasma_concentration) * absorption / (absorption - elimination) * (np.exp(-elimination * elapsed[active]) - np.exp(-absorption * elapsed[active]))
            plasma_total[active] += np.maximum(contribution, 0.0)

    kp_uu = _clip(float(passive_permeability_factor) / (1.0 + float(efflux_ratio)), 0.001, 5.0)
    plasma_unbound = plasma_total * float(fraction_unbound_plasma)
    equilibrium_brain_unbound = plasma_unbound * kp_uu
    brain_unbound = np.zeros_like(equilibrium_brain_unbound)
    brain_rate = math.log(2.0) / float(brain_equilibration_half_life_hours)
    for index in range(1, len(times)):
        dt = float(times[index] - times[index - 1])
        alpha = 1.0 - math.exp(-brain_rate * dt)
        brain_unbound[index] = brain_unbound[index - 1] + alpha * (equilibrium_brain_unbound[index] - brain_unbound[index - 1])
    if len(brain_unbound):
        brain_unbound[0] = equilibrium_brain_unbound[0] if route_token == "iv" else 0.0
    brain_total = brain_unbound / float(fraction_unbound_brain)
    valid_plasma = plasma_total > 1e-12
    kp_values = np.divide(brain_total, plasma_total, out=np.zeros_like(brain_total), where=valid_plasma)
    kp = float(np.nanmedian(kp_values[valid_plasma])) if valid_plasma.any() else 0.0
    if effective_threshold > 0:
        above = brain_unbound >= float(effective_threshold)
        time_above = float(np.trapezoid(above.astype(float), times))
    else:
        time_above = 0.0
    frame = pd.DataFrame({
        "time_hours": times,
        "plasma_total": plasma_total,
        "plasma_unbound": plasma_unbound,
        "brain_total": brain_total,
        "brain_unbound": brain_unbound,
        "equilibrium_brain_unbound": equilibrium_brain_unbound,
    })
    peak_index = int(np.argmax(brain_unbound)) if len(brain_unbound) else 0
    return {
        "kp_total": round(kp, 4),
        "kp_uu_brain": round(kp_uu, 4),
        "time_above_effective_threshold_hours": round(time_above, 4),
        "peak_brain_unbound": round(float(brain_unbound.max()), 6),
        "time_to_peak_brain_hours": round(float(times[peak_index]), 4),
        "plasma_auc": round(float(np.trapezoid(plasma_total, times)), 6),
        "brain_unbound_auc": round(float(np.trapezoid(brain_unbound, times)), 6),
        "dose_times_hours": dose_times,
        "parameters": values | {"effective_threshold": effective_threshold, "route": route_token, "absorption_half_life_hours": absorption_half_life_hours, "dose_count": int(dose_count)},
        "curve": frame,
        "scientific_boundary": "Research PK simulation driven entirely by supplied parameters; not a validated PBPK model.",
    }


def receptor_occupancy(
    free_brain_concentration: float,
    affinity_rows: Iterable[dict[str, Any]],
    *,
    concentration_unit: str = "nM",
    default_affinity_unit: str = "nM",
) -> pd.DataFrame:
    concentration_nm = concentration_to_nm(float(free_brain_concentration), concentration_unit)
    source_rows = list(affinity_rows)
    normalized = normalize_affinity_rows(source_rows, default_unit=default_affinity_unit)
    results: list[dict[str, Any]] = []
    for index, row in enumerate(normalized):
        source = source_rows[index] if index < len(source_rows) else {}
        target = str(row.get("target") or f"target_{index + 1}")
        affinity_nm = float(row.get("affinity_nm", np.nan))
        error = row.get("error")
        try:
            hill = float(source.get("hill_coefficient", source.get("hill", 1.0))) if isinstance(source, dict) else 1.0
            if not math.isfinite(hill) or hill <= 0:
                raise ValueError("Hill coefficient must be positive")
        except Exception as exc:
            error = str(exc)
            hill = 1.0
        if error or not math.isfinite(affinity_nm) or affinity_nm <= 0:
            results.append({
                "target": target, "affinity_nm": affinity_nm, "occupancy_percent": np.nan,
                "role": source.get("role", "unspecified") if isinstance(source, dict) else "unspecified",
                "error": error or "Kd/Ki must be positive",
            })
            continue
        numerator = concentration_nm ** hill
        occupancy = 100.0 * numerator / (numerator + affinity_nm ** hill)
        results.append({
            "target": target,
            "affinity_nm": round(affinity_nm, 6),
            "input_affinity_unit": row.get("input_unit"),
            "free_brain_concentration_nm": round(concentration_nm, 6),
            "hill_coefficient": round(hill, 4),
            "occupancy_percent": round(occupancy, 4),
            "engagement_band": "high" if occupancy >= 80 else "moderate" if occupancy >= 50 else "low",
            "role": source.get("role", "unspecified") if isinstance(source, dict) else "unspecified",
            "error": None,
        })
    frame = pd.DataFrame(results)
    if not frame.empty and "role" in frame:
        primary = pd.to_numeric(frame.loc[frame["role"].astype(str).str.lower().isin({"primary", "on_target", "on-target"}), "occupancy_percent"], errors="coerce")
        off = pd.to_numeric(frame.loc[~frame["role"].astype(str).str.lower().isin({"primary", "on_target", "on-target"}), "occupancy_percent"], errors="coerce")
        primary_max = float(primary.max()) if not primary.dropna().empty else np.nan
        off_max = float(off.max()) if not off.dropna().empty else np.nan
        margin = primary_max - off_max if math.isfinite(primary_max) and math.isfinite(off_max) else np.nan
        frame["selectivity_margin_percent"] = round(margin, 4) if math.isfinite(margin) else np.nan
    return frame



def chemical_space_applicability(smiles: str, reference_smiles: Iterable[str]) -> dict[str, Any]:
    """Compare a query compound with a supplied reference chemical space."""
    query = parse_smiles(smiles)
    reference_molecules: list[Chem.Mol] = []
    invalid = 0
    for value in reference_smiles:
        try:
            reference_molecules.append(parse_smiles(str(value)))
        except Exception:
            invalid += 1
    if not reference_molecules:
        raise ValueError("No valid reference SMILES were supplied for applicability assessment.")
    generator = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048)
    query_fp = generator.GetFingerprint(query)
    similarities = [float(DataStructs.TanimotoSimilarity(query_fp, generator.GetFingerprint(molecule))) for molecule in reference_molecules]
    query_desc = molecular_descriptors(Chem.MolToSmiles(query))
    descriptor_names = ["molecular_weight", "logp", "tpsa", "hbd_count", "hba_count", "rotatable_bonds"]
    reference_rows = [molecular_descriptors(Chem.MolToSmiles(molecule)) for molecule in reference_molecules]
    z_scores: dict[str, float] = {}
    for name in descriptor_names:
        values = np.asarray([float(row[name]) for row in reference_rows], dtype=float)
        scale = float(values.std(ddof=1)) if len(values) > 1 else 0.0
        z_scores[name] = round(float((float(query_desc[name]) - values.mean()) / scale), 6) if scale > 1e-12 else 0.0
    max_abs_z = max(abs(value) for value in z_scores.values()) if z_scores else 0.0
    nearest = max(similarities) if similarities else 0.0
    inside = nearest >= 0.30 and max_abs_z <= 3.0
    return {
        "inside_reference_space": inside,
        "nearest_morgan_tanimoto": round(nearest, 6),
        "median_morgan_tanimoto": round(float(np.median(similarities)), 6),
        "descriptor_z_scores": z_scores,
        "maximum_absolute_descriptor_z": round(float(max_abs_z), 6),
        "valid_reference_compounds": len(reference_molecules),
        "invalid_reference_smiles": invalid,
        "warning": None if inside else "Query is distant from the supplied reference chemical space; screening confidence should be reduced.",
    }


def bbb_reference_validation(
    reference_frame: pd.DataFrame,
    *,
    smiles_column: str = "smiles",
    label_column: str = "bbb_label",
    id_column: str | None = None,
) -> dict[str, Any]:
    """Evaluate the transparent BBB screen against user-supplied measured labels."""
    if reference_frame.empty:
        raise ValueError("BBB reference table is empty.")
    if smiles_column not in reference_frame.columns or label_column not in reference_frame.columns:
        raise ValueError("Reference table requires SMILES and measured-label columns.")
    positive_tokens = {"1", "true", "yes", "positive", "permeable", "bbb+", "high"}
    negative_tokens = {"0", "false", "no", "negative", "impermeable", "non-permeable", "bbb-", "low"}
    rows: list[dict[str, Any]] = []
    for index, row in reference_frame.iterrows():
        compound_id = str(row.get(id_column) if id_column and id_column in row else f"compound_{index + 1}")
        raw_label = row.get(label_column)
        label_text = "" if pd.isna(raw_label) else str(raw_label).strip().lower()
        measured = 1 if label_text in positive_tokens else 0 if label_text in negative_tokens else None
        try:
            result = bbb_permeability(str(row.get(smiles_column) or ""), compound_id)
            predicted = 1 if result["classification"] == "likely_permeable" else 0
            rows.append({
                "compound_id": compound_id,
                "smiles": row.get(smiles_column),
                "measured_label": measured,
                "measured_label_raw": row.get(label_column),
                "predicted_label": predicted,
                "classification": result["classification"],
                "probability_proxy": result["local_probability_proxy"],
                "inside_local_domain": result["applicability_domain"]["inside"],
                "murcko_scaffold": MurckoScaffold.MurckoScaffoldSmiles(mol=parse_smiles(str(row.get(smiles_column) or ""))),
                "error": None,
            })
        except Exception as exc:
            rows.append({
                "compound_id": compound_id,
                "smiles": row.get(smiles_column),
                "measured_label": measured,
                "measured_label_raw": row.get(label_column),
                "predicted_label": None,
                "classification": "error",
                "probability_proxy": None,
                "inside_local_domain": False,
                "murcko_scaffold": None,
                "error": str(exc),
            })
    evaluated = pd.DataFrame(rows)
    valid = evaluated.dropna(subset=["measured_label", "predicted_label", "probability_proxy"]).copy()
    metrics: dict[str, Any] = {
        "input_rows": len(reference_frame),
        "evaluated_rows": len(valid),
        "invalid_or_unmapped_rows": int(len(evaluated) - len(valid)),
        "unique_scaffolds": int(valid["murcko_scaffold"].replace("", np.nan).nunique(dropna=True)) if not valid.empty else 0,
        "inside_domain_fraction": round(float(valid["inside_local_domain"].mean()), 6) if not valid.empty else None,
    }
    calibration = pd.DataFrame()
    if not valid.empty and valid["measured_label"].nunique() == 2:
        actual = valid["measured_label"].astype(int).to_numpy()
        predicted = valid["predicted_label"].astype(int).to_numpy()
        tp = int(((actual == 1) & (predicted == 1)).sum())
        tn = int(((actual == 0) & (predicted == 0)).sum())
        fp = int(((actual == 0) & (predicted == 1)).sum())
        fn = int(((actual == 1) & (predicted == 0)).sum())
        sensitivity = tp / max(tp + fn, 1)
        specificity = tn / max(tn + fp, 1)
        precision = tp / max(tp + fp, 1)
        metrics.update({
            "true_positive": tp, "true_negative": tn, "false_positive": fp, "false_negative": fn,
            "sensitivity": round(sensitivity, 6),
            "specificity": round(specificity, 6),
            "precision": round(precision, 6),
            "balanced_accuracy": round((sensitivity + specificity) / 2.0, 6),
            "brier_score": round(float(np.mean((valid["probability_proxy"].to_numpy(float) - actual) ** 2)), 6),
        })
        calibration_source = valid[["measured_label", "probability_proxy"]].copy()
        try:
            calibration_source["probability_bin"] = pd.qcut(calibration_source["probability_proxy"], q=min(5, max(2, len(calibration_source) // 3)), duplicates="drop")
            calibration = calibration_source.groupby("probability_bin", observed=True).agg(
                sample_count=("measured_label", "size"),
                mean_probability_proxy=("probability_proxy", "mean"),
                observed_permeable_fraction=("measured_label", "mean"),
            ).reset_index()
            calibration["probability_bin"] = calibration["probability_bin"].astype(str)
        except ValueError:
            calibration = pd.DataFrame()
    warnings: list[str] = []
    if len(valid) < 30:
        warnings.append("Reference set is small; performance estimates are unstable.")
    if metrics.get("unique_scaffolds", 0) < 5:
        warnings.append("Low scaffold diversity; random-row performance can overstate generalization.")
    if metrics.get("inside_domain_fraction") is not None and metrics["inside_domain_fraction"] < 0.80:
        warnings.append("A substantial fraction of the reference set is outside local descriptor-domain checks.")
    return {
        "evaluated_compounds": evaluated,
        "validation_metrics": metrics,
        "calibration_table": calibration,
        "warnings": warnings,
        "scientific_boundary": "Internal evaluation against user-supplied labels only; no external calibration, regulatory validation or experimental replacement is claimed.",
    }


def simulate_brain_exposure_population(
    parameters: dict[str, Any],
    *,
    coefficient_of_variation: dict[str, float] | None = None,
    simulations: int = 100,
    random_state: int = 42,
) -> dict[str, Any]:
    """Propagate user-declared PK uncertainty through repeated exposure simulations."""
    required = {
        "initial_plasma_concentration", "half_life_hours", "duration_hours",
        "passive_permeability_factor", "efflux_ratio", "fraction_unbound_plasma", "fraction_unbound_brain",
    }
    missing = sorted(required - set(parameters))
    if missing:
        raise ValueError("Missing PK parameters: " + ", ".join(missing))
    count = max(10, min(int(simulations), 1000))
    cv = dict(coefficient_of_variation or {})
    rng = np.random.default_rng(random_state)
    curves: list[pd.DataFrame] = []
    summaries: list[dict[str, Any]] = []
    positive_parameters = {"initial_plasma_concentration", "half_life_hours", "passive_permeability_factor", "fraction_unbound_plasma", "fraction_unbound_brain", "dosing_interval_hours", "brain_equilibration_half_life_hours", "absorption_half_life_hours"}
    for iteration in range(count):
        sampled = dict(parameters)
        for name, variation in cv.items():
            if name not in sampled or sampled[name] is None:
                continue
            variation = max(0.0, float(variation))
            base = float(sampled[name])
            if variation == 0:
                continue
            if name in positive_parameters and base > 0:
                sigma = math.sqrt(math.log(1.0 + variation ** 2))
                sampled[name] = float(base * math.exp(rng.normal(-0.5 * sigma ** 2, sigma)))
            else:
                sampled[name] = float(rng.normal(base, abs(base) * variation))
        sampled["fraction_unbound_plasma"] = _clip(float(sampled["fraction_unbound_plasma"]), 0.001, 1.0)
        sampled["fraction_unbound_brain"] = _clip(float(sampled["fraction_unbound_brain"]), 0.001, 1.0)
        sampled["efflux_ratio"] = max(0.0, float(sampled["efflux_ratio"]))
        result = simulate_brain_exposure(**sampled)
        curve = result["curve"].copy()
        curve["simulation"] = iteration + 1
        curves.append(curve)
        summaries.append({
            "simulation": iteration + 1,
            "peak_brain_unbound": result["peak_brain_unbound"],
            "time_to_peak_brain_hours": result["time_to_peak_brain_hours"],
            "kp_uu_brain": result["kp_uu_brain"],
            "brain_unbound_auc": result["brain_unbound_auc"],
            "time_above_effective_threshold_hours": result["time_above_effective_threshold_hours"],
        })
    all_curves = pd.concat(curves, ignore_index=True)
    percentile_rows: list[dict[str, Any]] = []
    for time, group in all_curves.groupby("time_hours"):
        row: dict[str, Any] = {"time_hours": float(time)}
        for column in ("plasma_total", "plasma_unbound", "brain_total", "brain_unbound"):
            values = group[column].to_numpy(float)
            row[f"{column}_p05"] = float(np.percentile(values, 5))
            row[f"{column}_p50"] = float(np.percentile(values, 50))
            row[f"{column}_p95"] = float(np.percentile(values, 95))
        percentile_rows.append(row)
    return {
        "percentile_curve": pd.DataFrame(percentile_rows),
        "simulation_summary": pd.DataFrame(summaries),
        "simulations": count,
        "coefficient_of_variation": cv,
        "scientific_boundary": "User-parameter uncertainty propagation only; not population PK fitting or validated PBPK simulation.",
    }


def receptor_occupancy_kinetics(
    exposure_curve: pd.DataFrame,
    affinity_rows: Iterable[dict[str, Any]],
    *,
    time_column: str = "time_hours",
    concentration_column: str = "brain_unbound",
    concentration_unit: str = "nM",
    default_affinity_unit: str = "nM",
) -> dict[str, Any]:
    """Calculate equilibrium or kon/koff occupancy over an exposure curve."""
    if time_column not in exposure_curve.columns or concentration_column not in exposure_curve.columns:
        raise ValueError("Exposure curve requires time and concentration columns.")
    curve = exposure_curve[[time_column, concentration_column]].copy()
    curve[time_column] = pd.to_numeric(curve[time_column], errors="coerce")
    curve[concentration_column] = pd.to_numeric(curve[concentration_column], errors="coerce")
    curve = curve.dropna().sort_values(time_column).reset_index(drop=True)
    if len(curve) < 2:
        raise ValueError("At least two exposure time points are required.")
    concentration_nm = curve[concentration_column].map(lambda value: concentration_to_nm(float(value), concentration_unit)).to_numpy(float)
    source_rows = list(affinity_rows)
    normalized = normalize_affinity_rows(source_rows, default_unit=default_affinity_unit)
    time_values = curve[time_column].to_numpy(float)
    rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    for index, normalized_row in enumerate(normalized):
        source = source_rows[index] if index < len(source_rows) else {}
        target = str(normalized_row.get("target") or f"target_{index + 1}")
        affinity_nm = float(normalized_row.get("affinity_nm", np.nan))
        if not math.isfinite(affinity_nm) or affinity_nm <= 0:
            continue
        competitor_concentration = max(0.0, float(source.get("competitor_concentration", 0.0) or 0.0))
        competitor_kd = float(source.get("competitor_kd", np.nan) or np.nan)
        effective_affinity = affinity_nm * (1.0 + competitor_concentration / competitor_kd) if math.isfinite(competitor_kd) and competitor_kd > 0 else affinity_nm
        kon = source.get("kon_per_nm_hour", source.get("kon"))
        koff = source.get("koff_per_hour", source.get("koff"))
        kinetic = False
        occupancy = np.zeros(len(curve), dtype=float)
        try:
            kon_value = float(kon)
            koff_value = float(koff)
            kinetic = math.isfinite(kon_value) and math.isfinite(koff_value) and kon_value > 0 and koff_value >= 0
        except (TypeError, ValueError):
            kinetic = False
        if kinetic:
            occupancy[0] = concentration_nm[0] / (concentration_nm[0] + effective_affinity)
            for point in range(1, len(curve)):
                dt = max(0.0, time_values[point] - time_values[point - 1])
                derivative = kon_value * concentration_nm[point - 1] * (1.0 - occupancy[point - 1]) - koff_value * occupancy[point - 1]
                occupancy[point] = _clip(occupancy[point - 1] + dt * derivative, 0.0, 1.0)
        else:
            occupancy = concentration_nm / (concentration_nm + effective_affinity)
        for time, concentration, value in zip(time_values, concentration_nm, occupancy):
            rows.append({
                "target": target,
                "time_hours": float(time),
                "free_brain_concentration_nm": float(concentration),
                "occupancy_percent": round(float(value * 100.0), 6),
                "method": "kinetic_kon_koff" if kinetic else "equilibrium",
                "effective_affinity_nm": round(float(effective_affinity), 6),
                "role": source.get("role", "unspecified"),
            })
        summary_rows.append({
            "target": target,
            "peak_occupancy_percent": round(float(occupancy.max() * 100.0), 6),
            "time_to_peak_hours": round(float(time_values[int(np.argmax(occupancy))]), 6),
            "occupancy_auc_percent_hours": round(float(np.trapezoid(occupancy * 100.0, time_values)), 6),
            "method": "kinetic_kon_koff" if kinetic else "equilibrium",
            "competitor_adjusted": bool(effective_affinity != affinity_nm),
            "role": source.get("role", "unspecified"),
        })
    return {
        "occupancy_curve": pd.DataFrame(rows),
        "target_summary": pd.DataFrame(summary_rows),
        "scientific_boundary": "Research target-engagement simulation using supplied exposure and affinity/kinetic parameters; active metabolites and tissue heterogeneity require explicit user inputs and external validation.",
    }


def cns_drug_adme_workflow(
    smiles: str,
    *,
    reference_frame: pd.DataFrame | None = None,
    reference_smiles_column: str = "smiles",
) -> dict[str, Any]:
    """Combine transparent BBB, drug-likeness, transporter and CSF screens."""
    bbb = bbb_permeability(smiles)
    drug_likeness = cns_drug_likeness(smiles)
    adme = cns_adme_transporters(smiles)
    csf = blood_csf_barrier(smiles)
    reference_space = None
    if reference_frame is not None and not reference_frame.empty:
        if reference_smiles_column not in reference_frame.columns:
            raise ValueError("Reference chemical-space table is missing the selected SMILES column.")
        reference_space = chemical_space_applicability(smiles, reference_frame[reference_smiles_column].dropna().astype(str))
    warnings = list(dict.fromkeys([
        *bbb.get("warnings", []),
        *drug_likeness.get("warnings", []),
        *adme.get("liabilities", []),
        *([reference_space["warning"]] if reference_space and reference_space.get("warning") else []),
        "Ionization/pKa and measured logD are not inferred by this deterministic local workflow.",
    ]))
    return {
        "bbb_screen": bbb,
        "cns_drug_likeness": drug_likeness,
        "adme_transporter_screen": adme,
        "blood_csf_screen": csf,
        "reference_chemical_space": reference_space,
        "warnings": warnings,
        "scientific_boundary": "Integrated descriptor/proxy screening only; experimental permeability, transporter, metabolism, pKa/logD and external validation remain required.",
    }
