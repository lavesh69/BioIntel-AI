from __future__ import annotations

import argparse
import json
from pathlib import Path

from biointel.production.user_data import create_backup, merge_seed_tree, restore_backup, validate_backup


def main() -> int:
    parser = argparse.ArgumentParser(description="BioIntel AI persistent UserData migration and backup utility.")
    sub = parser.add_subparsers(dest="command", required=True)
    backup = sub.add_parser("backup")
    backup.add_argument("user_data")
    backup.add_argument("backup_parent")
    backup.add_argument("--label", default="manual")
    validate = sub.add_parser("validate")
    validate.add_argument("backup")
    restore = sub.add_parser("restore")
    restore.add_argument("backup")
    restore.add_argument("user_data")
    merge = sub.add_parser("merge-seed")
    merge.add_argument("source")
    merge.add_argument("destination")
    args = parser.parse_args()
    if args.command == "backup":
        print(create_backup(args.user_data, args.backup_parent, label=args.label))
    elif args.command == "validate":
        result = validate_backup(args.backup)
        print(json.dumps(result.to_dict(), indent=2))
        return 0 if result.valid else 1
    elif args.command == "restore":
        print(json.dumps(restore_backup(args.backup, args.user_data), indent=2))
    elif args.command == "merge-seed":
        print(json.dumps(merge_seed_tree(args.source, args.destination), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
