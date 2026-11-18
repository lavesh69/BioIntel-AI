from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pandas as pd

# In-memory table parsing intentionally stays bounded.  The shared Streamlit
# preflight accepts files up to 1 GB and stages larger inputs before this
# function is called.
INTERACTIVE_UPLOAD_BYTES = 100 * 1024 * 1024
SUPPORTED_SUFFIXES = {'.csv', '.tsv', '.txt', '.xlsx', '.xls', '.json'}


def read_upload(name: str, payload: bytes) -> pd.DataFrame:
    if len(payload) > INTERACTIVE_UPLOAD_BYTES:
        raise ValueError('Interactive planning preview is limited to 100 MB; use the 1 GB staged background upload flow.')
    suffix = Path(name).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ValueError(f'Unsupported planning file type: {suffix or "unknown"}')
    bio = BytesIO(payload)
    if suffix == '.csv':
        frame = pd.read_csv(bio, low_memory=False)
    elif suffix in {'.tsv', '.txt'}:
        frame = pd.read_csv(bio, sep='\t', low_memory=False)
    elif suffix in {'.xlsx', '.xls'}:
        frame = pd.read_excel(bio, sheet_name=0)
    else:
        frame = pd.read_json(bio)
    if frame.columns.duplicated().any():
        duplicates = sorted(set(map(str, frame.columns[frame.columns.duplicated()])))
        raise ValueError('Duplicate columns are not allowed: ' + ', '.join(duplicates))
    if frame.shape[1] > 500:
        raise ValueError('Input contains more than 500 columns; simplify the planning table before import.')
    return frame
