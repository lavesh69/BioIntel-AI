from __future__ import annotations

from io import BytesIO

from rdkit.Chem import Draw
from rdkit.Chem.rdchem import Mol


def molecule_png(mol: Mol, width: int = 700, height: int = 420) -> bytes:
    """Render a molecule as PNG bytes for Streamlit and report exports."""

    image = Draw.MolToImage(mol, size=(width, height))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
