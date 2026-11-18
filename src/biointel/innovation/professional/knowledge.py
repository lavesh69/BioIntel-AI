from __future__ import annotations

from collections import defaultdict, deque
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re
import shutil
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd
from scipy import stats
from scipy.integrate import solve_ivp
from sklearn.decomposition import PCA
from sklearn.impute import SimpleImputer
from sklearn.metrics import pairwise_distances
from sklearn.preprocessing import StandardScaler

from .common import (
    _normalise_identifier, _numeric, _safe_run, _split_tokens,
    hardware_profile, runtime_capability_scan, stable_frame_hash, stable_payload_hash,
)

# ---------------------------------------------------------------------------
# Biomedical knowledge graph and evidence copilot
# ---------------------------------------------------------------------------


def knowledge_contradiction_audit(edges: pd.DataFrame) -> pd.DataFrame:
    if edges.empty or not {"source", "target", "relation"}.issubset(edges.columns):
        return pd.DataFrame()
    frame = edges.copy()
    frame["source_key"] = frame["source"].map(_normalise_identifier)
    frame["target_key"] = frame["target"].map(_normalise_identifier)
    frame["relation_key"] = frame["relation"].map(_normalise_identifier)
    direction_column = next((column for column in ("direction", "evidence_direction", "stance") if column in frame), None)
    if direction_column is None:
        frame["stance"] = "supports"
        direction_column = "stance"
    frame["stance_norm"] = frame[direction_column].astype(str).str.lower()
    rows = []
    for key, group in frame.groupby(["source_key", "target_key", "relation_key"]):
        supports = int(group["stance_norm"].str.contains("support|positive|confirm", regex=True).sum())
        contradicts = int(group["stance_norm"].str.contains("contradict|negative|refute", regex=True).sum())
        rows.append({
            "source": key[0],
            "target": key[1],
            "relation": key[2],
            "evidence_records": len(group),
            "supports": supports,
            "contradicts": contradicts,
            "conflict_status": "Conflicting" if supports and contradicts else "Supported only" if supports else "Contradicting only" if contradicts else "Unclassified",
        })
    return pd.DataFrame(rows).sort_values(["conflict_status", "evidence_records"], ascending=[True, False])


def knowledge_paths(edges: pd.DataFrame, start: str, end: str, max_hops: int = 4, max_paths: int = 100) -> pd.DataFrame:
    if edges.empty or not {"source", "target"}.issubset(edges.columns):
        return pd.DataFrame()
    max_hops = int(np.clip(max_hops, 1, 8))
    adjacency: dict[str, list[tuple[str, str, int]]] = defaultdict(list)
    relation_col = "relation" if "relation" in edges else None
    for index, row in edges.reset_index(drop=True).iterrows():
        source = str(row["source"])
        target = str(row["target"])
        relation = str(row[relation_col]) if relation_col else "related_to"
        adjacency[source].append((target, relation, index))
    queue = deque([(start, [start], [], [])])
    rows = []
    while queue and len(rows) < max_paths:
        node, nodes_path, relations, evidence_rows = queue.popleft()
        if len(relations) >= max_hops:
            continue
        for neighbour, relation, edge_index in adjacency.get(node, []):
            if neighbour in nodes_path:
                continue
            next_nodes = nodes_path + [neighbour]
            next_relations = relations + [relation]
            next_evidence = evidence_rows + [edge_index]
            if neighbour == end:
                rows.append({
                    "hop_count": len(next_relations),
                    "node_path": " → ".join(next_nodes),
                    "relation_path": " → ".join(next_relations),
                    "edge_rows": ",".join(map(str, next_evidence)),
                    "path_sha256": stable_payload_hash({"nodes": next_nodes, "relations": next_relations}),
                })
            else:
                queue.append((neighbour, next_nodes, next_relations, next_evidence))
    return pd.DataFrame(rows).sort_values("hop_count") if rows else pd.DataFrame()


def knowledge_rdf_export(nodes: pd.DataFrame, edges: pd.DataFrame) -> str:
    lines = ["@prefix biointel: <urn:biointel:> .", "@prefix schema: <https://schema.org/> .", ""]
    for row in nodes.itertuples(index=False):
        node = str(getattr(row, "node", getattr(row, "name", "")))
        if not node:
            continue
        node_id = _normalise_identifier(node)
        node_type = _normalise_identifier(getattr(row, "type", "entity")) or "entity"
        lines.append(f'biointel:{node_id} a biointel:{node_type} ; schema:name {json.dumps(node)} .')
    for row in edges.itertuples(index=False):
        source = _normalise_identifier(getattr(row, "source", ""))
        target = _normalise_identifier(getattr(row, "target", ""))
        relation = _normalise_identifier(getattr(row, "relation", "related_to")) or "related_to"
        if source and target:
            lines.append(f"biointel:{source} biointel:{relation} biointel:{target} .")
    return "\n".join(lines) + "\n"


def evidence_claim_highlight(claim: str, evidence: pd.DataFrame, text_column: str = "text") -> pd.DataFrame:
    if evidence.empty or text_column not in evidence:
        return pd.DataFrame()
    keywords = {token.lower() for token in re.findall(r"[A-Za-z0-9_-]{3,}", claim) if token.lower() not in {"with", "from", "that", "this", "were", "have"}}
    rows = []
    for index, row in evidence.iterrows():
        text = str(row[text_column])
        lower = text.lower()
        hits = sorted(keyword for keyword in keywords if keyword in lower)
        if not hits:
            continue
        positions = [lower.find(keyword) for keyword in hits if lower.find(keyword) >= 0]
        anchor = min(positions) if positions else 0
        start = max(0, anchor - 120)
        end = min(len(text), anchor + 320)
        rows.append({
            "evidence_row": index,
            "matched_terms": ", ".join(hits),
            "match_fraction": len(hits) / max(1, len(keywords)),
            "passage": text[start:end].strip(),
            "passage_sha256": sha256(text[start:end].encode()).hexdigest(),
        })
    return pd.DataFrame(rows).sort_values("match_fraction", ascending=False) if rows else pd.DataFrame()
# ---------------------------------------------------------------------------
# Multi-omics biomarker discovery
# ---------------------------------------------------------------------------


def batch_center_correct(frame: pd.DataFrame, batch: Sequence[Any], preserve_scale: bool = True) -> pd.DataFrame:
    numeric = frame.apply(pd.to_numeric, errors="coerce").astype(float)
    batch_series = pd.Series(list(batch), index=numeric.index[: len(batch)]).reindex(numeric.index).fillna("unknown")
    global_mean = numeric.mean(axis=0)
    corrected = numeric.copy()
    global_std = numeric.std(axis=0, ddof=0).replace(0, 1)
    for _, indexes in batch_series.groupby(batch_series).groups.items():
        subset = numeric.loc[indexes]
        centered = subset - subset.mean(axis=0) + global_mean
        if preserve_scale:
            batch_std = subset.std(axis=0, ddof=0).replace(0, np.nan)
            centered = (subset - subset.mean(axis=0)) / batch_std * global_std + global_mean
            centered = centered.replace([np.inf, -np.inf], np.nan).fillna(subset - subset.mean(axis=0) + global_mean)
        corrected.loc[indexes] = centered
    corrected.attrs["method"] = "Batch mean/scale correction; screening analogue, not ComBat"
    corrected.attrs["input_sha256"] = stable_frame_hash(frame)
    return corrected


def multi_view_latent_factors(views: Mapping[str, pd.DataFrame], components: int = 3) -> tuple[pd.DataFrame, pd.DataFrame]:
    factors: list[pd.DataFrame] = []
    loadings: list[pd.DataFrame] = []
    for name, view in views.items():
        if view.empty:
            continue
        numeric = view.apply(pd.to_numeric, errors="coerce")
        imputed = SimpleImputer(strategy="median").fit_transform(numeric)
        scaled = StandardScaler().fit_transform(imputed)
        n_components = max(1, min(int(components), scaled.shape[0] - 1 if scaled.shape[0] > 1 else 1, scaled.shape[1]))
        pca = PCA(n_components=n_components, random_state=42)
        scores = pca.fit_transform(scaled)
        score_frame = pd.DataFrame(scores, index=view.index, columns=[f"{name}_factor_{index+1}" for index in range(n_components)])
        factors.append(score_frame)
        loading_frame = pd.DataFrame(pca.components_.T, index=numeric.columns, columns=score_frame.columns).reset_index(names="feature")
        loading_frame.insert(0, "view", name)
        loadings.append(loading_frame)
    combined = pd.concat(factors, axis=1) if factors else pd.DataFrame()
    loading_table = pd.concat(loadings, ignore_index=True) if loadings else pd.DataFrame()
    return combined, loading_table


def similarity_network_fusion_screen(views: Mapping[str, pd.DataFrame], neighbours: int = 10, iterations: int = 10) -> np.ndarray:
    matrices = []
    for view in views.values():
        if view.empty:
            continue
        numeric = view.apply(pd.to_numeric, errors="coerce")
        scaled = StandardScaler().fit_transform(SimpleImputer(strategy="median").fit_transform(numeric))
        distance = pairwise_distances(scaled, metric="euclidean")
        sigma = np.nanmedian(distance[distance > 0]) if np.any(distance > 0) else 1.0
        affinity = np.exp(-(distance ** 2) / max(2 * sigma ** 2, 1e-9))
        np.fill_diagonal(affinity, 1.0)
        k = max(1, min(int(neighbours), affinity.shape[0] - 1))
        if k < affinity.shape[0] - 1:
            mask = np.zeros_like(affinity, dtype=bool)
            for row in range(affinity.shape[0]):
                keep = np.argpartition(affinity[row], -k - 1)[-k - 1:]
                mask[row, keep] = True
            affinity = np.where(mask | mask.T, affinity, 0.0)
        affinity = affinity / np.maximum(affinity.sum(axis=1, keepdims=True), 1e-12)
        matrices.append(affinity)
    if not matrices:
        return np.empty((0, 0))
    fused = sum(matrices) / len(matrices)
    for _ in range(max(0, int(iterations))):
        updated = []
        for index, matrix in enumerate(matrices):
            others = (sum(matrices) - matrix) / max(1, len(matrices) - 1) if len(matrices) > 1 else matrix
            propagated = matrix @ others @ matrix.T
            propagated = propagated / np.maximum(propagated.sum(axis=1, keepdims=True), 1e-12)
            updated.append(propagated)
        matrices = updated
        fused = sum(matrices) / len(matrices)
    fused = (fused + fused.T) / 2
    np.fill_diagonal(fused, 1.0)
    return fused


def logrank_screen(time: Sequence[float], event: Sequence[int], group: Sequence[Any]) -> dict[str, Any]:
    t = np.asarray(time, dtype=float)
    e = np.asarray(event, dtype=int)
    g = np.asarray(group)
    valid = np.isfinite(t) & np.isin(e, [0, 1]) & pd.notna(g)
    t, e, g = t[valid], e[valid], g[valid]
    groups = np.unique(g)
    if len(groups) != 2 or len(t) < 6:
        return {"status": "Requires two groups and at least six valid observations", "n": len(t)}
    g1 = g == groups[0]
    observed_1 = expected_1 = variance_1 = 0.0
    for event_time in np.unique(t[e == 1]):
        at_risk = t >= event_time
        deaths = (t == event_time) & (e == 1)
        n = int(at_risk.sum())
        n1 = int((at_risk & g1).sum())
        d = int(deaths.sum())
        d1 = int((deaths & g1).sum())
        if n <= 1 or d == 0:
            continue
        observed_1 += d1
        expected_1 += d * n1 / n
        variance_1 += n1 * (n - n1) * d * (n - d) / (n ** 2 * (n - 1))
    statistic = (observed_1 - expected_1) ** 2 / variance_1 if variance_1 > 0 else np.nan
    p_value = float(stats.chi2.sf(statistic, 1)) if np.isfinite(statistic) else np.nan
    return {
        "n": len(t),
        "groups": [str(value) for value in groups],
        "events": int(e.sum()),
        "chi_square": float(statistic) if np.isfinite(statistic) else None,
        "p_value": p_value if np.isfinite(p_value) else None,
        "status": "Exploratory association" if np.isfinite(p_value) and p_value < 0.05 else "No clear group separation",
        "boundary": "Unadjusted log-rank screen; not a multivariable survival model or clinical validation.",
    }
