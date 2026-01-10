from src import constants

import os
import sys
import argparse
import shutil
from collections import defaultdict
from datetime import datetime, timedelta

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


def main():
    """
    Scans the backup directory and removes backups older than a specified number of days.
    """
    parser = argparse.ArgumentParser(
        description="Clean up old event backups.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "--retention-days",
        type=int,
        default=30,
        help="The number of days to keep backups. Backups older than this will be deleted. Default is 30."
    )
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--dry-run",
        action="store_true",
        help="Scan and report which backups would be deleted without actually deleting them."
    )
    mode_group.add_argument(
        "--execute",
        action="store_true",
        help="Actually delete the old backups."
    )
    args = parser.parse_args()

    if not os.path.isdir(constants.BACKUP_DIR):
        print(f"INFO: Backup directory not found at '{constants.BACKUP_DIR}'. Nothing to do.")
        return

    print(f"Scanning backup directory: {constants.BACKUP_DIR}")
    print(f"Retention policy: {args.retention_days} days")
    if args.dry_run:
        print("Mode: Dry Run (no files will be deleted)")
    else:
        print("Mode: Execute (files will be deleted)")

    now = datetime.now()
    retention_delta = timedelta(days=args.retention_days)
    backups_found = 0
    backups_to_delete_grouped = defaultdict(list)

    for dirname in os.listdir(constants.BACKUP_DIR):
        backup_path = os.path.join(constants.BACKUP_DIR, dirname)
        if not os.path.isdir(backup_path):
            continue

        backups_found += 1
        try:
            # Expected format: YYYYMMDDHHMMSS_[action_type]
            parts = dirname.split('_', 1) # Split only on the first underscore
            timestamp_str = parts[0]
            action_type = parts[1] if len(parts) > 1 else "unknown_action"
            backup_time = datetime.strptime(timestamp_str, '%Y%m%d%H%M%S')

            if now - backup_time > retention_delta:
                backups_to_delete_grouped[action_type].append((dirname, backup_path))
        except (ValueError, IndexError):
            print(f"WARNING: Could not parse timestamp from directory name '{dirname}'. Skipping.")
            continue

    if not backups_found:
        print("\nNo backups found.")
        return

    total_to_delete = sum(len(v) for v in backups_to_delete_grouped.values())
    if not total_to_delete:
        print(f"\nFound {backups_found} backups, none of which are older than {args.retention_days} days.")
        return

    print(f"\nFound {total_to_delete} backups to delete (older than {args.retention_days} days):")
    for action_type, backups in backups_to_delete_grouped.items():
        print(f"  Action Type: {action_type} ({len(backups)} backups)")
        for dirname, _ in backups:
            print(f"    - {dirname}")

    if args.execute:
        print("\nProceeding with deletion...")
        deleted_count = 0
        try:
            for action_type, backups in backups_to_delete_grouped.items():
                print(f"  Deleting backups for action type: {action_type}")
                for dirname, backup_path in backups:
                    print(f"    - Deleting {backup_path}...")
                    shutil.rmtree(backup_path)
                    deleted_count += 1
            print(f"\nSuccessfully deleted {deleted_count} backups.")
        except Exception as e:
            print(f"\nERROR: An error occurred during deletion: {e}")
            print("Some backups may not have been deleted.")

    print("\nCleanup script finished.")


if __name__ == '__main__':
    main()
