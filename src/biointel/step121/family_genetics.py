from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from math import log10
from typing import Any, Iterable

import numpy as np
import pandas as pd

PED_COLUMNS = ("family_id", "individual_id", "father_id", "mother_id", "sex", "phenotype")
VARIANT_COLUMNS = ("variant_id", "sample_id", "genotype")
_MISSING_PARENT = {"", "0", "-9", "nan", "none", "na"}


@dataclass(frozen=True)
class PedigreeIssue:
    severity: str
    code: str
    individual_id: str
    detail: str


@dataclass(frozen=True)
class FamilyAnalysisResult:
    pedigree_qc: pd.DataFrame
    trio_qc: pd.DataFrame
    inheritance: pd.DataFrame
    de_novo_candidates: pd.DataFrame
    compound_heterozygous: pd.DataFrame
    kinship: pd.DataFrame
    segregation: pd.DataFrame
    release_gate: dict[str, Any]
    manifest: dict[str, Any]


def _clean_id(value: Any) -> str:
    text = str(value).strip()
    return "0" if text.lower() in _MISSING_PARENT else text


def normalize_genotype(value: Any) -> tuple[int, ...] | None:
    """Return sorted biallelic genotype alleles, or None for missing/unusable calls."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    text = str(value).strip().split(":", 1)[0]
    if text in {"", ".", "./.", ".|.", "NA", "nan", "None"}:
        return None
    separator = "/" if "/" in text else "|" if "|" in text else None
    if separator is None:
        try:
            allele = int(text)
        except ValueError:
            return None
        return (allele, allele)
    parts = text.split(separator)
    if len(parts) != 2 or any(part == "." for part in parts):
        return None
    try:
        alleles = tuple(sorted(int(part) for part in parts))
    except ValueError:
        return None
    if any(allele < 0 for allele in alleles):
        return None
    return alleles


def genotype_dosage(value: Any) -> float:
    genotype = normalize_genotype(value)
    if genotype is None:
        return np.nan
    return float(sum(allele > 0 for allele in genotype))


def _coerce_pedigree(pedigree: pd.DataFrame) -> pd.DataFrame:
    lookup = {str(column).strip().lower(): column for column in pedigree.columns}
    aliases = {
        "fid": "family_id",
        "family": "family_id",
        "iid": "individual_id",
        "sample_id": "individual_id",
        "sample": "individual_id",
        "pid": "father_id",
        "father": "father_id",
        "mid": "mother_id",
        "mother": "mother_id",
        "affected": "phenotype",
    }
    renamed: dict[Any, str] = {}
    for normalized, original in lookup.items():
        target = aliases.get(normalized, normalized)
        if target in PED_COLUMNS:
            renamed[original] = target
    frame = pedigree.rename(columns=renamed).copy()
    for column in PED_COLUMNS:
        if column not in frame.columns:
            if column in {"father_id", "mother_id"}:
                frame[column] = "0"
            elif column == "family_id":
                frame[column] = "FAMILY_1"
            else:
                frame[column] = np.nan
    frame = frame[list(PED_COLUMNS)].copy()
    for column in ("family_id", "individual_id", "father_id", "mother_id"):
        frame[column] = frame[column].map(_clean_id)
    frame["sex"] = pd.to_numeric(frame["sex"], errors="coerce").fillna(0).astype(int)
    frame["phenotype"] = pd.to_numeric(frame["phenotype"], errors="coerce").fillna(0).astype(int)
    return frame


def validate_pedigree(pedigree: pd.DataFrame) -> pd.DataFrame:
    frame = _coerce_pedigree(pedigree)
    issues: list[PedigreeIssue] = []
    if frame["individual_id"].eq("0").any():
        for sample in frame.loc[frame["individual_id"].eq("0"), "individual_id"]:
            issues.append(PedigreeIssue("error", "missing_individual_id", sample, "Individual ID is missing."))
    duplicates = frame[frame["individual_id"].duplicated(keep=False)]
    for sample in sorted(duplicates["individual_id"].unique()):
        issues.append(PedigreeIssue("error", "duplicate_individual", sample, "Individual appears more than once."))

    ids = set(frame["individual_id"])
    by_id = frame.drop_duplicates("individual_id").set_index("individual_id")
    for row in frame.itertuples(index=False):
        for role, parent_id, expected_sex in (("father", row.father_id, 1), ("mother", row.mother_id, 2)):
            if parent_id == "0":
                continue
            if parent_id not in ids:
                issues.append(PedigreeIssue("warning", f"missing_{role}", row.individual_id, f"{role.title()} {parent_id} is not in the pedigree."))
                continue
            parent = by_id.loc[parent_id]
            if int(parent["sex"]) not in {0, expected_sex}:
                issues.append(PedigreeIssue("warning", f"{role}_sex_conflict", row.individual_id, f"{role.title()} {parent_id} has incompatible sex code."))
            if str(parent["family_id"]) != str(row.family_id):
                issues.append(PedigreeIssue("error", "cross_family_parent", row.individual_id, f"Parent {parent_id} belongs to another family."))
        if row.individual_id in {row.father_id, row.mother_id}:
            issues.append(PedigreeIssue("error", "self_parent", row.individual_id, "Individual cannot be their own parent."))

    parent_map = {
        row.individual_id: [parent for parent in (row.father_id, row.mother_id) if parent != "0"]
        for row in frame.itertuples(index=False)
    }
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str, trail: tuple[str, ...]) -> None:
        if node in visiting:
            cycle = " -> ".join((*trail, node))
            issues.append(PedigreeIssue("error", "pedigree_cycle", node, f"Ancestry cycle detected: {cycle}"))
            return
        if node in visited:
            return
        visiting.add(node)
        for parent in parent_map.get(node, []):
            if parent in parent_map:
                visit(parent, (*trail, node))
        visiting.discard(node)
        visited.add(node)

    for individual in parent_map:
        visit(individual, ())

    if not issues:
        issues.append(PedigreeIssue("pass", "pedigree_valid", "", "No structural pedigree issues detected."))
    return pd.DataFrame(asdict(issue) for issue in issues)


def mendelian_consistent(child: Any, father: Any, mother: Any) -> bool | None:
    child_gt = normalize_genotype(child)
    father_gt = normalize_genotype(father)
    mother_gt = normalize_genotype(mother)
    if child_gt is None or father_gt is None or mother_gt is None:
        return None
    possible = {tuple(sorted((fa, mo))) for fa in father_gt for mo in mother_gt}
    return child_gt in possible


def _coerce_variants(variants: pd.DataFrame) -> pd.DataFrame:
    lookup = {str(column).strip().lower(): column for column in variants.columns}
    aliases = {
        "variant": "variant_id",
        "id": "variant_id",
        "sample": "sample_id",
        "iid": "sample_id",
        "gt": "genotype",
        "gene_symbol": "gene",
        "symbol": "gene",
        "dp": "depth",
        "ad": "allele_depth",
        "vaf": "alt_fraction",
        "af": "population_af",
    }
    renamed: dict[Any, str] = {}
    for normalized, original in lookup.items():
        renamed[original] = aliases.get(normalized, normalized)
    frame = variants.rename(columns=renamed).copy()
    missing = [column for column in VARIANT_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError("Variant table missing required columns: " + ", ".join(missing))
    frame["variant_id"] = frame["variant_id"].astype(str).str.strip()
    frame["sample_id"] = frame["sample_id"].astype(str).str.strip()
    frame["genotype"] = frame["genotype"].astype(str).str.strip()
    frame["dosage"] = frame["genotype"].map(genotype_dosage)
    for column in ("depth", "allele_depth", "alt_fraction", "population_af"):
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if "gene" not in frame.columns:
        frame["gene"] = ""
    return frame


def _inheritance_label(child_gt: Any, father_gt: Any, mother_gt: Any) -> str:
    child = normalize_genotype(child_gt)
    father = normalize_genotype(father_gt)
    mother = normalize_genotype(mother_gt)
    if child is None or father is None or mother is None:
        return "insufficient_calls"
    child_alt = sum(a > 0 for a in child)
    father_alt = sum(a > 0 for a in father)
    mother_alt = sum(a > 0 for a in mother)
    consistent = mendelian_consistent(child, father, mother)
    if consistent is False:
        return "mendelian_error"
    if child_alt > 0 and father_alt == 0 and mother_alt == 0:
        return "de_novo_candidate"
    if child_alt == 2 and father_alt > 0 and mother_alt > 0:
        return "recessive_inherited"
    if child_alt > 0 and father_alt > 0 and mother_alt == 0:
        return "paternal_inherited"
    if child_alt > 0 and mother_alt > 0 and father_alt == 0:
        return "maternal_inherited"
    if child_alt > 0 and father_alt > 0 and mother_alt > 0:
        return "both_parents_carry"
    return "reference_or_uninformative"


def _trio_rows(pedigree: pd.DataFrame, variants: pd.DataFrame) -> pd.DataFrame:
    ped = _coerce_pedigree(pedigree)
    trios = ped[(ped["father_id"] != "0") & (ped["mother_id"] != "0")].copy()
    if trios.empty:
        return pd.DataFrame()
    pivot = variants.pivot_table(index="variant_id", columns="sample_id", values="genotype", aggfunc="first")
    annotations = variants.drop_duplicates("variant_id").set_index("variant_id")
    rows: list[dict[str, Any]] = []
    for trio in trios.itertuples(index=False):
        for variant_id, calls in pivot.iterrows():
            if not {trio.individual_id, trio.father_id, trio.mother_id}.issubset(calls.index):
                continue
            child_gt = calls.get(trio.individual_id)
            father_gt = calls.get(trio.father_id)
            mother_gt = calls.get(trio.mother_id)
            consistency = mendelian_consistent(child_gt, father_gt, mother_gt)
            base = {
                "family_id": trio.family_id,
                "child_id": trio.individual_id,
                "father_id": trio.father_id,
                "mother_id": trio.mother_id,
                "variant_id": variant_id,
                "child_gt": child_gt,
                "father_gt": father_gt,
                "mother_gt": mother_gt,
                "mendelian_consistent": consistency,
                "inheritance": _inheritance_label(child_gt, father_gt, mother_gt),
            }
            if variant_id in annotations.index:
                for column in ("gene", "chrom", "position", "consequence", "population_af"):
                    if column in annotations.columns:
                        base[column] = annotations.at[variant_id, column]
            child_rows = variants[(variants["variant_id"] == variant_id) & (variants["sample_id"] == trio.individual_id)]
            if not child_rows.empty:
                for column in ("depth", "allele_depth", "alt_fraction"):
                    if column in child_rows.columns:
                        base[f"child_{column}"] = child_rows.iloc[0][column]
            rows.append(base)
    return pd.DataFrame(rows)


def _kinship_table(variants: pd.DataFrame, pedigree: pd.DataFrame) -> pd.DataFrame:
    matrix = variants.pivot_table(index="variant_id", columns="sample_id", values="dosage", aggfunc="first")
    samples = list(matrix.columns)
    ped = _coerce_pedigree(pedigree).set_index("individual_id")
    rows: list[dict[str, Any]] = []
    for index, sample_a in enumerate(samples):
        for sample_b in samples[index + 1 :]:
            pair = matrix[[sample_a, sample_b]].dropna()
            if pair.empty:
                continue
            a = pair[sample_a].to_numpy(float)
            b = pair[sample_b].to_numpy(float)
            concordance = float(np.mean(a == b))
            ibs0 = float(np.mean(((a == 0) & (b == 2)) | ((a == 2) & (b == 0))))
            centered_a = a - np.mean(a)
            centered_b = b - np.mean(b)
            denom = float(np.sqrt(np.sum(centered_a**2) * np.sum(centered_b**2)))
            correlation = float(np.sum(centered_a * centered_b) / denom) if denom else np.nan
            expected = "unrelated_or_unknown"
            if sample_a in ped.index and sample_b in ped.index:
                row_a, row_b = ped.loc[sample_a], ped.loc[sample_b]
                if sample_b in {row_a.father_id, row_a.mother_id} or sample_a in {row_b.father_id, row_b.mother_id}:
                    expected = "parent_child"
                elif (
                    row_a.father_id != "0"
                    and row_a.father_id == row_b.father_id
                    and row_a.mother_id != "0"
                    and row_a.mother_id == row_b.mother_id
                ):
                    expected = "full_siblings"
            mismatch = False
            if expected == "parent_child" and ibs0 > 0.02:
                mismatch = True
            if expected == "full_siblings" and concordance < 0.45:
                mismatch = True
            rows.append(
                {
                    "sample_a": sample_a,
                    "sample_b": sample_b,
                    "variants_compared": len(pair),
                    "genotype_concordance": concordance,
                    "ibs0_rate": ibs0,
                    "dosage_correlation": correlation,
                    "expected_relationship": expected,
                    "relationship_flag": mismatch,
                }
            )
    return pd.DataFrame(rows)


def _compound_hets(trio_rows: pd.DataFrame) -> pd.DataFrame:
    if trio_rows.empty or "gene" not in trio_rows.columns:
        return pd.DataFrame()
    inherited = trio_rows[trio_rows["inheritance"].isin(["maternal_inherited", "paternal_inherited"])].copy()
    rows: list[dict[str, Any]] = []
    for (family_id, child_id, gene), group in inherited.groupby(["family_id", "child_id", "gene"], dropna=False):
        maternal = group[group["inheritance"] == "maternal_inherited"]
        paternal = group[group["inheritance"] == "paternal_inherited"]
        if maternal.empty or paternal.empty or not str(gene).strip():
            continue
        for maternal_variant in maternal.itertuples(index=False):
            for paternal_variant in paternal.itertuples(index=False):
                rows.append(
                    {
                        "family_id": family_id,
                        "child_id": child_id,
                        "gene": gene,
                        "maternal_variant": maternal_variant.variant_id,
                        "paternal_variant": paternal_variant.variant_id,
                        "phase_status": "trans_candidate_unphased",
                        "requires_read_backed_phasing": True,
                    }
                )
    return pd.DataFrame(rows)


def _segregation_lod(variants: pd.DataFrame, pedigree: pd.DataFrame) -> pd.DataFrame:
    ped = _coerce_pedigree(pedigree)
    merged = variants.merge(
        ped[["family_id", "individual_id", "phenotype"]],
        left_on="sample_id",
        right_on="individual_id",
        how="inner",
    )
    rows: list[dict[str, Any]] = []
    penetrance = 0.90
    phenocopy = 0.02
    null_prevalence = 0.10
    for (family_id, variant_id), group in merged.groupby(["family_id", "variant_id"]):
        informative = group[group["phenotype"].isin([1, 2]) & group["dosage"].notna()].copy()
        if len(informative) < 3:
            continue
        log_alt = 0.0
        log_null = 0.0
        for row in informative.itertuples(index=False):
            affected = int(row.phenotype) == 2
            carrier = float(row.dosage) > 0
            probability_alt = penetrance if carrier and affected else (1 - penetrance if carrier else phenocopy) if affected else (1 - phenocopy)
            if not affected:
                probability_alt = (1 - penetrance) if carrier else (1 - phenocopy)
            probability_null = null_prevalence if affected else (1 - null_prevalence)
            log_alt += log10(max(probability_alt, 1e-12))
            log_null += log10(max(probability_null, 1e-12))
        rows.append(
            {
                "family_id": family_id,
                "variant_id": variant_id,
                "informative_members": len(informative),
                "lod_proxy": log_alt - log_null,
                "model": "dominant_penetrance_0.90_phenocopy_0.02",
                "interpretation": "supportive" if log_alt - log_null >= 1 else "weak_or_opposing",
            }
        )
    return pd.DataFrame(rows).sort_values("lod_proxy", ascending=False) if rows else pd.DataFrame()


def analyse_family_variants(
    pedigree: pd.DataFrame,
    variants: pd.DataFrame,
    *,
    min_child_depth: float = 10.0,
    min_child_alt_fraction: float = 0.20,
    max_population_af: float = 0.01,
) -> FamilyAnalysisResult:
    ped = _coerce_pedigree(pedigree)
    var = _coerce_variants(variants)
    pedigree_qc = validate_pedigree(ped)
    trio_rows = _trio_rows(ped, var)
    if trio_rows.empty:
        trio_qc = pd.DataFrame(
            [{"metric": "informative_trios", "value": 0}, {"metric": "mendelian_error_rate", "value": np.nan}]
        )
    else:
        callable_rows = trio_rows[trio_rows["mendelian_consistent"].notna()]
        error_rate = float((callable_rows["mendelian_consistent"] == False).mean()) if not callable_rows.empty else np.nan  # noqa: E712
        trio_qc = pd.DataFrame(
            [
                {"metric": "informative_trios", "value": trio_rows["child_id"].nunique()},
                {"metric": "variant_trio_observations", "value": len(trio_rows)},
                {"metric": "mendelian_error_rate", "value": error_rate},
                {"metric": "de_novo_candidates_raw", "value": int((trio_rows["inheritance"] == "de_novo_candidate").sum())},
            ]
        )

    de_novo = trio_rows[trio_rows.get("inheritance", pd.Series(dtype=str)) == "de_novo_candidate"].copy()
    if not de_novo.empty:
        if "child_depth" in de_novo.columns:
            de_novo = de_novo[de_novo["child_depth"].fillna(0) >= min_child_depth]
        if "child_alt_fraction" in de_novo.columns:
            de_novo = de_novo[de_novo["child_alt_fraction"].fillna(0) >= min_child_alt_fraction]
        if "population_af" in de_novo.columns:
            de_novo = de_novo[de_novo["population_af"].fillna(0) <= max_population_af]
        de_novo["status"] = "candidate_requires_read_review_and_orthogonal_confirmation"

    compound = _compound_hets(trio_rows)
    kinship = _kinship_table(var, ped)
    segregation = _segregation_lod(var, ped)
    error_count = int((pedigree_qc["severity"] == "error").sum()) if not pedigree_qc.empty else 0
    relationship_flags = int(kinship["relationship_flag"].sum()) if not kinship.empty else 0
    mendelian_errors = int((trio_rows.get("mendelian_consistent", pd.Series(dtype=object)) == False).sum()) if not trio_rows.empty else 0  # noqa: E712
    blockers: list[str] = []
    if error_count:
        blockers.append(f"{error_count} pedigree structure error(s)")
    if relationship_flags:
        blockers.append(f"{relationship_flags} relationship/identity flag(s)")
    if mendelian_errors:
        blockers.append(f"{mendelian_errors} Mendelian inconsistency observation(s)")
    blockers.extend(
        [
            "Read-backed phasing not attached",
            "Clinical variant classification and independent review not attached",
            "Candidate de-novo/mosaic calls require read-level and orthogonal confirmation",
        ]
    )
    release_gate = {
        "research_workflow_ready": error_count == 0,
        "diagnostic_release_ready": False,
        "blockers": blockers,
        "boundary": "Family-genetics prioritisation is research support and is not a diagnostic conclusion.",
    }
    digest_source = pd.util.hash_pandas_object(var.astype("string").fillna(""), index=True).values.tobytes() + pd.util.hash_pandas_object(ped.astype("string").fillna(""), index=True).values.tobytes()
    manifest = {
        "schema": "biointel.step121.family_genetics.v1",
        "pedigree_rows": len(ped),
        "variant_rows": len(var),
        "families": int(ped["family_id"].nunique()),
        "samples": int(ped["individual_id"].nunique()),
        "variants": int(var["variant_id"].nunique()),
        "parameters": {
            "min_child_depth": min_child_depth,
            "min_child_alt_fraction": min_child_alt_fraction,
            "max_population_af": max_population_af,
        },
        "input_sha256": sha256(digest_source).hexdigest(),
        "diagnostic_release_ready": False,
    }
    return FamilyAnalysisResult(
        pedigree_qc=pedigree_qc,
        trio_qc=trio_qc,
        inheritance=trio_rows,
        de_novo_candidates=de_novo,
        compound_heterozygous=compound,
        kinship=kinship,
        segregation=segregation,
        release_gate=release_gate,
        manifest=manifest,
    )
