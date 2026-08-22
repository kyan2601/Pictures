import argparse

from src import helper
from src.adhoc.cleanup_backups import main as cleanup_backups_main
from src.classes.workflows.AssignDate import AssignDate
from src.classes.workflows.DuplicateImageCheck import DuplicateImageCheck
from src.classes.workflows.MetadataCleanupChecks import MetadataCleanupChecks
from src.classes.workflows.ProcessNewMedia import ProcessNewMedia


def _process_new(args):
    ProcessNewMedia(dry_run=not args.execute, directory=args.directory).run()


def _cleanup(args):
    for year in args.year:
        MetadataCleanupChecks(year=year).run(dry_run=not args.execute)


def _find_duplicates(args):
    directory = helper.get_directory_for_year_month(args.year, args.month) if args.month \
        else helper.get_directory_for_year(args.year)
    DuplicateImageCheck(directory).run(dry_run=not args.execute)


def _cleanup_backups(args):
    cleanup_backups_main(dry_run=not args.execute, retention_days=args.retention_days)


def _assign_date(args):
    AssignDate(dry_run=not args.execute).run(args.files, args.date)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Pictures file system workflows.")
    subparsers = parser.add_subparsers(dest='command', required=True)

    process_new_parser = subparsers.add_parser(
        'process-new', help="Ingest and sort files from the 'new/' directory.")
    process_new_parser.add_argument(
        '--directory', help="Directory to process (defaults to the whole 'new/' directory).")
    process_new_parser.add_argument('--execute', action='store_true', help='Apply changes (default is dry run).')
    process_new_parser.set_defaults(func=_process_new)

    cleanup_parser = subparsers.add_parser(
        'cleanup', help='Run metadata cleanup checks for one or more years.')
    cleanup_parser.add_argument('--year', type=int, nargs='+', required=True, help='Year(s) to check.')
    cleanup_parser.add_argument('--execute', action='store_true', help='Apply changes (default is dry run).')
    cleanup_parser.set_defaults(func=_cleanup)

    dup_parser = subparsers.add_parser(
        'find-duplicates', help='Find and optionally remove duplicate images.')
    dup_parser.add_argument('--year', type=int, required=True, help='Year to search.')
    dup_parser.add_argument('--month', type=int, help='Month to search (defaults to the whole year).')
    dup_parser.add_argument('--execute', action='store_true', help='Apply changes (default is dry run).')
    dup_parser.set_defaults(func=_find_duplicates)

    cleanup_backups_parser = subparsers.add_parser(
        'cleanup-backups', help='Delete backup directories older than the retention period.')
    cleanup_backups_parser.add_argument(
        '--retention-days', type=int, default=30, help='Age threshold in days (default: 30).')
    cleanup_backups_parser.add_argument('--execute', action='store_true', help='Apply changes (default is dry run).')
    cleanup_backups_parser.set_defaults(func=_cleanup_backups)

    assign_date_parser = subparsers.add_parser(
        'assign-date', help='Assign an explicit date to a batch of files with untrustworthy dates.')
    assign_date_parser.add_argument('--files', nargs='+', required=True, help='Filepaths to assign.')
    assign_date_parser.add_argument('--date', required=True, help='Target date (YYYY-MM-DD).')
    assign_date_parser.add_argument('--execute', action='store_true', help='Apply changes (default is dry run).')
    assign_date_parser.set_defaults(func=_assign_date)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == '__main__':
    main()
