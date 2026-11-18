from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from biointel.operational_v164 import provisioning_catalog


@dataclass(frozen=True)
class LicencePolicy:
    licence_id: str
    label: str
    terms_url: str
    acceptance_mode: str
    redistribution_status: str
    notes: str = ""


@dataclass(frozen=True)
class ReferenceAsset:
    reference_id: str
    label: str
    category: str
    release_mode: str
    source_url: str
    checksum_url: str
    licence_id: str
    expected_format: str
    approximate_size_gb: float
    required_tools: tuple[str, ...]
    modules: tuple[str, ...]
    download_strategy: str
    install_command: tuple[str, ...] = ()
    schema_checks: tuple[str, ...] = ()
    notes: str = ""


LICENCES: dict[str, LicencePolicy] = {
    "bioconda-upstream": LicencePolicy(
        "bioconda-upstream",
        "Upstream package licence captured from installed package and project source",
        "https://bioconda.github.io/",
        "capture-and-review",
        "depends-on-upstream",
        "Conda packaging is not a substitute for reviewing the upstream software licence.",
    ),
    "ncbi-data-policy": LicencePolicy(
        "ncbi-data-policy", "NCBI data usage policy", "https://www.ncbi.nlm.nih.gov/home/about/policies/", "record-review", "provider-policy"
    ),
    "ensembl-terms": LicencePolicy(
        "ensembl-terms", "Ensembl terms and conditions", "https://www.ensembl.org/info/about/legal/index.html", "record-review", "provider-policy"
    ),
    "chembl-cc-by-sa-3": LicencePolicy(
        "chembl-cc-by-sa-3", "Creative Commons Attribution-ShareAlike 3.0", "https://creativecommons.org/licenses/by-sa/3.0/", "automatic-with-attribution-record", "redistribution-with-conditions"
    ),
    "go-cc-by-4": LicencePolicy(
        "go-cc-by-4", "Creative Commons Attribution 4.0", "https://creativecommons.org/licenses/by/4.0/", "automatic-with-attribution-record", "redistribution-with-attribution"
    ),
    "uniprot-cc-by-4": LicencePolicy(
        "uniprot-cc-by-4", "Creative Commons Attribution 4.0", "https://www.uniprot.org/help/license", "automatic-with-attribution-record", "redistribution-with-attribution"
    ),
    "reactome-cc-by-4": LicencePolicy(
        "reactome-cc-by-4", "Creative Commons Attribution 4.0", "https://reactome.org/license", "automatic-with-attribution-record", "redistribution-with-attribution"
    ),
    "hpo-terms": LicencePolicy(
        "hpo-terms", "Human Phenotype Ontology licence", "https://hpo.jax.org/app/license", "record-review", "provider-policy"
    ),
    "ucsc-terms": LicencePolicy(
        "ucsc-terms", "UCSC Genome Browser data use conditions", "https://genome.ucsc.edu/goldenPath/credits.html", "record-review", "source-dependent"
    ),
    "broad-gnomad-terms": LicencePolicy(
        "broad-gnomad-terms", "gnomAD terms of use", "https://gnomad.broadinstitute.org/terms", "explicit-operator-acceptance", "provider-policy"
    ),
    "card-terms": LicencePolicy(
        "card-terms", "CARD data licence and terms", "https://card.mcmaster.ca/about", "explicit-operator-acceptance", "provider-policy"
    ),
    "dtu-academic": LicencePolicy(
        "dtu-academic", "DTU Health Tech stand-alone software terms", "https://services.healthtech.dtu.dk/", "explicit-operator-acceptance", "restricted-by-user-class"
    ),
    "ont-public-license": LicencePolicy(
        "ont-public-license", "Oxford Nanopore Technologies Public License", "https://github.com/nanoporetech/dorado/blob/release-v1.0/LICENSE.md", "record-review", "provider-policy"
    ),
    "proteinmpnn-mit": LicencePolicy(
        "proteinmpnn-mit", "MIT License", "https://github.com/dauparas/ProteinMPNN/blob/main/LICENSE", "automatic-with-attribution-record", "redistribution-with-attribution"
    ),
    "rfdiffusion-bsd": LicencePolicy(
        "rfdiffusion-bsd", "BSD 3-Clause License covering code and referenced weights", "https://github.com/RosettaCommons/RFdiffusion/blob/main/LICENSE", "automatic-with-attribution-record", "redistribution-with-conditions"
    ),
    "bindingdb-terms": LicencePolicy(
        "bindingdb-terms", "BindingDB terms of use", "https://www.bindingdb.org/rwd/bind/chemsearch/marvin/SDFdownload.jsp?all_download=yes", "record-review", "provider-policy"
    ),
    "source-database-terms": LicencePolicy(
        "source-database-terms", "Source database licences apply", "", "explicit-operator-acceptance", "mixed-sources"
    ),
}


_MANUAL_ENGINE_POLICIES: dict[str, dict[str, Any]] = {
    "dorado": {"licence_id": "ont-public-license", "upstream": "https://github.com/nanoporetech/dorado", "install_route": "provider-release"},
    "netmhcpan": {"licence_id": "dtu-academic", "upstream": "https://services.healthtech.dtu.dk/services/NetMHCpan-4.1/", "install_route": "manual-authorized-download"},
    "netmhciipan": {"licence_id": "dtu-academic", "upstream": "https://services.healthtech.dtu.dk/services/NetMHCIIpan-4.0/", "install_route": "manual-authorized-download"},
    "proteinmpnn": {"licence_id": "proteinmpnn-mit", "upstream": "https://github.com/dauparas/ProteinMPNN", "install_route": "git-and-weight-verification"},
    "rfdiffusion": {"licence_id": "rfdiffusion-bsd", "upstream": "https://github.com/RosettaCommons/RFdiffusion", "install_route": "container-or-git-and-weight-verification"},
}


def engine_catalog() -> pd.DataFrame:
    base = provisioning_catalog().copy()
    rows: list[dict[str, Any]] = []
    for row in base.to_dict(orient="records"):
        engine = str(row["engine"])
        conda_packages = [item.strip() for item in str(row.get("conda_packages") or "").split(",") if item.strip()]
        pip_packages = [item.strip() for item in str(row.get("pip_packages") or "").split(",") if item.strip()]
        manual = _MANUAL_ENGINE_POLICIES.get(engine, {})
        primary_package = conda_packages[0] if conda_packages else (pip_packages[0] if pip_packages else engine)
        if manual:
            licence_id = str(manual["licence_id"])
            upstream = str(manual["upstream"])
            install_route = str(manual["install_route"])
        else:
            licence_id = "bioconda-upstream"
            upstream = f"https://bioconda.github.io/recipes/{primary_package}/README.html" if conda_packages else f"https://pypi.org/project/{primary_package}/"
            install_route = "micromamba" if conda_packages else "pinned-python-venv"
        item = {
            **row,
            "upstream_url": upstream,
            "licence_id": licence_id,
            "licence_acceptance_mode": LICENCES[licence_id].acceptance_mode,
            "install_route": install_route,
            "platform_target": "WSL2-Linux-x86_64",
            "package_provenance_required": True,
            "package_sha256_required": True,
            "license_text_sha256_required": True,
            "smoke_test_required": True,
            "golden_fixture_required": True,
            "negative_control_required": True,
        }
        rows.append(item)
    frame = pd.DataFrame(rows).sort_values("engine").reset_index(drop=True)
    if len(frame) != 53 or frame["engine"].nunique() != 53:
        raise RuntimeError(f"Expected 53 unique specialist engines, found {len(frame)} rows/{frame['engine'].nunique()} unique.")
    return frame


REFERENCES: tuple[ReferenceAsset, ...] = (
    ReferenceAsset("grch38-fasta", "Human reference genome GRCh38", "genome", "pinned", "https://hgdownload.soe.ucsc.edu/goldenPath/hg38/bigZips/hg38.fa.gz", "", "ucsc-terms", "FASTA.GZ", 0.95, ("samtools", "bwa", "minimap2"), ("cancer_genomics_core", "genome_editing_safety", "pharmacogenomics", "population_gwas", "rare_variant_family", "structural_variant_repeat"), "direct", schema_checks=("gzip", "fasta")),
    ReferenceAsset("clinvar-grch38-vcf", "ClinVar GRCh38 VCF", "clinical-variant", "weekly-or-monthly-pinned", "https://ftp.ncbi.nlm.nih.gov/pub/clinvar/vcf_GRCh38/clinvar.vcf.gz", "https://ftp.ncbi.nlm.nih.gov/pub/clinvar/vcf_GRCh38/clinvar.vcf.gz.md5", "ncbi-data-policy", "VCF.GZ", 0.25, ("bcftools", "vep"), ("cancer_genomics_core", "pharmacogenomics", "rare_variant_family"), "direct", schema_checks=("gzip", "vcf")),
    ReferenceAsset("clinvar-grch38-tbi", "ClinVar GRCh38 VCF index", "clinical-variant", "paired-with-clinvar-vcf", "https://ftp.ncbi.nlm.nih.gov/pub/clinvar/vcf_GRCh38/clinvar.vcf.gz.tbi", "", "ncbi-data-policy", "TBI", 0.01, ("bcftools",), ("cancer_genomics_core", "pharmacogenomics", "rare_variant_family"), "direct", schema_checks=("tabix-index",)),
    ReferenceAsset("vep-cache-grch38", "Ensembl VEP Homo sapiens GRCh38 cache", "variant-annotation", "ensembl-release-pinned", "https://www.ensembl.org/info/docs/tools/vep/script/vep_cache.html", "", "ensembl-terms", "VEP_CACHE", 25.0, ("vep",), ("cancer_genomics_core", "pharmacogenomics", "rare_variant_family", "structural_variant_repeat"), "tool-managed", install_command=("perl", "INSTALL.pl", "-a", "c", "-s", "homo_sapiens", "-y", "GRCh38"), schema_checks=("vep-cache-info",)),
    ReferenceAsset("gnomad-genomes", "gnomAD genomes", "population-variant", "explicit-release", "https://gnomad.broadinstitute.org/downloads", "", "broad-gnomad-terms", "VCF/BGZF", 500.0, ("bcftools",), ("population_gwas", "rare_variant_family", "pharmacogenomics"), "manual-release", schema_checks=("vcf", "tabix-index")),
    ReferenceAsset("hpo-ontology", "Human Phenotype Ontology", "ontology", "latest-release-resolved", "https://github.com/obophenotype/human-phenotype-ontology/releases/latest/download/hp.obo", "", "hpo-terms", "OBO", 0.05, (), ("rare_variant_family", "biomedical_knowledge_graph"), "direct", schema_checks=("obo",)),
    ReferenceAsset("go-basic", "Gene Ontology basic", "ontology", "current", "https://purl.obolibrary.org/obo/go/go-basic.obo", "", "go-cc-by-4", "OBO", 0.04, (), ("biomedical_knowledge_graph", "multiomics_harmonization", "enzyme_pathway_design"), "direct", schema_checks=("obo",)),
    ReferenceAsset("reactome-uniprot", "Reactome UniProt pathway mapping", "pathway", "current", "https://reactome.org/download/current/UniProt2Reactome_All_Levels.txt", "", "reactome-cc-by-4", "TSV", 0.25, (), ("biomedical_knowledge_graph", "multiomics_harmonization", "enzyme_pathway_design"), "direct", schema_checks=("tsv",)),
    ReferenceAsset("uniprot-swissprot", "UniProtKB Swiss-Prot", "protein", "current", "https://rest.uniprot.org/uniprotkb/stream?compressed=true&format=fasta&query=%28reviewed%3Atrue%29", "", "uniprot-cc-by-4", "FASTA.GZ", 0.25, ("blastn",), ("protein_language_design", "proteogenomics_neoantigen", "immunoinformatics_vaccine", "enzyme_pathway_design"), "direct", schema_checks=("gzip", "fasta")),
    ReferenceAsset("chembl", "ChEMBL database release", "chemistry", "explicit-release", "https://chembl.gitbook.io/chembl-interface-documentation/downloads", "", "chembl-cc-by-sa-3", "SQLite/PostgreSQL dump", 20.0, (), ("protein_ligand_codesign", "docking_dynamics", "phenotypic_screening"), "manual-release", schema_checks=("sqlite-or-postgres-dump",)),
    ReferenceAsset("bindingdb", "BindingDB complete dataset", "binding", "explicit-release", "https://www.bindingdb.org/rwd/bind/chemsearch/marvin/SDFdownload.jsp?all_download=yes", "", "bindingdb-terms", "TSV/SDF", 5.0, (), ("protein_ligand_codesign", "docking_dynamics", "protein_language_design"), "manual-release", schema_checks=("tsv-or-sdf",)),
    ReferenceAsset("amrfinder-db", "NCBI AMRFinderPlus database", "amr", "tool-compatible-current", "https://github.com/ncbi/amr", "", "ncbi-data-policy", "AMRFINDER_DB", 1.0, ("amrfinderplus",), ("amr_surveillance",), "tool-managed", install_command=("amrfinder", "-u"), schema_checks=("amrfinder-db-version",)),
    ReferenceAsset("resfinder-db", "ResFinder database", "amr", "git-commit-pinned", "https://bitbucket.org/genomicepidemiology/resfinder_db.git", "", "source-database-terms", "FASTA/JSON", 0.3, ("resfinder",), ("amr_surveillance",), "git-pinned", schema_checks=("git-commit", "fasta")),
    ReferenceAsset("card", "Comprehensive Antibiotic Resistance Database", "amr", "explicit-release", "https://card.mcmaster.ca/download", "", "card-terms", "FASTA/JSON", 2.0, (), ("amr_surveillance", "one_health_environmental"), "manual-release", schema_checks=("fasta", "json")),
    ReferenceAsset("kraken2-standard", "Kraken 2 Standard database", "metagenomics", "dated-release", "https://benlangmead.github.io/aws-indexes/k2", "", "source-database-terms", "KRAKEN2_DB", 100.0, ("kraken2", "bracken"), ("metagenomics_core", "one_health_environmental", "strain_microbiome"), "manual-release", schema_checks=("kraken2-hash", "taxonomy")),
    ReferenceAsset("humann-chocophlan", "HUMAnN ChocoPhlAn database", "metagenomics", "tool-compatible-release", "https://huttenhower.sph.harvard.edu/humann/", "", "source-database-terms", "HUMANN_DB", 20.0, ("humann",), ("metagenomics_core", "one_health_environmental", "strain_microbiome"), "tool-managed", install_command=("humann_databases", "--download", "chocophlan", "full"), schema_checks=("humann-database",)),
    ReferenceAsset("humann-uniref90", "HUMAnN UniRef90 database", "metagenomics", "tool-compatible-release", "https://huttenhower.sph.harvard.edu/humann/", "", "source-database-terms", "HUMANN_DB", 20.0, ("humann",), ("metagenomics_core", "one_health_environmental", "strain_microbiome"), "tool-managed", install_command=("humann_databases", "--download", "uniref", "uniref90_diamond"), schema_checks=("humann-database",)),
    ReferenceAsset("busco-lineages", "BUSCO lineage datasets", "assembly", "tool-compatible-release", "https://busco.ezlab.org/busco_userguide.html", "", "source-database-terms", "BUSCO_LINEAGE", 15.0, ("busco",), ("long_read_core",), "tool-managed", install_command=("busco", "--download", "all"), schema_checks=("busco-lineage",)),
    ReferenceAsset("igblast-germline", "IgBLAST germline database", "immunoglobulin", "ncbi-current", "https://ftp.ncbi.nih.gov/blast/executables/igblast/release/", "", "ncbi-data-policy", "BLAST_DB", 2.0, ("igblast",), ("antibody_biologics", "cell_therapy_cart"), "manual-release", schema_checks=("blast-db",)),
    ReferenceAsset("dorado-models", "Dorado basecalling models", "long-read", "tool-compatible-release", "https://github.com/nanoporetech/dorado", "", "ont-public-license", "DORADO_MODELS", 100.0, ("dorado",), ("long_read_epigenome",), "tool-managed", install_command=("dorado", "download", "--model", "all"), schema_checks=("dorado-model-list",)),
    ReferenceAsset("colabfold-databases", "ColabFold search databases", "protein-structure", "script-compatible-release", "https://github.com/sokrypton/ColabFold", "", "source-database-terms", "COLABFOLD_DB", 2000.0, ("colabfold",), ("protein_ligand_codesign",), "manual-release", schema_checks=("colabfold-db",)),
    ReferenceAsset("netmhcpan-data", "NetMHCpan stand-alone data package", "immunoinformatics", "authorized-version", "https://services.healthtech.dtu.dk/services/NetMHCpan-4.1/", "", "dtu-academic", "NETMHC_DATA", 1.0, ("netmhcpan",), ("immunoinformatics_vaccine", "proteogenomics_neoantigen"), "manual-authorized", schema_checks=("netmhc-self-test",)),
    ReferenceAsset("netmhciipan-data", "NetMHCIIpan stand-alone data package", "immunoinformatics", "authorized-version", "https://services.healthtech.dtu.dk/services/NetMHCIIpan-4.0/", "", "dtu-academic", "NETMHC_DATA", 1.0, ("netmhciipan",), ("immunoinformatics_vaccine", "proteogenomics_neoantigen"), "manual-authorized", schema_checks=("netmhc-self-test",)),
    ReferenceAsset("proteinmpnn-weights", "ProteinMPNN official model weights", "protein-design", "git-commit-pinned", "https://github.com/dauparas/ProteinMPNN", "", "proteinmpnn-mit", "PYTORCH_WEIGHTS", 1.0, ("proteinmpnn",), ("protein_language_design", "protein_ligand_codesign"), "git-pinned", schema_checks=("pytorch-weight", "known-model-names")),
    ReferenceAsset("rfdiffusion-weights", "RFdiffusion official model weights", "protein-design", "readme-release-pinned", "https://github.com/RosettaCommons/RFdiffusion", "", "rfdiffusion-bsd", "PYTORCH_WEIGHTS", 10.0, ("rfdiffusion",), ("protein_language_design", "protein_ligand_codesign"), "manual-release", schema_checks=("pytorch-weight", "rfdiffusion-config")),
    ReferenceAsset("repeat-expansion-catalog", "Repeat-expansion locus catalogue", "structural-variant", "project-pinned", "https://github.com/Illumina/ExpansionHunter", "", "bioconda-upstream", "JSON", 0.01, ("expansionhunter",), ("structural_variant_repeat",), "manual-release", schema_checks=("json", "locus-catalog")),
)


def reference_catalog() -> pd.DataFrame:
    rows = []
    for item in REFERENCES:
        row = asdict(item)
        for key in ("required_tools", "modules", "install_command", "schema_checks"):
            row[key] = ", ".join(row[key])
        policy = LICENCES[item.licence_id]
        row.update(
            {
                "licence_label": policy.label,
                "licence_terms_url": policy.terms_url,
                "licence_acceptance_mode": policy.acceptance_mode,
                "redistribution_status": policy.redistribution_status,
                "provider_checksum_available": bool(item.checksum_url),
                "local_sha256_required": True,
                "release_pin_required": True,
                "schema_validation_required": True,
                "scientific_review_required": True,
            }
        )
        rows.append(row)
    return pd.DataFrame(rows).sort_values("reference_id").reset_index(drop=True)


def licence_catalog() -> pd.DataFrame:
    return pd.DataFrame([asdict(item) for item in LICENCES.values()]).sort_values("licence_id").reset_index(drop=True)


def canonical_sha256(payload: dict[str, Any]) -> str:
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def engine_manifest(engine: str) -> dict[str, Any]:
    frame = engine_catalog()
    rows = frame.loc[frame["engine"] == engine]
    if rows.empty:
        raise KeyError(engine)
    payload = rows.iloc[0].to_dict()
    payload["schema"] = "biointel.step170.specialist-engine.v1"
    payload["manifest_sha256"] = canonical_sha256(payload)
    return payload


def reference_manifest(reference_id: str) -> dict[str, Any]:
    frame = reference_catalog()
    rows = frame.loc[frame["reference_id"] == reference_id]
    if rows.empty:
        raise KeyError(reference_id)
    payload = rows.iloc[0].to_dict()
    payload["schema"] = "biointel.step170.production-reference.v1"
    payload["manifest_sha256"] = canonical_sha256(payload)
    return payload


__all__ = [
    "LICENCES",
    "REFERENCES",
    "LicencePolicy",
    "ReferenceAsset",
    "canonical_sha256",
    "engine_catalog",
    "engine_manifest",
    "licence_catalog",
    "reference_catalog",
    "reference_manifest",
]
