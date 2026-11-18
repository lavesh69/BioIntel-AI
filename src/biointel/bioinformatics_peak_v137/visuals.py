from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from .catalog import MODULE_BY_KEY
from .scientific import AnalysisBundle


@dataclass
class VisualArtifact:
    title: str
    interpretation: str
    method: str
    source_name: str
    data: pd.DataFrame
    figure: go.Figure


VISUAL_PLANS: dict[str, tuple[tuple[str, str, str], ...]] = {
    "population_gwas_peak": (
        ("Manhattan plot", "scatter_genome", "result"), ("QQ plot", "qq", "qq"),
        ("Ancestry PCA", "scatter", "ancestry_pca"), ("LD proxy heatmap", "heatmap", "genotype_matrix"),
        ("Regional association", "scatter", "result"), ("PRS distribution", "hist", "prs_scores"),
        ("Subgroup forest", "bar", "result"), ("QC dashboard", "bar", "result"),
    ),
    "epigenomics_peak": (
        ("Peak heatmap", "heatmap", "peak_matrix"), ("Genome track", "scatter_genome", "result"),
        ("Accessibility volcano", "volcano", "result"), ("Motif activity heatmap", "heatmap", "motif_activity"),
        ("TF activity network", "network", "result"), ("Methylation profile", "hist", "result"),
        ("Peak-to-gene links", "sankey", "result"), ("RNA concordance", "scatter", "result"),
    ),
    "pharmacogenomics_peak": (
        ("Pharmacogene coverage", "bar", "result"), ("Diplotype evidence waterfall", "bar", "phenotypes"),
        ("Drug-gene matrix", "heatmap", "drug_gene_matrix"), ("Phenotype distribution", "bar", "phenotypes"),
        ("Population comparison", "hist", "result"), ("Evidence ladder", "bar", "result"),
        ("Conflict matrix", "heatmap", "conflicts"), ("Review timeline", "scatter", "result"),
    ),
    "structural_variant_peak": (
        ("Chromosome SV track", "scatter_genome", "result"), ("Breakpoint Circos-style view", "network", "result"),
        ("CNV profile", "line", "result"), ("Repeat-size distribution", "hist", "result"),
        ("Mosaic allele fraction", "hist", "result"), ("Caller concordance", "heatmap", "caller_concordance"),
        ("Segregation proxy", "bar", "gene_impact"), ("Priority waterfall", "bar", "result"),
    ),
    "rna_splicing_peak": (
        ("Sashimi-style junction view", "line", "result"), ("Transcript architecture", "scatter", "result"),
        ("Exon-usage heatmap", "heatmap", "psi_matrix"), ("PSI distribution", "hist", "result"),
        ("Isoform switching", "volcano", "result"), ("Junction support", "scatter", "result"),
        ("Variant-splice map", "network", "result"), ("Gene summary", "bar", "gene_summary"),
    ),
    "immune_repertoire": (
        ("Clonotype network", "network", "result"), ("V/J usage matrix", "heatmap", "vj_usage"),
        ("CDR3 length distribution", "hist", "result"), ("Diversity curves", "scatter", "diversity"),
        ("Clonal expansion treemap", "treemap", "result"), ("Clone-cell embedding", "scatter", "result"),
        ("Longitudinal clone tracking", "line", "longitudinal"), ("Repertoire QC dashboard", "bar", "diversity"),
    ),
    "single_cell_multiome": (
        ("Joint embedding", "scatter", "result"), ("Modality agreement", "hist", "result"),
        ("RNA-ATAC links", "network", "feature_links"), ("TF activity heatmap", "heatmap", "tf_activity"),
        ("Cell-state trajectory", "line", "result"), ("Multiome feature browser", "bar", "feature_links"),
        ("Batch mixing", "heatmap", "batch_mixing"), ("Cluster composition", "bar", "cluster_composition"),
    ),
    "proteogenomics_peak": (
        ("Variant-to-peptide flow", "sankey", "result"), ("HLA binding heatmap", "heatmap", "hla_matrix"),
        ("Peptide coverage", "bar", "result"), ("RNA and MS evidence", "scatter", "result"),
        ("Candidate waterfall", "bar", "result"), ("Normal-tissue risk", "scatter", "result"),
        ("Clonality landscape", "hist", "result"), ("Panel diversity", "treemap", "vaccine_panel"),
    ),
    "gene_regulatory_network": (
        ("TF regulatory network", "network", "top_edges"), ("Regulon activity heatmap", "heatmap", "activity_matrix"),
        ("TF condition volcano", "volcano", "result"), ("Target-gene flow", "sankey", "result"),
        ("Network centrality", "bar", "regulons"), ("Regulatory circuit", "network", "result"),
        ("Evidence matrix", "heatmap", "result"), ("Condition comparison", "scatter", "regulons"),
    ),
    "federated_genomic_discovery": (
        ("Phenotype-case matrix", "heatmap", "phenotype_matrix"), ("Federated source map", "network", "source_coverage"),
        ("Variant-match network", "network", "result"), ("Pedigree-compatible case view", "treemap", "result"),
        ("Access-status badges", "bar", "result"), ("Query provenance timeline", "scatter", "query_provenance"),
        ("Match waterfall", "bar", "result"), ("Source coverage", "bar", "source_coverage"),
    ),
    "viral_within_host": (
        ("Within-host frequency trajectories", "line", "result"), ("Minor-variant spectrum", "hist", "result"),
        ("Lineage marker landscape", "scatter", "lineage_markers"), ("Recombination matrix", "heatmap", "result"),
        ("Selection proxy profile", "scatter_genome", "result"), ("Subject timeline", "line", "trajectories"),
        ("Mutation heatmap", "heatmap", "result"), ("Viral QC dashboard", "bar", "subject_summary"),
    ),
    "genome_annotation": (
        ("Genome feature track", "scatter_genome", "result"), ("Annotation version difference", "heatmap", "version_diff"),
        ("Completeness dashboard", "bar", "result"), ("Orthology matrix", "heatmap", "orthology"),
        ("Synteny blocks", "scatter", "chromosome_summary"), ("Evidence distribution", "bar", "result"),
        ("Feature-length profile", "hist", "result"), ("Manual review funnel", "treemap", "review_queue"),
    ),
    "circular_dna_instability": (
        ("Circular breakpoint map", "network", "result"), ("Copy-number profile", "line", "result"),
        ("Amplification topology", "network", "result"), ("Mobile-element map", "scatter_genome", "result"),
        ("Recurrence heatmap", "heatmap", "chromosome_summary"), ("Gene impact", "bar", "gene_impact"),
        ("Event-size distribution", "hist", "result"), ("Instability priority waterfall", "bar", "result"),
    ),
    "environmental_edna": (
        ("Species-site heatmap", "heatmap", "occupancy"), ("Occupancy map", "scatter", "occupancy"),
        ("Biodiversity curves", "line", "sample_summary"), ("Control contamination", "bar", "contamination"),
        ("Temporal trends", "line", "result"), ("Reference confidence", "hist", "result"),
        ("Community ordination", "scatter", "sample_summary"), ("Surveillance alert dashboard", "bar", "occupancy"),
    ),
    "comparative_regulatory_genomics": (
        ("Conservation landscape", "scatter_genome", "result"), ("Motif-turnover heatmap", "heatmap", "motif_turnover"),
        ("Regulatory activity comparison", "scatter", "result"), ("Regulatory synteny", "scatter", "synteny"),
        ("Ortholog network", "network", "result"), ("Constraint distribution", "hist", "result"),
        ("Species clustering", "scatter", "species_summary"), ("Cross-species evidence matrix", "heatmap", "ortholog_matrix"),
    ),
}


def _bounded(frame: pd.DataFrame, n: int = 5000) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame()
    out = frame.copy()
    out = out.loc[:, ~out.columns.duplicated()]
    out.replace([np.inf, -np.inf], np.nan, inplace=True)
    if len(out) > n:
        out = out.sample(n, random_state=42).sort_index()
    return out


def _source(bundle: AnalysisBundle, name: str) -> pd.DataFrame:
    return _bounded(bundle.result if name == "result" else bundle.extras.get(name, pd.DataFrame()))


def _first_numeric(frame: pd.DataFrame, preferred: tuple[str, ...] = ()) -> str | None:
    for column in preferred:
        if column in frame.columns and pd.to_numeric(frame[column], errors="coerce").notna().any():
            return column
    for column in frame.columns:
        if pd.to_numeric(frame[column], errors="coerce").notna().sum() >= max(2, len(frame) // 10):
            return str(column)
    return None


def _first_category(frame: pd.DataFrame, preferred: tuple[str, ...] = ()) -> str | None:
    for column in preferred:
        if column in frame.columns:
            return column
    for column in frame.columns:
        if frame[column].nunique(dropna=True) <= min(max(2, len(frame) // 2), 40):
            return str(column)
    return str(frame.columns[0]) if len(frame.columns) else None


def _figure(kind: str, frame: pd.DataFrame, title: str) -> go.Figure:
    if frame.empty:
        fig = go.Figure()
        fig.add_annotation(text="No compatible records are available for this visual.", x=0.5, y=0.5, showarrow=False)
        fig.update_layout(title=title, height=430)
        return fig

    numeric = [str(c) for c in frame.columns if pd.to_numeric(frame[c], errors="coerce").notna().any()]
    categories = [str(c) for c in frame.columns if c not in numeric]
    x_cat = _first_category(frame, ("variant", "region", "gene", "tf", "sample", "species", "chrom", "event_type", "source", "cluster", "feature", "peptide", "site"))
    x_num = _first_numeric(frame, ("position", "start", "time", "frequency", "priority_score", "activity", "conservation", "psi", "delta_psi", "log2_fold_change"))
    y_num = _first_numeric(frame, ("priority_score", "minus_log10_p", "minus_log10_q", "delta_activity", "frequency", "activity", "signal", "count", "reads", "occupancy", "mean_priority"))
    color = _first_category(frame, ("chrom", "condition", "group", "lineage", "event_type", "species", "cluster", "source", "gene", "tf"))

    try:
        if kind == "scatter_genome":
            x = "position" if "position" in frame.columns else "start" if "start" in frame.columns else x_num
            y = "minus_log10_p" if "minus_log10_p" in frame.columns else "priority_score" if "priority_score" in frame.columns else y_num
            fig = px.scatter(frame, x=x, y=y, color=color, hover_data=list(frame.columns[:8])) if x and y else px.scatter(frame.reset_index(), x="index", y=y_num)
        elif kind == "volcano":
            x = next((c for c in ("log2_fold_change", "delta_psi", "delta_activity", "beta") if c in frame.columns), x_num)
            if "minus_log10_q" in frame.columns:
                y = "minus_log10_q"
            elif "q_value" in frame.columns:
                temp = frame.copy(); temp["minus_log10_q"] = -np.log10(pd.to_numeric(temp["q_value"], errors="coerce").clip(lower=1e-300)); frame = temp; y = "minus_log10_q"
            elif "p_value" in frame.columns:
                temp = frame.copy(); temp["minus_log10_p"] = -np.log10(pd.to_numeric(temp["p_value"], errors="coerce").clip(lower=1e-300)); frame = temp; y = "minus_log10_p"
            else:
                y = y_num
            fig = px.scatter(frame, x=x, y=y, color=color, hover_data=list(frame.columns[:8])) if x and y else px.scatter(frame.reset_index(), x="index", y=y_num)
        elif kind == "qq":
            x = "expected" if "expected" in frame.columns else numeric[0]
            y = "observed" if "observed" in frame.columns else numeric[min(1, len(numeric)-1)]
            fig = px.scatter(frame, x=x, y=y)
            low = float(np.nanmin([pd.to_numeric(frame[x], errors="coerce").min(), pd.to_numeric(frame[y], errors="coerce").min()]))
            high = float(np.nanmax([pd.to_numeric(frame[x], errors="coerce").max(), pd.to_numeric(frame[y], errors="coerce").max()]))
            fig.add_shape(type="line", x0=low, y0=low, x1=high, y1=high, line={"dash":"dash"})
        elif kind == "hist":
            x = next((c for c in ("priority_score","frequency","allele_fraction","size_bp","psi","delta_psi","reference_confidence","length_bp","shannon") if c in frame.columns), x_num or y_num)
            fig = px.histogram(frame, x=x, color=color if color != x else None, nbins=35)
        elif kind == "bar":
            x = x_cat or str(frame.columns[0]); y = y_num
            if y is None:
                counts = frame[x].astype(str).value_counts().head(30).rename_axis(x).reset_index(name="records"); frame = counts; y = "records"
            plot = frame.sort_values(y, ascending=False).head(40) if y in frame.columns else frame.head(40)
            fig = px.bar(plot, x=x, y=y, color=color if color not in {x, y} else None)
        elif kind == "line":
            x = next((c for c in ("time","position","start","date") if c in frame.columns), x_num)
            y = next((c for c in ("frequency","count","activity","copy_number","priority_score","shannon","total_reads") if c in frame.columns), y_num)
            line_group = _first_category(frame, ("subject","sample","clonotype","species","lineage","chrom"))
            fig = px.line(frame.sort_values(x) if x else frame, x=x, y=y, color=color, line_group=line_group) if x and y else px.line(frame.reset_index(), x="index", y=y_num)
        elif kind == "scatter":
            x = next((c for c in ("PC1","UMAP1","phenotype_similarity","conservation","activity","expression","binding_score") if c in frame.columns), x_num)
            y = next((c for c in ("PC2","UMAP2","variant_match","priority_score","modality_agreement","normal_tissue_risk","mean_activity") if c in frame.columns and c != x), y_num)
            fig = px.scatter(frame, x=x, y=y, color=color, hover_data=list(frame.columns[:8])) if x and y else px.scatter(frame.reset_index(), x="index", y=y_num)
        elif kind == "heatmap":
            matrix = frame.copy()
            index_col = categories[0] if categories else None
            if index_col:
                matrix = matrix.set_index(index_col)
            matrix = matrix.apply(pd.to_numeric, errors="coerce")
            matrix = matrix.loc[:, matrix.notna().any()]
            matrix = matrix.iloc[:60, :60]
            if matrix.empty:
                return _figure("bar", frame, title)
            fig = px.imshow(matrix.fillna(0), aspect="auto", labels={"color":"value"})
        elif kind == "network":
            source_col = next((c for c in ("tf","gene","source","sample","chrom","event_type","clonotype","species") if c in frame.columns), x_cat)
            target_col = next((c for c in ("target","variant","drug","peptide","region","gene","j_gene","ortholog_group") if c in frame.columns and c != source_col), None)
            if source_col is None or target_col is None:
                return _figure("scatter", frame, title)
            edges = frame[[source_col,target_col] + ([y_num] if y_num and y_num not in {source_col,target_col} else [])].dropna().head(120)
            nodes = pd.Index(pd.unique(edges[[source_col,target_col]].astype(str).values.ravel()))
            theta = np.linspace(0,2*np.pi,len(nodes),endpoint=False); coords={node:(float(np.cos(t)),float(np.sin(t))) for node,t in zip(nodes,theta)}
            fig=go.Figure()
            for _,row in edges.iterrows():
                sx,sy=coords[str(row[source_col])]; tx,ty=coords[str(row[target_col])]
                fig.add_trace(go.Scatter(x=[sx,tx,None],y=[sy,ty,None],mode="lines",hoverinfo="skip",showlegend=False,line={"width":1}))
            fig.add_trace(go.Scatter(x=[coords[n][0] for n in nodes],y=[coords[n][1] for n in nodes],mode="markers+text",text=list(nodes),textposition="top center",showlegend=False))
            fig.update_xaxes(visible=False); fig.update_yaxes(visible=False)
        elif kind == "sankey":
            source_col = next((c for c in ("variant","tf","gene","source","event_type") if c in frame.columns), x_cat)
            target_col = next((c for c in ("peptide","target","drug","gene","region") if c in frame.columns and c != source_col), None)
            if source_col is None or target_col is None:
                return _figure("bar", frame, title)
            edges=frame.groupby([source_col,target_col],as_index=False).size().sort_values("size",ascending=False).head(80)
            labels=list(pd.unique(edges[[source_col,target_col]].astype(str).values.ravel())); idx={v:i for i,v in enumerate(labels)}
            fig=go.Figure(go.Sankey(node={"label":labels},link={"source":[idx[str(v)] for v in edges[source_col]],"target":[idx[str(v)] for v in edges[target_col]],"value":edges["size"].tolist()}))
        elif kind == "treemap":
            path_cols=[c for c in ("group","chain","gene","hla","source","access_status","event_type","species","sample") if c in frame.columns][:2]
            value=next((c for c in ("count","priority_score","reads","frequency","max_priority") if c in frame.columns),None)
            if not path_cols:
                return _figure("bar", frame, title)
            fig=px.treemap(frame.head(500),path=path_cols,values=value)
        else:
            fig = px.scatter(frame.reset_index(), x="index", y=y_num)
    except Exception:
        fig = go.Figure()
        fig.add_annotation(text="This visual could not be rendered from the current schema. Review column mapping.", x=0.5, y=0.5, showarrow=False)

    fig.update_layout(title=title, height=460, margin={"l":30,"r":20,"t":60,"b":35}, legend_title_text="")
    return fig


def build_visuals(module_key: str, bundle: AnalysisBundle) -> list[VisualArtifact]:
    module = MODULE_BY_KEY[module_key]
    plans = VISUAL_PLANS[module_key]
    artifacts: list[VisualArtifact] = []
    for title, kind, source_name in plans:
        data = _source(bundle, source_name)
        fig = _figure(kind, data, title)
        artifacts.append(
            VisualArtifact(
                title=title,
                interpretation=f"Explore {title.lower()} for {module.short_title}; selections should be interpreted with the module quality gates and scientific boundary.",
                method=f"BioIntel deterministic {kind.replace('_',' ')} rendering from bounded result records.",
                source_name=source_name,
                data=data,
                figure=fig,
            )
        )
    return artifacts
