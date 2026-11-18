from __future__ import annotations

import argparse
import getpass
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.security.passwords import hash_password  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a BioIntel UI user JSON entry.")
    parser.add_argument("username")
    parser.add_argument("--display-name", default="")
    parser.add_argument("--role", choices=["admin", "researcher", "reviewer"], default="admin")
    args = parser.parse_args()
    password = getpass.getpass("Credential (minimum 12 characters): ")
    confirmation = getpass.getpass("Confirm credential: ")
    if password != confirmation:
        raise SystemExit("Passwords do not match.")
    record = {
        args.username.strip().lower(): {
            "display_name": args.display_name.strip() or args.username.strip(),
            "role": args.role,
            "password_hash": hash_password(password),
        }
    }
    print(json.dumps(record, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
