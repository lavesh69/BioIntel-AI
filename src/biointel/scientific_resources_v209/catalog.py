from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote, quote_plus, urlparse

from biointel.internet.network_policy import OFFICIAL_SCIENTIFIC_HOSTS


@dataclass(frozen=True)
class ScientificResource:
    key: str
    name: str
    homepage: str
    search_template: str | None
    purpose: str
    privacy_note: str = "Public website: do not submit patient identifiers or confidential project content."

    @property
    def host(self) -> str:
        return (urlparse(self.homepage).hostname or "").lower().rstrip(".")

    def url(self, query: str = "") -> str:
        cleaned = str(query or "").strip()
        if not cleaned or not self.search_template:
            value = self.homepage
        else:
            value = self.search_template.format(
                query=quote_plus(cleaned),
                path_query=quote(cleaned, safe=""),
            )
        parsed = urlparse(value)
        host = (parsed.hostname or "").lower().rstrip(".")
        if parsed.scheme.lower() != "https" or not host:
            raise ValueError(f"Unsafe scientific-resource URL for {self.name}.")
        if host not in OFFICIAL_SCIENTIFIC_HOSTS:
            raise ValueError(f"Scientific-resource host is not approved: {host}")
        return value


RESOURCES: dict[str, ScientificResource] = {
    "pubmed": ScientificResource(
        "pubmed", "PubMed", "https://pubmed.ncbi.nlm.nih.gov/",
        "https://pubmed.ncbi.nlm.nih.gov/?term={query}",
        "Primary biomedical literature search.",
    ),
    "europepmc": ScientificResource(
        "europepmc", "Europe PMC", "https://europepmc.org/",
        "https://europepmc.org/search?query={query}",
        "Literature, grants and open full-text discovery.",
    ),
    "ncbi": ScientificResource(
        "ncbi", "NCBI", "https://www.ncbi.nlm.nih.gov/",
        "https://www.ncbi.nlm.nih.gov/search/all/?term={query}",
        "Sequences, genes, genomes and biomedical records.",
    ),
    "clinvar": ScientificResource(
        "clinvar", "NCBI ClinVar", "https://www.ncbi.nlm.nih.gov/clinvar/",
        "https://www.ncbi.nlm.nih.gov/clinvar/?term={query}",
        "Submitted clinical-variant assertions and supporting evidence.",
    ),
    "geo": ScientificResource(
        "geo", "NCBI GEO", "https://www.ncbi.nlm.nih.gov/geo/",
        "https://www.ncbi.nlm.nih.gov/gds/?term={query}",
        "Public functional-genomics and expression studies.",
    ),
    "gnomad": ScientificResource(
        "gnomad", "gnomAD Browser", "https://gnomad.broadinstitute.org/",
        "https://gnomad.broadinstitute.org/search?query={query}",
        "Population allele frequency and gene constraint context.",
    ),
    "ensembl": ScientificResource(
        "ensembl", "Ensembl", "https://www.ensembl.org/",
        "https://www.ensembl.org/Multi/Search/Results?q={query}",
        "Genome, transcript, comparative and variation annotation.",
    ),
    "uniprot": ScientificResource(
        "uniprot", "UniProt", "https://www.uniprot.org/",
        "https://www.uniprot.org/uniprotkb?query={query}",
        "Protein sequence, function and evidence records.",
    ),
    "interpro": ScientificResource(
        "interpro", "InterPro", "https://www.ebi.ac.uk/interpro/",
        "https://www.ebi.ac.uk/interpro/search/text/{path_query}/",
        "Protein family, domain and functional-site annotation.",
    ),
    "reactome": ScientificResource(
        "reactome", "Reactome", "https://reactome.org/",
        "https://reactome.org/content/query?q={query}",
        "Curated pathway and reaction evidence.",
    ),
    "string": ScientificResource(
        "string", "STRING", "https://string-db.org/", None,
        "Protein association and interaction-network exploration.",
    ),
    "rcsb": ScientificResource(
        "rcsb", "RCSB PDB", "https://www.rcsb.org/", None,
        "Experimentally determined macromolecular structures.",
    ),
    "pubchem": ScientificResource(
        "pubchem", "PubChem", "https://pubchem.ncbi.nlm.nih.gov/",
        "https://pubchem.ncbi.nlm.nih.gov/#query={query}",
        "Compound identity, properties and public assay records.",
    ),
    "chembl": ScientificResource(
        "chembl", "ChEMBL", "https://www.ebi.ac.uk/chembl/",
        "https://www.ebi.ac.uk/chembl/explore/compound/?q={query}",
        "Curated bioactivity and medicinal-chemistry records.",
    ),
    "clinicaltrials": ScientificResource(
        "clinicaltrials", "ClinicalTrials.gov", "https://clinicaltrials.gov/",
        "https://clinicaltrials.gov/search?term={query}",
        "Registered interventional and observational study records.",
    ),
    "openneuro": ScientificResource(
        "openneuro", "OpenNeuro", "https://openneuro.org/", None,
        "Public BIDS-organized neuroimaging and neurophysiology datasets.",
    ),
    "allen": ScientificResource(
        "allen", "Allen Brain Atlas", "https://portal.brain-map.org/", None,
        "Brain-region, cell-type and transcriptomic atlas resources.",
    ),
    "hpa": ScientificResource(
        "hpa", "Human Protein Atlas", "https://www.proteinatlas.org/",
        "https://www.proteinatlas.org/search/{path_query}",
        "Tissue, cell-type and subcellular protein-expression context.",
    ),
    "iuphar": ScientificResource(
        "iuphar", "IUPHAR/BPS Guide to Pharmacology", "https://www.guidetopharmacology.org/", None,
        "Expert-curated target, ligand and pharmacology context.",
    ),
    "gpcrdb": ScientificResource(
        "gpcrdb", "GPCRdb", "https://gpcrdb.org/", None,
        "GPCR sequences, structures, topology and pharmacology.",
    ),
}


_NEURO_GROUPS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("genetic", "variant", "genome", "development"), ("clinvar", "gnomad", "ensembl", "pubmed")),
    (("imaging", "connectom", "neuropath", "oncology", "critical"), ("openneuro", "allen", "pubmed", "clinicaltrials")),
    (("expression", "atlas", "cell_type", "neuroimmune", "inflammation"), ("allen", "hpa", "geo", "reactome", "pubmed")),
    (("eeg", "meg", "sleep", "epilep", "movement", "autonomic", "speech", "digital"), ("openneuro", "pubmed", "clinicaltrials")),
    (("target", "gpcr", "ion_channel", "pathway", "receptor", "neurotransmitter"), ("iuphar", "gpcrdb", "uniprot", "reactome", "string", "pubmed")),
    (("bbb", "drug", "adme", "pk", "occupancy", "off_target", "side_effect", "polypharmacy", "blood_csf"), ("pubchem", "chembl", "iuphar", "clinicaltrials", "pubmed")),
    (("trial", "clinical", "translation", "precision", "rehabilitation"), ("clinicaltrials", "pubmed", "europepmc")),
)


_CATEGORY_DEFAULTS: dict[str, tuple[str, ...]] = {
    "Neuro/CNS": ("pubmed", "openneuro", "allen", "clinicaltrials"),
    "Bioinformatics": ("ncbi", "ensembl", "geo", "europepmc"),
    "Discovery": ("pubchem", "chembl", "rcsb", "uniprot", "iuphar", "pubmed"),
    "Lab Analytics": ("pubmed", "europepmc", "ncbi", "uniprot", "reactome"),
}


def _extend_unique(output: list[str], values: tuple[str, ...]) -> None:
    for value in values:
        if value in RESOURCES and value not in output:
            output.append(value)


def resource_keys_for_module(module_key: str, title: str, category: str, *, limit: int = 6) -> tuple[str, ...]:
    text = f"{module_key} {title}".lower().replace("-", "_")
    output: list[str] = []
    if category == "Neuro/CNS":
        for tokens, resources in _NEURO_GROUPS:
            if any(token in text for token in tokens):
                _extend_unique(output, resources)
    elif category == "Bioinformatics":
        if any(token in text for token in ("variant", "genome", "gwas", "rare", "crispr", "annotation", "pangenome", "long_read")):
            _extend_unique(output, ("ncbi", "clinvar", "gnomad", "ensembl", "pubmed"))
        if any(token in text for token in ("single_cell", "spatial", "transcript", "omics", "expression", "epigen", "cell_atlas")):
            _extend_unique(output, ("geo", "hpa", "reactome", "europepmc"))
        if any(token in text for token in ("protein", "proteom", "glyco")):
            _extend_unique(output, ("uniprot", "interpro", "string", "europepmc"))
        if any(token in text for token in ("microbi", "pathogen", "amr", "virolog", "environment", "edna", "one_health")):
            _extend_unique(output, ("ncbi", "uniprot", "europepmc"))
    elif category == "Discovery":
        if any(token in text for token in ("protein", "antibody", "enzyme", "host_pathogen")):
            _extend_unique(output, ("uniprot", "rcsb", "interpro", "iuphar", "pubmed"))
        if any(token in text for token in ("drug", "compound", "admet", "docking", "ligand", "dti")):
            _extend_unique(output, ("pubchem", "chembl", "rcsb", "iuphar", "pubmed"))
        if any(token in text for token in ("immun", "neoantigen", "cell_therapy", "vaccine")):
            _extend_unique(output, ("uniprot", "clinicaltrials", "pubmed", "europepmc"))
    elif category == "Lab Analytics":
        if any(token in text for token in ("image", "microscopy", "phenotyp", "organoid")):
            _extend_unique(output, ("hpa", "pubmed", "europepmc"))
        if any(token in text for token in ("microbi", "metagenom")):
            _extend_unique(output, ("ncbi", "uniprot", "pubmed"))
        if any(token in text for token in ("synthetic", "primer", "crispr", "gene_therapy")):
            _extend_unique(output, ("ncbi", "ensembl", "uniprot", "pubmed"))
        if any(token in text for token in ("bioprocess", "fermentation")):
            _extend_unique(output, ("pubmed", "europepmc", "reactome"))
    _extend_unique(output, _CATEGORY_DEFAULTS.get(category, ("pubmed",)))
    return tuple(output[: max(1, int(limit))])


def resources_for_module(module_key: str, title: str, category: str, *, limit: int = 6) -> tuple[ScientificResource, ...]:
    return tuple(RESOURCES[key] for key in resource_keys_for_module(module_key, title, category, limit=limit))


def validate_resource_catalog() -> list[str]:
    errors: list[str] = []
    for key, resource in RESOURCES.items():
        try:
            resource.url("test query")
        except Exception as exc:
            errors.append(f"{key}: {exc}")
    return errors


__all__ = [
    "ScientificResource",
    "RESOURCES",
    "resource_keys_for_module",
    "resources_for_module",
    "validate_resource_catalog",
]
