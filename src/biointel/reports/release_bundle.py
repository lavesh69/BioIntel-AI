from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

from biointel.reports.model_card import build_model_card_markdown
from biointel.training.model_artifact import ModelArtifact


def build_model_release_bundle(artifact: ModelArtifact, model_path: str | Path) -> bytes:
    path = Path(model_path)
    if not path.exists() or path.suffix != ".joblib":
        raise ValueError("A saved .joblib model artifact is required.")
    files = {
        path.name: path.read_bytes(),
        f"{path.stem}.metadata.json": artifact.metadata_json().encode(),
        f"{path.stem}.model_card.md": build_model_card_markdown(artifact).encode(),
        "README.txt": b"BioIntel AI model release bundle\nResearch use only.\n",
    }
    manifest = {name: hashlib.sha256(content).hexdigest() for name, content in files.items()}
    files["MANIFEST_SHA256.json"] = json.dumps(manifest, indent=2, sort_keys=True).encode()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()
