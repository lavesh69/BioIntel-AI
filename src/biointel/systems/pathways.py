from __future__ import annotations

from collections import defaultdict, deque
from math import comb, erf, sqrt
from random import Random
from typing import Iterable

import numpy as np
import pandas as pd

PATHWAY_PACK_VERSION = "2026.07-local-reviewed-v1"

# Compact, versioned offline packs. They are intentionally curated for robust local use;
# users can replace/extend them with GMT files through ``parse_gmt``.
HUMAN_PATHWAYS: dict[str, set[str]] = {
    "DNA repair": {
        "BRCA1",
        "BRCA2",
        "ATM",
        "ATR",
        "RAD51",
        "CHEK1",
        "CHEK2",
        "TP53",
        "PALB2",
        "MRE11",
        "NBN",
        "XRCC1",
    },
    "Homologous recombination": {
        "BRCA1",
        "BRCA2",
        "RAD51",
        "PALB2",
        "BARD1",
        "RAD50",
        "MRE11",
        "NBN",
        "RPA1",
    },
    "Mismatch repair": {"MLH1", "MSH2", "MSH6", "PMS2", "MSH3", "EXO1"},
    "Nucleotide excision repair": {
        "XPA",
        "XPC",
        "ERCC1",
        "ERCC2",
        "ERCC3",
        "ERCC4",
        "ERCC5",
        "DDB1",
        "DDB2",
    },
    "PI3K-AKT signalling": {
        "PIK3CA",
        "PIK3CB",
        "PIK3CD",
        "AKT1",
        "AKT2",
        "AKT3",
        "PTEN",
        "MTOR",
        "TSC1",
        "TSC2",
        "RHEB",
    },
    "MAPK signalling": {
        "KRAS",
        "NRAS",
        "HRAS",
        "BRAF",
        "RAF1",
        "MAP2K1",
        "MAP2K2",
        "MAPK1",
        "MAPK3",
        "DUSP6",
    },
    "JAK-STAT signalling": {
        "JAK1",
        "JAK2",
        "JAK3",
        "TYK2",
        "STAT1",
        "STAT2",
        "STAT3",
        "STAT5A",
        "STAT5B",
        "SOCS1",
        "SOCS3",
    },
    "NF-kappa B signalling": {
        "NFKB1",
        "NFKB2",
        "RELA",
        "RELB",
        "IKBKB",
        "IKBKG",
        "CHUK",
        "TNF",
        "TRAF2",
    },
    "Apoptosis": {
        "TP53",
        "BAX",
        "BAK1",
        "BCL2",
        "BCL2L1",
        "MCL1",
        "CASP3",
        "CASP8",
        "CASP9",
        "APAF1",
        "FAS",
    },
    "Cell cycle": {
        "CDK1",
        "CDK2",
        "CDK4",
        "CDK6",
        "CCND1",
        "CCNE1",
        "CCNA2",
        "RB1",
        "TP53",
        "E2F1",
        "CDC25A",
    },
    "p53 signalling": {"TP53", "MDM2", "CDKN1A", "BAX", "PUMA", "BBC3", "GADD45A", "CHEK2", "ATM"},
    "TGF-beta signalling": {
        "TGFB1",
        "TGFBR1",
        "TGFBR2",
        "SMAD2",
        "SMAD3",
        "SMAD4",
        "SMAD7",
        "BMP2",
        "BMP4",
    },
    "WNT signalling": {
        "WNT1",
        "WNT3A",
        "FZD1",
        "LRP5",
        "LRP6",
        "CTNNB1",
        "APC",
        "GSK3B",
        "AXIN1",
        "TCF7L2",
    },
    "Notch signalling": {
        "NOTCH1",
        "NOTCH2",
        "JAG1",
        "JAG2",
        "DLL1",
        "DLL4",
        "RBPJ",
        "HES1",
        "MAML1",
    },
    "Hedgehog signalling": {"SHH", "IHH", "PTCH1", "SMO", "SUFU", "GLI1", "GLI2", "GLI3"},
    "Hypoxia response": {"HIF1A", "EPAS1", "VHL", "EGLN1", "VEGFA", "SLC2A1", "LDHA", "CA9"},
    "Oxidative stress": {
        "NFE2L2",
        "KEAP1",
        "SOD1",
        "SOD2",
        "CAT",
        "GPX1",
        "GCLC",
        "GCLM",
        "HMOX1",
        "NQO1",
    },
    "Glycolysis": {"HK1", "HK2", "GPI", "PFKM", "ALDOA", "GAPDH", "PGK1", "ENO1", "PKM", "LDHA"},
    "TCA cycle": {"CS", "ACO2", "IDH2", "OGDH", "DLST", "SUCLG1", "SDHA", "FH", "MDH2"},
    "Fatty acid oxidation": {
        "CPT1A",
        "CPT2",
        "ACADM",
        "ACADL",
        "HADHA",
        "HADHB",
        "ECHS1",
        "ACOX1",
        "PPARA",
    },
    "mTOR signalling": {
        "MTOR",
        "RPTOR",
        "RICTOR",
        "AKT1",
        "TSC1",
        "TSC2",
        "RHEB",
        "RPS6KB1",
        "EIF4EBP1",
    },
    "Autophagy": {
        "ULK1",
        "BECN1",
        "ATG5",
        "ATG7",
        "ATG12",
        "ATG16L1",
        "MAP1LC3B",
        "SQSTM1",
        "LAMP1",
    },
    "Interferon response": {
        "IFNA1",
        "IFNB1",
        "IFNG",
        "IFNAR1",
        "IFNGR1",
        "STAT1",
        "STAT2",
        "IRF1",
        "IRF7",
        "ISG15",
        "MX1",
    },
    "T-cell receptor signalling": {
        "CD3D",
        "CD3E",
        "CD247",
        "LCK",
        "ZAP70",
        "LAT",
        "PLCG1",
        "CARD11",
        "NFATC1",
    },
    "B-cell receptor signalling": {
        "CD79A",
        "CD79B",
        "SYK",
        "BTK",
        "BLNK",
        "PLCG2",
        "CARD11",
        "NFKB1",
    },
    "Angiogenesis": {"VEGFA", "VEGFB", "KDR", "FLT1", "ANGPT1", "ANGPT2", "TEK", "PECAM1", "HIF1A"},
    "Epithelial mesenchymal transition": {
        "CDH1",
        "CDH2",
        "VIM",
        "SNAI1",
        "SNAI2",
        "TWIST1",
        "ZEB1",
        "ZEB2",
        "TGFB1",
    },
    "Chromatin remodelling": {
        "ARID1A",
        "ARID1B",
        "SMARCA4",
        "SMARCB1",
        "CHD4",
        "KMT2D",
        "EZH2",
        "SUZ12",
    },
    "RNA splicing": {"SF3B1", "SRSF2", "U2AF1", "U2AF2", "PRPF8", "HNRNPA1", "RBM10", "ZRSR2"},
    "Ribosome biogenesis": {"RPL5", "RPL11", "RPS6", "RPS14", "NPM1", "NOP56", "NOP58", "FBL"},
}

MOUSE_PATHWAYS: dict[str, set[str]] = {name: set(genes) for name, genes in HUMAN_PATHWAYS.items()}
MOUSE_PATHWAYS.update(
    {
        "Murine innate immune sensing": {
            "TLR7",
            "TLR9",
            "MYD88",
            "IRF7",
            "IFIT1",
            "IFIT3",
            "OAS1A",
            "MX1",
        },
        "Skeletal muscle regeneration": {
            "PAX7",
            "MYOD1",
            "MYOG",
            "MYF5",
            "DES",
            "DMD",
            "IGF1",
            "HGF",
        },
    }
)
GENERIC_PATHWAYS: dict[str, set[str]] = {
    name: genes
    for name, genes in HUMAN_PATHWAYS.items()
    if name
    in {
        "DNA repair",
        "PI3K-AKT signalling",
        "MAPK signalling",
        "Apoptosis",
        "Cell cycle",
        "Oxidative stress",
        "Glycolysis",
        "TCA cycle",
        "Autophagy",
        "RNA splicing",
    }
}

PATHWAY_PACKS = {
    "Homo sapiens": HUMAN_PATHWAYS,
    "Mus musculus": MOUSE_PATHWAYS,
    "Generic reference": GENERIC_PATHWAYS,
}
DEMO_PATHWAYS = HUMAN_PATHWAYS  # backward compatible name

GENE_ALIASES = {
    "P53": "TP53",
    "HER2": "ERBB2",
    "ERBB-2": "ERBB2",
    "P21": "CDKN1A",
    "VEGFR2": "KDR",
    "PD1": "PDCD1",
    "PD-L1": "CD274",
    "NFKB": "NFKB1",
    "B-CATENIN": "CTNNB1",
    "MTORC1": "MTOR",
    "HIF-1A": "HIF1A",
}


def normalize_gene_symbol(value: object) -> str:
    symbol = str(value).strip().upper()
    return GENE_ALIASES.get(symbol, symbol)


def pathway_pack(organism: str) -> dict[str, set[str]]:
    if organism not in PATHWAY_PACKS:
        raise ValueError(f"Unsupported organism context: {organism}")
    return {name: set(genes) for name, genes in PATHWAY_PACKS[organism].items()}


def parse_gmt(text: str) -> dict[str, set[str]]:
    pathways: dict[str, set[str]] = {}
    for line_number, raw in enumerate(str(text).splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split("\t")
        if len(fields) < 3:
            raise ValueError(f"GMT line {line_number} requires name, description and genes.")
        name = fields[0].strip()
        genes = {normalize_gene_symbol(value) for value in fields[2:] if value.strip()}
        if not name or not genes:
            raise ValueError(f"GMT line {line_number} has an empty pathway or gene set.")
        pathways[name] = genes
    if not pathways:
        raise ValueError("No pathway sets were found in the GMT content.")
    return pathways


def hypergeom_tail(overlap: int, set_size: int, query_size: int, universe_size: int) -> float:
    if any(value < 0 for value in (overlap, set_size, query_size, universe_size)):
        raise ValueError("Hypergeometric parameters cannot be negative.")
    if (
        set_size > universe_size
        or query_size > universe_size
        or overlap > min(set_size, query_size)
    ):
        return 1.0
    maximum = min(set_size, query_size)
    denominator = comb(universe_size, query_size)
    if not denominator:
        return 1.0
    total = 0
    for k in range(overlap, maximum + 1):
        remaining_query = query_size - k
        if 0 <= remaining_query <= universe_size - set_size:
            total += comb(set_size, k) * comb(universe_size - set_size, remaining_query)
    return min(1.0, total / denominator)


def _bh_adjust(values: Iterable[float]) -> list[float]:
    series = pd.Series(list(values), dtype=float)
    if series.empty:
        return []
    order = series.sort_values().index.tolist()
    adjusted = pd.Series(1.0, index=series.index, dtype=float)
    running = 1.0
    for rank, index in reversed(list(enumerate(order, 1))):
        running = min(running, float(series.loc[index]) * len(series) / rank)
        adjusted.loc[index] = min(1.0, running)
    return adjusted.tolist()


def pathway_enrichment(
    genes: list[str] | set[str],
    *,
    pathways: dict[str, set[str]] | None = None,
    universe: set[str] | None = None,
) -> pd.DataFrame:
    query_submitted = {normalize_gene_symbol(gene) for gene in genes if str(gene).strip()}
    pathways = {
        name: {normalize_gene_symbol(g) for g in members}
        for name, members in (pathways or DEMO_PATHWAYS).items()
    }
    if not query_submitted:
        raise ValueError("At least one gene is required.")

    pathway_universe = set().union(*pathways.values()) if pathways else set()
    selected_universe = (
        {normalize_gene_symbol(gene) for gene in universe if str(gene).strip()}
        if universe is not None
        else pathway_universe
    )
    if not selected_universe:
        raise ValueError("The selected background universe is empty.")

    # Correctness: both query and every pathway are intersected with the selected universe.
    query = query_submitted & selected_universe
    if not query:
        preview = ", ".join(sorted(query_submitted)[:8])
        raise ValueError(
            "None of the submitted genes are recognized in the selected background universe"
            + (f": {preview}" if preview else ".")
        )

    rows: list[dict[str, object]] = []
    for name, raw_members in pathways.items():
        members = raw_members & selected_universe
        if not members:
            continue
        overlap = sorted(query & members)
        p_value = hypergeom_tail(len(overlap), len(members), len(query), len(selected_universe))
        expected = len(query) * len(members) / len(selected_universe)
        enrichment_ratio = len(overlap) / expected if expected > 0 else 0.0
        rows.append(
            {
                "pathway": name,
                "overlap_count": len(overlap),
                "pathway_size": len(members),
                "query_size": len(query),
                "universe_size": len(selected_universe),
                "expected_overlap": expected,
                "enrichment_ratio": enrichment_ratio,
                "overlap_genes": ", ".join(overlap),
                "p_value": p_value,
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return pd.DataFrame(
            columns=[
                "pathway",
                "overlap_count",
                "pathway_size",
                "query_size",
                "universe_size",
                "expected_overlap",
                "enrichment_ratio",
                "overlap_genes",
                "p_value",
                "fdr_bh",
            ]
        )
    frame["fdr_bh"] = _bh_adjust(frame["p_value"])
    return frame.sort_values(["p_value", "overlap_count"], ascending=[True, False]).reset_index(
        drop=True
    )


def preranked_gsea(
    ranked_genes: pd.DataFrame,
    *,
    gene_column: str = "gene",
    score_column: str = "score",
    pathways: dict[str, set[str]] | None = None,
    permutations: int = 500,
    random_state: int = 42,
    minimum_size: int = 3,
    maximum_size: int = 500,
) -> pd.DataFrame:
    if gene_column not in ranked_genes or score_column not in ranked_genes:
        raise ValueError("Ranked table must contain gene and score columns.")
    table = ranked_genes[[gene_column, score_column]].copy()
    table[gene_column] = table[gene_column].map(normalize_gene_symbol)
    table[score_column] = pd.to_numeric(table[score_column], errors="coerce")
    table = table.dropna().sort_values(score_column, ascending=False).drop_duplicates(gene_column)
    if len(table) < 5:
        raise ValueError("At least five ranked genes are required for GSEA.")
    genes = table[gene_column].tolist()
    scores = table[score_column].to_numpy(float)
    pathways = pathways or DEMO_PATHWAYS
    rng = Random(random_state)

    def enrichment_score(members: set[str], order: list[str], weights: np.ndarray) -> float:
        hits = np.array([gene in members for gene in order], dtype=bool)
        hit_count = int(hits.sum())
        miss_count = len(order) - hit_count
        if hit_count == 0 or miss_count == 0:
            return 0.0
        hit_weights = np.abs(weights[hits])
        hit_weights = hit_weights / max(hit_weights.sum(), 1e-12)
        running = np.empty(len(order), dtype=float)
        hit_index = 0
        value = 0.0
        miss_penalty = 1.0 / miss_count
        for index, is_hit in enumerate(hits):
            if is_hit:
                value += float(hit_weights[hit_index])
                hit_index += 1
            else:
                value -= miss_penalty
            running[index] = value
        maximum = float(running.max())
        minimum = float(running.min())
        return maximum if abs(maximum) >= abs(minimum) else minimum

    rows: list[dict[str, object]] = []
    for name, raw_members in pathways.items():
        members = {normalize_gene_symbol(g) for g in raw_members} & set(genes)
        if not minimum_size <= len(members) <= maximum_size:
            continue
        observed = enrichment_score(members, genes, scores)
        null: list[float] = []
        for _ in range(max(20, int(permutations))):
            permuted = genes.copy()
            rng.shuffle(permuted)
            null.append(enrichment_score(members, permuted, scores))
        same_sign = [value for value in null if value * observed >= 0]
        scale = np.mean(np.abs(same_sign or null)) or 1.0
        nes = observed / scale
        p_value = (1 + sum(abs(value) >= abs(observed) for value in null)) / (len(null) + 1)
        rows.append(
            {
                "pathway": name,
                "size": len(members),
                "enrichment_score": observed,
                "normalized_enrichment_score": nes,
                "p_value": p_value,
                "leading_edge": ", ".join(
                    [gene for gene in genes[: max(1, len(genes) // 3)] if gene in members]
                ),
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return pd.DataFrame(
            columns=[
                "pathway",
                "size",
                "enrichment_score",
                "normalized_enrichment_score",
                "p_value",
                "fdr_bh",
                "leading_edge",
            ]
        )
    frame["fdr_bh"] = _bh_adjust(frame["p_value"])
    return frame.sort_values(
        ["fdr_bh", "normalized_enrichment_score"], ascending=[True, False]
    ).reset_index(drop=True)


def interaction_edges(
    genes: list[str] | set[str], pathways: dict[str, set[str]] | None = None
) -> pd.DataFrame:
    query = {normalize_gene_symbol(gene) for gene in genes if str(gene).strip()}
    pathways = pathways or DEMO_PATHWAYS
    evidence: dict[tuple[str, str], set[str]] = defaultdict(set)
    for pathway, members in pathways.items():
        present = sorted(query & {normalize_gene_symbol(g) for g in members})
        for index, left in enumerate(present):
            for right in present[index + 1 :]:
                evidence[(left, right)].add(pathway)
    rows = [
        {
            "source": left,
            "target": right,
            "pathways": "; ".join(sorted(names)),
            "evidence_count": len(names),
            "edge_type": "pathway_co_membership",
        }
        for (left, right), names in evidence.items()
    ]
    return pd.DataFrame(
        rows, columns=["source", "target", "pathways", "evidence_count", "edge_type"]
    )


def network_metrics(edges: pd.DataFrame) -> pd.DataFrame:
    required = {"source", "target"}
    if edges.empty:
        return pd.DataFrame(
            columns=["gene", "degree", "degree_centrality", "betweenness", "component"]
        )
    if not required.issubset(edges.columns):
        raise ValueError("Edge table requires source and target columns.")
    adjacency: dict[str, set[str]] = defaultdict(set)
    for row in edges.itertuples(index=False):
        left, right = str(getattr(row, "source")), str(getattr(row, "target"))
        if left == right:
            continue
        adjacency[left].add(right)
        adjacency[right].add(left)
    nodes = sorted(adjacency)
    component: dict[str, int] = {}
    component_id = 0
    for start in nodes:
        if start in component:
            continue
        component_id += 1
        queue = deque([start])
        component[start] = component_id
        while queue:
            current = queue.popleft()
            for neighbour in adjacency[current]:
                if neighbour not in component:
                    component[neighbour] = component_id
                    queue.append(neighbour)

    betweenness = dict.fromkeys(nodes, 0.0)
    # Brandes algorithm for unweighted graphs.
    for source in nodes:
        stack: list[str] = []
        predecessors: dict[str, list[str]] = {node: [] for node in nodes}
        sigma = dict.fromkeys(nodes, 0.0)
        sigma[source] = 1.0
        distance = dict.fromkeys(nodes, -1)
        distance[source] = 0
        queue = deque([source])
        while queue:
            vertex = queue.popleft()
            stack.append(vertex)
            for neighbour in adjacency[vertex]:
                if distance[neighbour] < 0:
                    queue.append(neighbour)
                    distance[neighbour] = distance[vertex] + 1
                if distance[neighbour] == distance[vertex] + 1:
                    sigma[neighbour] += sigma[vertex]
                    predecessors[neighbour].append(vertex)
        dependency = dict.fromkeys(nodes, 0.0)
        while stack:
            vertex = stack.pop()
            for predecessor in predecessors[vertex]:
                if sigma[vertex]:
                    dependency[predecessor] += (
                        sigma[predecessor] / sigma[vertex] * (1 + dependency[vertex])
                    )
            if vertex != source:
                betweenness[vertex] += dependency[vertex]
    normalizer = max((len(nodes) - 1) * (len(nodes) - 2), 1)
    return (
        pd.DataFrame(
            [
                {
                    "gene": node,
                    "degree": len(adjacency[node]),
                    "degree_centrality": len(adjacency[node]) / max(len(nodes) - 1, 1),
                    "betweenness": betweenness[node] / normalizer,
                    "component": component[node],
                }
                for node in nodes
            ]
        )
        .sort_values(["degree", "betweenness"], ascending=False)
        .reset_index(drop=True)
    )


def normal_two_sided_p(z_value: float) -> float:
    return max(0.0, min(1.0, 1.0 - erf(abs(z_value) / sqrt(2.0))))
