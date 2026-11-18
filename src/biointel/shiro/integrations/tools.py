from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class ShiroAction:
    action_id: str
    label: str
    description: str
    page: str
    kind: str = "open_module"
    requires_confirmation: bool = True

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


_MODULES = (
    (("fasta", "sequence", "dna", "rna", "gc content"), ShiroAction("sequence-analyzer", "Open Sequence Intelligence", "Analyse nucleotide or protein sequences in BioIntel.", "pages/1_Sequence_Analyzer.py")),
    (("batch sequence", "many sequences"), ShiroAction("batch-sequence", "Open Batch Sequence Analysis", "Process multiple sequence records.", "pages/16_Batch_Sequence_Analysis.py")),
    (("variant", "vcf", "mutation", "annotation"), ShiroAction("variant-workbench", "Open Variant Workbench", "Review and annotate variant evidence.", "pages/57_Variant_Annotation_Workbench.py")),
    (("primer", "crispr", "guide rna", "codon"), ShiroAction("crispr-studio", "Open Primer & CRISPR Studio", "Prepare primer, guide and codon workflows.", "pages/58_Primer_CRISPR_Codon_Studio.py")),
    (("admet", "drug likeness", "toxicity"), ShiroAction("admet", "Open Molecular Developability", "Review descriptors, drug-likeness and research risk flags.", "pages/62_ADMET_Drug_Discovery.py")),
    (("pathway", "enrichment", "network"), ShiroAction("pathway", "Open Pathway Intelligence", "Run pathway and network analysis.", "pages/63_Pathway_Network_Analysis.py")),
    (("metagenomic", "microbiome", "taxonomy", "kraken"), ShiroAction("metagenomics", "Open Metagenomics Workspace", "Review microbial and metagenomic evidence.", "pages/82_Metagenomics_Pipeline.py")),
    (("single cell", "scrna", "cell cluster", "cell type"), ShiroAction("single-cell", "Open Single-Cell Intelligence", "Explore cell populations, markers and heterogeneity.", "pages/80_Single_Cell_Heterogeneity.py")),
    (("cancer", "oncology", "somatic", "tumor"), ShiroAction("cancer-genomics", "Open Cancer Genomics", "Review oncology research evidence and variants.", "pages/81_Cancer_Genomics.py")),
    (("multi omics", "biomarker"), ShiroAction("multi-omics", "Open Multi-Omics Discovery", "Integrate omics evidence and biomarker candidates.", "pages/102_Multi_Omics_Biomarker_Discovery.py")),
    (("dock", "binding pose", "ligand"), ShiroAction("docking", "Open Molecular Docking", "Prepare a qualified structural investigation.", "pages/116_Molecular_Docking_and_Dynamics_Lab.py")),
    (("protein design", "mutation engineering", "proteinmpnn"), ShiroAction("protein-design", "Open Protein Design", "Prepare a protein design or mutation workflow.", "pages/96_AI_Protein_Design_Lab.py")),
    (("classroom", "lesson", "quiz", "whiteboard", "notebook", "coding lab", "question bank", "learning analytics", "offline learning"), ShiroAction("education-suite", "Open BioIntel Education Suite", "Open interactive lessons, assessment, collaboration, coding and learning records.", "pages/356_BioIntel_Education_Suite.py")),
    (("career", "internship", "scholarship"), ShiroAction("career-hub", "Open Career & Scholarship Hub", "Discover and track education opportunities.", "pages/355_BioIntel_Career_Internship_Scholarship_Hub.py")),
    (("workflow", "pipeline", "dag"), ShiroAction("workflow-builder", "Open Workflow Builder", "Compose a reusable BioIntel scientific workflow.", "pages/103_Visual_Workflow_Builder.py")),
)


def suggest_actions(query: str, root: str | Path, maximum: int = 3) -> tuple[ShiroAction, ...]:
    normalized = " ".join(query.casefold().split())
    root_path = Path(root)
    values: list[ShiroAction] = []
    for terms, action in _MODULES:
        if any(term in normalized for term in terms) and (root_path / action.page).is_file():
            values.append(action)
    return tuple(values[:maximum])


def public_module_catalog(root: str | Path) -> Iterable[ShiroAction]:
    root_path = Path(root)
    for _, action in _MODULES:
        if (root_path / action.page).is_file():
            yield action
