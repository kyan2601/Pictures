import argparse
import os

from src import constants, helper
from src.adhoc.cleanup_backups import main as cleanup_backups_main
from src.classes.entities.EventsMetadataFile import EventsMetadataFile
from src.classes.workflows.AnnotateMedia import AnnotateMedia
from src.classes.workflows.AssignDate import AssignDate
from src.classes.workflows.AssignEvent import AssignEvent
from src.classes.workflows.DuplicateImageCheck import DuplicateImageCheck
from src.classes.workflows.GallerySite import GallerySite
from src.classes.workflows.LibraryStats import LibraryStats
from src.classes.workflows.MetadataCleanupChecks import MetadataCleanupChecks
from src.classes.workflows.ProcessNewMedia import ProcessNewMedia
from src.classes.workflows.SearchMedia import SearchMedia


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


def _mark_reviewed(args):
    page_path = os.path.join(constants.REVIEW_DIR, args.category, f'{args.page}.html')
    GallerySite(constants.REVIEW_DIR).mark_reviewed(page_path)
    print(f'Marked as reviewed: {page_path}')


def _annotate(args):
    AnnotateMedia(dry_run=not args.execute).run(
        args.files, title=args.title, tags=args.tags, people=args.people,
        comments=args.comments, is_highlight=args.is_highlight)


def _create_event(args):
    events_file = EventsMetadataFile.get_instance()
    if not args.execute:
        event, media_df = events_file.preview_event(
            title=args.title, start_date=args.start_date, end_date=args.end_date,
            nominal_month=args.nominal_month)
        print(f'[dry run] would create event {event.event_id} [{event.title}]')
        print(f'[dry run] event directory: {event.get_directory()}')
        print(f'[dry run] {len(media_df)} media file(s) in range would move '
              f'into the event directory')
        return
    event = events_file.create_event(
        title=args.title, start_date=args.start_date, end_date=args.end_date,
        description=args.description, nominal_month=args.nominal_month,
        backup=not args.no_backup)
    print(event)


def _assign_event(args):
    AssignEvent(dry_run=not args.execute).run(args.files, args.event_id)


def _search(args):
    SearchMedia().run(
        years=args.year, tags=args.tags, people=args.people, title=args.title,
        comments=args.comments, event_id=args.event_id, is_highlight=args.highlight,
        start_date=args.start_date, end_date=args.end_date, limit=args.limit)


def _stats(args):
    LibraryStats().run(years=args.year)


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

    mark_reviewed_parser = subparsers.add_parser(
        'mark-reviewed', help='Mark a review page as reviewed.')
    mark_reviewed_parser.add_argument(
        '--category', required=True, help="Review category (e.g. 'duplicate-check').")
    mark_reviewed_parser.add_argument('--page', required=True, help="Page id (e.g. '2022-05').")
    mark_reviewed_parser.set_defaults(func=_mark_reviewed)

    annotate_parser = subparsers.add_parser(
        'annotate', help='Edit metadata annotations (title, tags, people, comments, highlight).')
    annotate_parser.add_argument(
        '--files', nargs='+', required=True, help='Filepaths to annotate (as listed in metadata.csv).')
    annotate_parser.add_argument('--title', help='Set the title.')
    annotate_parser.add_argument('--tags', help='Set tags (comma- or semicolon-separated).')
    annotate_parser.add_argument('--people', help='Set people (comma- or semicolon-separated).')
    annotate_parser.add_argument('--comments', help='Set comments.')
    highlight_group = annotate_parser.add_mutually_exclusive_group()
    highlight_group.add_argument(
        '--highlight', dest='is_highlight', action='store_true', default=None,
        help='Mark as highlight.')
    highlight_group.add_argument(
        '--no-highlight', dest='is_highlight', action='store_false',
        help='Unmark highlight.')
    annotate_parser.add_argument('--execute', action='store_true', help='Apply changes (default is dry run).')
    annotate_parser.set_defaults(func=_annotate)

    create_event_parser = subparsers.add_parser(
        'create-event', help='Create an event and move in-range media into its folder.')
    create_event_parser.add_argument('--title', required=True, help='Event title.')
    create_event_parser.add_argument('--start-date', required=True, help='Start date (YYYY-MM-DD).')
    create_event_parser.add_argument('--end-date', required=True, help='End date (YYYY-MM-DD).')
    create_event_parser.add_argument('--description', help='Event description.')
    create_event_parser.add_argument('--nominal-month', help='Month name for the folder (defaults to the start month).')
    create_event_parser.add_argument(
        '--no-backup', action='store_true',
        help='Skip the backup step (originals are deleted instead of moved to backup).')
    create_event_parser.add_argument('--execute', action='store_true', help='Apply changes (default is dry run).')
    create_event_parser.set_defaults(func=_create_event)

    assign_event_parser = subparsers.add_parser(
        'assign-event', help="Move files into an existing event's folder and set their event_id.")
    assign_event_parser.add_argument(
        '--files', nargs='+', required=True, help='Filepaths to assign (as listed in metadata.csv).')
    assign_event_parser.add_argument('--event-id', type=int, required=True, help='Target event id.')
    assign_event_parser.add_argument('--execute', action='store_true', help='Apply changes (default is dry run).')
    assign_event_parser.set_defaults(func=_assign_event)

    search_parser = subparsers.add_parser(
        'search', help='Search metadata across years (read-only).')
    search_parser.add_argument(
        '--year', type=int, nargs='*', help='Year(s) to search (defaults to all years).')
    search_parser.add_argument('--tags', help='Tags to match (comma- or semicolon-separated, any match).')
    search_parser.add_argument('--people', help='People to match (comma- or semicolon-separated, any match).')
    search_parser.add_argument('--title', help='Case-insensitive substring match on title.')
    search_parser.add_argument('--comments', help='Case-insensitive substring match on comments.')
    search_parser.add_argument('--event-id', type=int, help='Only media in this event.')
    search_parser.add_argument('--highlight', action='store_true', help='Only highlights.')
    search_parser.add_argument('--start-date', help='Only media on/after this date (YYYY-MM-DD).')
    search_parser.add_argument('--end-date', help='Only media on/before this date (YYYY-MM-DD).')
    search_parser.add_argument('--limit', type=int, help='Max results to show.')
    search_parser.set_defaults(func=_search)

    stats_parser = subparsers.add_parser(
        'stats', help='Print library statistics (read-only).')
    stats_parser.add_argument(
        '--year', type=int, nargs='*', help='Year(s) to include (defaults to all years).')
    stats_parser.set_defaults(func=_stats)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == '__main__':
    main()
