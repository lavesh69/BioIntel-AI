from __future__ import annotations

"""Standalone worker used by isolated BioIntel scientific runtimes.

The worker intentionally avoids importing the BioIntel application package. It
accepts one JSON request and writes one JSON result, allowing dependency-heavy
scientific environments to remain isolated from the desktop application's core.
"""

import argparse
import json
import math
from pathlib import Path
import sys
import traceback
from typing import Any


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return None
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_value(item) for item in value]
    if hasattr(value, "item"):
        try:
            return _json_value(value.item())
        except Exception:
            pass
    if hasattr(value, "tolist"):
        try:
            return _json_value(value.tolist())
        except Exception:
            pass
    return str(value)


def _required(payload: dict[str, Any], key: str) -> Any:
    value = payload.get(key)
    if value is None or value == "" or value == []:
        raise ValueError(f"Required BioIntel input is missing: {key}")
    return value


def _sequence_records(payload: dict[str, Any]):
    from Bio import SeqIO
    from Bio.Seq import Seq
    from Bio.SeqRecord import SeqRecord

    path = str(payload.get("input_path", "")).strip()
    text = str(payload.get("sequence", "")).strip()
    if path:
        with Path(path).open("r", encoding="utf-8", errors="replace") as handle:
            return list(SeqIO.parse(handle, payload.get("format", "fasta")))
    if not text:
        raise ValueError("A sequence or FASTA file is required.")
    if text.startswith(">"):
        from io import StringIO

        return list(SeqIO.parse(StringIO(text), "fasta"))
    return [SeqRecord(Seq("".join(text.split())), id="biointel_input")]


def sequence_intelligence(operation: str, payload: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    from Bio.SeqUtils import gc_fraction

    records = _sequence_records(payload)
    lengths = [len(record.seq) for record in records]
    gc_values = [round(gc_fraction(str(record.seq)) * 100.0, 4) for record in records if len(record.seq)]
    metrics = {
        "records": len(records),
        "total_length": sum(lengths),
        "minimum_length": min(lengths) if lengths else 0,
        "maximum_length": max(lengths) if lengths else 0,
        "mean_gc_percent": round(sum(gc_values) / len(gc_values), 4) if gc_values else 0.0,
    }
    return {"metrics": metrics, "message": "BioIntel sequence analysis completed."}


def variant_file_intelligence(operation: str, payload: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    import pysam

    path = Path(_required(payload, "input_path"))
    limit = int(payload.get("max_records", 100000))
    suffix = path.suffix.casefold()
    if suffix in {".bam", ".sam", ".cram"} or operation == "alignment_summary":
        mode = "rb" if suffix != ".sam" else "r"
        count = mapped = unmapped = 0
        with pysam.AlignmentFile(str(path), mode) as handle:
            references = list(handle.references)
            for record in handle.fetch(until_eof=True):
                count += 1
                if record.is_unmapped:
                    unmapped += 1
                else:
                    mapped += 1
                if count >= limit:
                    break
        metrics = {"file_type": "alignment", "records_scanned": count, "mapped": mapped, "unmapped": unmapped, "references": len(references)}
    else:
        count = 0
        variant_types: dict[str, int] = {}
        with pysam.VariantFile(str(path)) as handle:
            samples = list(handle.header.samples)
            contigs = list(handle.header.contigs)
            for record in handle.fetch():
                count += 1
                ref_len = len(record.ref or "")
                alt_lengths = [len(str(alt)) for alt in (record.alts or ())]
                if any(length != ref_len for length in alt_lengths):
                    kind = "indel"
                else:
                    kind = "substitution"
                variant_types[kind] = variant_types.get(kind, 0) + 1
                if count >= limit:
                    break
        metrics = {"file_type": "variant", "records_scanned": count, "samples": len(samples), "contigs": len(contigs), "variant_classes": variant_types}
    return {"metrics": metrics, "message": "BioIntel genomic file analysis completed."}


def biological_statistics(operation: str, payload: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    import numpy as np
    from skbio import DistanceMatrix
    from skbio.diversity import alpha_diversity, beta_diversity

    matrix = np.asarray(_required(payload, "matrix"), dtype=float)
    if matrix.ndim != 2 or matrix.shape[0] < 1 or matrix.shape[1] < 1:
        raise ValueError("BioIntel expects a non-empty two-dimensional abundance matrix.")
    ids = [str(value) for value in payload.get("sample_ids", [f"sample_{index+1}" for index in range(matrix.shape[0])])]
    if len(ids) != matrix.shape[0]:
        raise ValueError("Sample identifier count must match matrix rows.")
    if operation == "distance_matrix":
        metric = str(payload.get("metric", "braycurtis"))
        distance: DistanceMatrix = beta_diversity(metric, matrix, ids)
        metrics = {"metric": metric, "samples": matrix.shape[0], "features": matrix.shape[1], "distance_matrix": distance.data.round(6).tolist()}
    else:
        metric = str(payload.get("metric", "shannon"))
        values = alpha_diversity(metric, matrix, ids)
        metrics = {"metric": metric, "samples": matrix.shape[0], "features": matrix.shape[1], "values": {str(index): float(value) for index, value in values.items()}}
    return {"metrics": metrics, "message": "BioIntel biological statistics completed."}


def _anndata_from_payload(payload: dict[str, Any]):
    import anndata as ad
    import numpy as np

    path = str(payload.get("input_path", "")).strip()
    if path:
        return ad.read_h5ad(path)
    matrix = np.asarray(_required(payload, "matrix"), dtype=float)
    if matrix.ndim != 2:
        raise ValueError("Single-cell matrix must be two-dimensional.")
    return ad.AnnData(matrix)


def single_cell_analysis(operation: str, payload: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    import numpy as np
    import scanpy as sc

    adata = _anndata_from_payload(payload)
    if adata.n_obs < 2 or adata.n_vars < 2:
        raise ValueError("Single-cell analysis requires at least two cells and two features.")
    sc.pp.calculate_qc_metrics(adata, inplace=True, percent_top=None, log1p=False)
    metrics: dict[str, Any] = {
        "cells": int(adata.n_obs),
        "features": int(adata.n_vars),
        "median_counts_per_cell": float(np.median(adata.obs["total_counts"])),
        "median_features_per_cell": float(np.median(adata.obs["n_genes_by_counts"])),
    }
    if operation == "single_cell_embedding":
        target_sum = float(payload.get("target_sum", 10000.0))
        sc.pp.normalize_total(adata, target_sum=target_sum)
        sc.pp.log1p(adata)
        components = min(int(payload.get("components", 10)), adata.n_obs - 1, adata.n_vars - 1)
        if components >= 2:
            sc.pp.pca(adata, n_comps=components)
            metrics["embedding_components"] = int(adata.obsm["X_pca"].shape[1])
            metrics["variance_ratio"] = np.asarray(adata.uns["pca"]["variance_ratio"][:components]).round(6).tolist()
    return {"metrics": metrics, "message": "BioIntel single-cell analysis completed."}


def single_cell_ai(operation: str, payload: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    import numpy as np
    import scvi

    metrics: dict[str, Any] = {"runtime_available": True, "accelerator": "auto"}
    if operation == "single_cell_latent":
        import anndata as ad

        matrix = np.asarray(_required(payload, "matrix"), dtype=float)
        if matrix.ndim != 2 or matrix.shape[0] < 4 or matrix.shape[1] < 4:
            raise ValueError("BioIntel latent modelling requires at least four cells and four features.")
        adata = ad.AnnData(matrix)
        scvi.model.SCVI.setup_anndata(adata)
        model = scvi.model.SCVI(adata, n_latent=min(int(payload.get("latent_dimensions", 5)), matrix.shape[1] - 1))
        epochs = max(1, min(int(payload.get("epochs", 1)), 50))
        model.train(max_epochs=epochs, accelerator="auto", devices="auto", enable_progress_bar=False)
        latent = model.get_latent_representation()
        metrics.update({"cells": matrix.shape[0], "features": matrix.shape[1], "latent_shape": list(latent.shape), "epochs": epochs})
        output_dir.mkdir(parents=True, exist_ok=True)
        latent_path = output_dir / "biointel_single_cell_latent.csv"
        np.savetxt(latent_path, latent, delimiter=",")
        return {"metrics": metrics, "artifacts": [str(latent_path)], "message": "BioIntel single-cell latent modelling completed."}
    return {"metrics": metrics, "message": "BioIntel single-cell AI runtime diagnostic passed."}


def multiomics_integration(operation: str, payload: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    import anndata as ad
    import muon as mu
    import numpy as np

    path = str(payload.get("input_path", "")).strip()
    if path:
        data = mu.read_h5mu(path)
    else:
        modalities = _required(payload, "modalities")
        if not isinstance(modalities, dict) or len(modalities) < 2:
            raise ValueError("At least two omics modalities are required.")
        data = mu.MuData({name: ad.AnnData(np.asarray(values, dtype=float)) for name, values in modalities.items()})
    shapes = {name: [int(mod.n_obs), int(mod.n_vars)] for name, mod in data.mod.items()}
    shared_obs = len(data.obs_names)
    metrics = {"modalities": len(shapes), "modality_shapes": shapes, "shared_observations": shared_obs}
    return {"metrics": metrics, "message": "BioIntel multi-omics container validation completed."}


def spatial_omics(operation: str, payload: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    import numpy as np
    import squidpy as sq

    adata = _anndata_from_payload(payload)
    coordinates = np.asarray(_required(payload, "spatial_coordinates"), dtype=float)
    if coordinates.ndim != 2 or coordinates.shape[0] != adata.n_obs or coordinates.shape[1] < 2:
        raise ValueError("Spatial coordinates must provide x/y values for every observation.")
    adata.obsm["spatial"] = coordinates[:, :2]
    sq.gr.spatial_neighbors(adata, coord_type="generic", n_neighs=max(2, min(int(payload.get("neighbors", 6)), adata.n_obs - 1)))
    matrix = adata.obsp["spatial_connectivities"]
    metrics = {"observations": int(adata.n_obs), "features": int(adata.n_vars), "spatial_edges": int(matrix.nnz), "coordinate_dimensions": 2}
    return {"metrics": metrics, "message": "BioIntel spatial-neighbour analysis completed."}


def molecular_intelligence(operation: str, payload: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    from rdkit import Chem, DataStructs
    from rdkit.Chem import Crippen, Descriptors, Lipinski, rdFingerprintGenerator

    smiles = str(_required(payload, "smiles"))
    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        raise ValueError("BioIntel could not parse the molecular representation.")
    metrics: dict[str, Any] = {
        "canonical_smiles": Chem.MolToSmiles(molecule),
        "molecular_weight": round(float(Descriptors.MolWt(molecule)), 4),
        "logp": round(float(Crippen.MolLogP(molecule)), 4),
        "h_bond_donors": int(Lipinski.NumHDonors(molecule)),
        "h_bond_acceptors": int(Lipinski.NumHAcceptors(molecule)),
        "rotatable_bonds": int(Lipinski.NumRotatableBonds(molecule)),
    }
    if operation == "fingerprint":
        generator = rdFingerprintGenerator.GetMorganGenerator(radius=int(payload.get("radius", 2)), fpSize=int(payload.get("size", 2048)))
        fingerprint = generator.GetFingerprint(molecule)
        metrics["fingerprint_bits"] = int(fingerprint.GetNumBits())
        metrics["fingerprint_on_bits"] = int(fingerprint.GetNumOnBits())
        comparison = str(payload.get("comparison_smiles", "")).strip()
        if comparison:
            other = Chem.MolFromSmiles(comparison)
            if other is None:
                raise ValueError("BioIntel could not parse the comparison molecule.")
            metrics["tanimoto_similarity"] = round(float(DataStructs.TanimotoSimilarity(fingerprint, generator.GetFingerprint(other))), 6)
    return {"metrics": metrics, "message": "BioIntel molecular intelligence completed."}


def molecular_ai(operation: str, payload: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    import deepchem as dc
    import numpy as np

    if operation == "model_diagnostic":
        return {"metrics": {"runtime_available": True, "supported_input": "molecular representations"}, "message": "BioIntel molecular AI runtime diagnostic passed."}
    smiles = payload.get("smiles")
    if isinstance(smiles, str):
        smiles = [smiles]
    if not smiles:
        raise ValueError("At least one molecular representation is required.")
    featurizer = dc.feat.CircularFingerprint(size=int(payload.get("size", 1024)), radius=int(payload.get("radius", 2)))
    features = np.asarray(featurizer.featurize(list(map(str, smiles))))
    metrics = {"molecules": int(features.shape[0]), "feature_dimensions": int(features.shape[1]), "nonzero_features": [int(np.count_nonzero(row)) for row in features]}
    return {"metrics": metrics, "message": "BioIntel molecular AI featurization completed."}


def molecular_simulation(operation: str, payload: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    import openmm
    from openmm import unit

    platforms = [openmm.Platform.getPlatform(index).getName() for index in range(openmm.Platform.getNumPlatforms())]
    if operation == "simulation_diagnostic":
        return {"metrics": {"runtime_available": True, "platforms": platforms}, "message": "BioIntel simulation runtime diagnostic passed."}
    system = openmm.System()
    system.addParticle(39.9 * unit.amu)
    force = openmm.CustomExternalForce("0.5*k*(x*x+y*y+z*z)")
    force.addGlobalParameter("k", 100.0 * unit.kilojoule_per_mole / unit.nanometer**2)
    force.addParticle(0, [])
    system.addForce(force)
    integrator = openmm.VerletIntegrator(0.001 * unit.picoseconds)
    context = openmm.Context(system, integrator)
    context.setPositions([[0.1, 0.0, 0.0]] * unit.nanometer)
    openmm.LocalEnergyMinimizer.minimize(context, maxIterations=max(1, min(int(payload.get("iterations", 20)), 1000)))
    state = context.getState(getEnergy=True, getPositions=True)
    energy = state.getPotentialEnergy().value_in_unit(unit.kilojoule_per_mole)
    positions = state.getPositions(asNumpy=True).value_in_unit(unit.nanometer)
    del context, integrator
    return {"metrics": {"platforms": platforms, "potential_energy_kj_mol": round(float(energy), 8), "final_position_nm": positions.round(8).tolist()}, "message": "BioIntel energy minimization completed."}


def trajectory_analysis(operation: str, payload: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    import MDAnalysis as mda
    import numpy as np

    topology = str(payload.get("topology_path", "")).strip()
    trajectory = str(payload.get("trajectory_path", "")).strip()
    if not topology:
        return {"metrics": {"runtime_available": True}, "message": "BioIntel trajectory runtime diagnostic passed."}
    universe = mda.Universe(topology, trajectory) if trajectory else mda.Universe(topology)
    metrics: dict[str, Any] = {"atoms": int(universe.atoms.n_atoms), "residues": int(universe.residues.n_residues), "frames": int(len(universe.trajectory))}
    if operation == "rmsd":
        from MDAnalysis.analysis import rms

        analysis = rms.RMSD(universe, universe, select=str(payload.get("selection", "backbone"))).run()
        values = np.asarray(analysis.results.rmsd)
        metrics["rmsd_mean"] = float(np.mean(values[:, 2])) if values.size else 0.0
        metrics["rmsd_max"] = float(np.max(values[:, 2])) if values.size else 0.0
    return {"metrics": metrics, "message": "BioIntel trajectory analysis completed."}


def protein_language(operation: str, payload: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    import esm

    if operation == "protein_model_diagnostic":
        available = [name for name in dir(esm.pretrained) if name.startswith("esm2_")]
        return {"metrics": {"runtime_available": True, "registered_model_adapters": len(available), "asset_download_allowed": False}, "message": "BioIntel protein-language runtime diagnostic passed; model assets remain qualification-gated."}
    model_path = str(_required(payload, "model_path"))
    sequence = str(_required(payload, "sequence")).replace(" ", "").replace("\n", "")
    if not Path(model_path).is_file():
        raise ValueError("A locally qualified BioIntel protein model asset is required.")
    model, alphabet = esm.pretrained.load_model_and_alphabet_local(model_path)
    model.eval()
    batch_converter = alphabet.get_batch_converter()
    _, _, tokens = batch_converter([("biointel_input", sequence)])
    layer = int(payload.get("representation_layer", getattr(model, "num_layers", 0)))
    with __import__("torch").no_grad():
        result = model(tokens, repr_layers=[layer], return_contacts=False)
    representation = result["representations"][layer][0, 1 : len(sequence) + 1].mean(0).cpu().numpy()
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "biointel_protein_embedding.csv"
    __import__("numpy").savetxt(path, representation[None, :], delimiter=",")
    return {"metrics": {"sequence_length": len(sequence), "embedding_dimensions": int(representation.shape[0]), "representation_layer": layer}, "artifacts": [str(path)], "message": "BioIntel protein embedding completed."}


def pathway_intelligence(operation: str, payload: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    import gseapy as gp
    import pandas as pd

    ranking = _required(payload, "ranking")
    if isinstance(ranking, dict):
        ranking_frame = pd.DataFrame({"gene": list(ranking), "score": list(ranking.values())})
    else:
        ranking_frame = pd.DataFrame(ranking, columns=["gene", "score"])
    gene_sets = _required(payload, "gene_sets")
    output_dir.mkdir(parents=True, exist_ok=True)
    result = gp.prerank(
        rnk=ranking_frame,
        gene_sets=gene_sets,
        outdir=None,
        permutation_num=max(10, min(int(payload.get("permutations", 100)), 10000)),
        seed=int(payload.get("seed", 7)),
        min_size=max(2, int(payload.get("min_size", 2))),
        max_size=max(5, int(payload.get("max_size", 5000))),
        verbose=False,
    )
    frame = result.res2d.reset_index()
    output = output_dir / "biointel_pathway_results.csv"
    frame.to_csv(output, index=False)
    top = frame.head(int(payload.get("top_terms", 20))).to_dict(orient="records")
    return {"metrics": {"ranked_genes": int(len(ranking_frame)), "pathways_tested": int(len(frame)), "top_results": top}, "artifacts": [str(output)], "message": "BioIntel offline pathway analysis completed."}


def medical_imaging_ai(operation: str, payload: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    import monai
    import numpy as np
    import torch
    from monai.transforms import Compose, EnsureChannelFirst, ScaleIntensity, Resize

    if operation == "model_diagnostic":
        return {"metrics": {"runtime_available": True, "accelerator_available": bool(torch.cuda.is_available())}, "message": "BioIntel medical-imaging AI runtime diagnostic passed."}
    array = np.asarray(_required(payload, "array"), dtype=np.float32)
    spatial_size = tuple(int(value) for value in payload.get("spatial_size", [64, 64]))
    transforms = Compose([EnsureChannelFirst(channel_dim="no_channel"), ScaleIntensity(), Resize(spatial_size=spatial_size)])
    result = transforms(array)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "biointel_preprocessed_image.npy"
    np.save(path, result.detach().cpu().numpy() if hasattr(result, "detach") else np.asarray(result))
    return {"metrics": {"input_shape": list(array.shape), "output_shape": list(result.shape), "accelerator_available": bool(torch.cuda.is_available())}, "artifacts": [str(path)], "message": "BioIntel medical-image preprocessing completed."}


def bioimaging_workspace(operation: str, payload: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    import napari

    return {"metrics": {"runtime_available": True, "viewer_mode": "desktop companion"}, "message": "BioIntel imaging workspace diagnostic passed."}


HANDLERS = {
    "sequence_intelligence": sequence_intelligence,
    "variant_file_intelligence": variant_file_intelligence,
    "biological_statistics": biological_statistics,
    "single_cell_analysis": single_cell_analysis,
    "single_cell_ai": single_cell_ai,
    "multiomics_integration": multiomics_integration,
    "spatial_omics": spatial_omics,
    "molecular_intelligence": molecular_intelligence,
    "molecular_ai": molecular_ai,
    "molecular_simulation": molecular_simulation,
    "trajectory_analysis": trajectory_analysis,
    "protein_language": protein_language,
    "pathway_intelligence": pathway_intelligence,
    "medical_imaging_ai": medical_imaging_ai,
    "bioimaging_workspace": bioimaging_workspace,
}


DIAGNOSTIC_MODULES = {
    "sequence_intelligence": "Bio",
    "variant_file_intelligence": "pysam",
    "biological_statistics": "skbio",
    "single_cell_analysis": "scanpy",
    "single_cell_ai": "scvi",
    "multiomics_integration": "muon",
    "spatial_omics": "squidpy",
    "molecular_intelligence": "rdkit",
    "molecular_ai": "deepchem",
    "molecular_simulation": "openmm",
    "trajectory_analysis": "MDAnalysis",
    "protein_language": "esm",
    "pathway_intelligence": "gseapy",
    "medical_imaging_ai": "monai",
    "bioimaging_workspace": "napari",
}


def _technical_diagnostic(integration_id: str) -> dict[str, Any]:
    import importlib
    import importlib.metadata
    import platform

    module_name = DIAGNOSTIC_MODULES.get(integration_id)
    if not module_name:
        raise ValueError("No Python diagnostic is registered for this BioIntel integration.")
    module = importlib.import_module(module_name)
    version = getattr(module, "__version__", None)
    return {
        "schema": "biointel.integration-worker-result.v2",
        "status": "completed",
        "message": "BioIntel runtime diagnostic passed.",
        "metrics": {
            "runtime_available": True,
            "runtime_version": str(version or "managed"),
            "python": platform.python_version(),
        },
        "artifacts": [],
    }


def run(request: dict[str, Any]) -> dict[str, Any]:
    integration_id = str(request.get("integration_id", ""))
    operation = str(request.get("operation", ""))
    payload = request.get("payload", {})
    if not isinstance(payload, dict):
        raise ValueError("BioIntel integration payload must be a JSON object.")
    output_dir = Path(str(request.get("output_dir", "artifacts"))).expanduser().resolve()
    if operation == "technical_diagnostic":
        return _technical_diagnostic(integration_id)
    if integration_id not in HANDLERS:
        raise ValueError("This BioIntel integration is not assigned to the Python worker.")
    output_dir.mkdir(parents=True, exist_ok=True)
    result = HANDLERS[integration_id](operation, payload, output_dir)
    return {
        "schema": "biointel.integration-worker-result.v2",
        "status": "completed",
        "message": str(result.get("message", "BioIntel scientific operation completed.")),
        "metrics": _json_value(result.get("metrics", {})),
        "artifacts": _json_value(result.get("artifacts", [])),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args()
    try:
        request = json.loads(args.request.read_text(encoding="utf-8"))
        result = run(request)
        code = 0
    except Exception as exc:
        result = {
            "schema": "biointel.integration-worker-result.v2",
            "status": "failed",
            "message": str(exc) if isinstance(exc, ValueError) else "BioIntel scientific worker failed safely.",
            "metrics": {},
            "artifacts": [],
            "internal_error": {"type": type(exc).__name__, "traceback": traceback.format_exc()},
        }
        code = 1
    args.result.parent.mkdir(parents=True, exist_ok=True)
    args.result.write_text(json.dumps(_json_value(result), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
