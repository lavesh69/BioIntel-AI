from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.chemistry.common_compounds import (  # noqa: E402
    load_common_compound_directory,
    write_common_compound_directory,
)


def main() -> None:
    path = write_common_compound_directory(ROOT)
    frame = load_common_compound_directory(ROOT)
    payload = {
        "path": path.relative_to(ROOT).as_posix(),
        "rows": len(frame),
        "unique_smiles": int(frame["canonical_smiles"].nunique()),
        "curated_common_names": int((frame["name_type"] == "curated_common_name").sum()),
        "registry_names": int((frame["name_type"] != "curated_common_name").sum()),
    }
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
