import argparse

from src import helper
from src.classes.workflows.DuplicateImageCheck import DuplicateImageCheck
from src.classes.workflows.MetadataCleanupChecks import MetadataCleanupChecks
from src.classes.workflows.ProcessNewMedia import ProcessNewMedia


def _process_new(args):
    ProcessNewMedia(dry_run=not args.execute).run()


def _cleanup(args):
    for year in args.year:
        MetadataCleanupChecks(year=year).run(dry_run=not args.execute)


def _find_duplicates(args):
    directory = helper.get_directory_for_year_month(args.year, args.month) if args.month \
        else helper.get_directory_for_year(args.year)
    DuplicateImageCheck(directory).run(dry_run=not args.execute)


def main():
    parser = argparse.ArgumentParser(description="Pictures file system workflows.")
    subparsers = parser.add_subparsers(dest='command', required=True)

    process_new_parser = subparsers.add_parser(
        'process-new', help="Ingest and sort files from the 'new/' directory.")
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

    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
