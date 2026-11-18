from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.data.data_packs import write_data_packs  # noqa: E402


def main() -> None:
    records = write_data_packs(ROOT)
    for record in records:
        print(
            f"{record.title}: {record.rows} rows, "
            f"{record.compounds} compounds, "
            f"{record.targets} targets"
        )


if __name__ == "__main__":
    main()
