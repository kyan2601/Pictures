import os
import shutil
from collections import defaultdict

import pandas as pd

from src import helper
from src.classes.entities.EventsMetadataFile import EventsMetadataFile
from src.classes.entities.MetadataFile import MetadataFile


class AssignEvent:
    """Moves library files into an existing event's folder and sets event_id.

    Files must already be ingested (present in a yearly metadata.csv).
    Originals are moved to a timestamped backup directory after the copies
    land in the event folder and metadata is updated.
    """

    def __init__(self, dry_run=True):
        self.dry_run = dry_run

    @staticmethod
    def _is_unassigned(event_id_value):
        return event_id_value is None or (isinstance(event_id_value, float) and pd.isna(event_id_value)) \
            or (isinstance(event_id_value, str) and event_id_value.strip() == '')

    def run(self, files, event_id):
        event = EventsMetadataFile.get_instance().get_event(event_id)
        event_dir = event.get_directory()

        # 1. Validate everything and build the move plan first.
        moves = []  # (filepath, year, new_filepath, record)
        records_by_year = defaultdict(list)
        for filepath in files:
            year = helper.get_year_from_filepath(filepath)
            metadata_file = MetadataFile.get_instance(year)
            if not metadata_file.has_media_metadata(filepath):
                print(f'  [skip] no metadata record for {filepath}')
                continue
            record = metadata_file.get_media_metadata(filepath)
            if not self._is_unassigned(record.get('event_id')):
                existing = int(record['event_id'])
                if existing == int(event_id):
                    print(f'  [skip] already in event {event_id}: {filepath}')
                    continue
                raise RuntimeError(
                    f'{filepath} already belongs to event {existing}; '
                    f'unassign it before moving it to event {event_id}.')

            new_filepath = os.path.join(event_dir, os.path.basename(filepath))
            if os.path.abspath(new_filepath) == os.path.abspath(filepath):
                print(f'  [skip] already in the event directory: {filepath}')
                continue
            if os.path.exists(new_filepath):
                raise RuntimeError(
                    f'Cannot move {filepath}: {new_filepath} already exists '
                    f'(name collision inside the event directory).')

            record['filepath'] = new_filepath
            record['event_id'] = int(event_id)
            moves.append((filepath, year, new_filepath))
            records_by_year[year].append(record)

        if not moves:
            print('No files to assign.')
            return

        if self.dry_run:
            print(f'[dry run] would move {len(moves)} file(s) into event '
                  f'{event_id} [{event.title}] at {event_dir}')
            for filepath, _, new_filepath in moves:
                print(f'  [dry run] {filepath} -> {new_filepath}')
            return

        # 2. Copy into the event directory; roll back copies on failure before
        #    anything else has changed.
        os.makedirs(event_dir, exist_ok=True)
        copied = []
        try:
            for filepath, _, new_filepath in moves:
                shutil.copy2(filepath, new_filepath)
                copied.append(new_filepath)
        except Exception:
            for path in copied:
                try:
                    os.remove(path)
                except OSError:
                    pass
            raise
        print(f'Copied {len(copied)} file(s) into {event_dir}')

        # 3. Update metadata (one write per affected year).
        for year, records in sorted(records_by_year.items()):
            metadata_file = MetadataFile.get_instance(year)
            for record in records:
                metadata_file.add_media_metadata(record, update=True, write=False)
            metadata_file.write()
        print(f'Updated metadata for {len(moves)} file(s) across '
              f'{len(records_by_year)} year(s)')

        # 4. Originals go to backup, now that copies + metadata are in place.
        backup_dir = helper.create_backup_directory('assign_event')
        for filepath, _, _ in moves:
            shutil.move(filepath, backup_dir)
        print(f'Moved {len(moves)} original(s) to backup: {backup_dir}')
