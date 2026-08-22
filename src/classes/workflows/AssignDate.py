import glob
import os
import re
import shutil
from datetime import datetime, timedelta

from src import constants, helper
from src.classes import media_class_factory
from src.classes.entities.MetadataFile import MetadataFile

_SEQUENCE_NUMBER_PATTERN = re.compile(r'(\d+)\s+of\s+\d+', re.IGNORECASE)
_NATURAL_SORT_CHUNK_PATTERN = re.compile(r'(\d+)')


def _sequence_number(filepath):
    match = _SEQUENCE_NUMBER_PATTERN.search(os.path.basename(filepath))
    return int(match.group(1)) if match else None


def _natural_sort_key(filepath):
    filename = os.path.basename(filepath)
    return [int(chunk) if chunk.isdigit() else chunk.lower()
            for chunk in _NATURAL_SORT_CHUNK_PATTERN.split(filename)]


class AssignDate:
    """
    Assigns an explicit date to a batch of files whose real capture date can't be
    trusted (missing/unreliable EXIF and filesystem timestamps). Relative order within
    the batch is preserved via synthetic same-day timestamps one second apart, so
    filename indices and metadata.csv 'dt' values still sort the same way the files
    were originally ordered.
    """

    def __init__(self, dry_run=True):
        self.dry_run = dry_run
        self.run_log = []
        self.media = []

    def _print_and_log(self, message):
        print(message)
        self.run_log.append(message)

    def _filter_supported_media(self, filepaths):
        filtered = []
        for filepath in filepaths:
            filename = os.path.basename(filepath)
            if filename.startswith('._'):
                continue
            if '.' not in filename:
                continue
            ext = filename.rsplit('.', 1)[1].lower()
            if ext not in constants.MEDIA_EXTENSIONS:
                continue
            filtered.append(filepath)
        return filtered

    def _split_out_live_photo_movies(self, filepaths):
        live_photo_movies = set(helper.identify_live_photo_movies(filepaths))
        remaining = [fp for fp in filepaths if fp not in live_photo_movies]
        return remaining, sorted(live_photo_movies)

    def _remove_live_photo_movies(self, live_photo_movies):
        if not live_photo_movies:
            return

        if self.dry_run:
            self._print_and_log(f"DRY RUN: Would move {len(live_photo_movies)} live photo movies to backup")
            return

        backup_dir = helper.create_backup_directory('live_photo_removal')
        moved_count = 0
        for filepath in live_photo_movies:
            try:
                shutil.move(filepath, backup_dir)
                moved_count += 1
                print(f'[-] Moved live photo movie to backup: {filepath}')
            except (OSError, shutil.Error) as e:
                print(f"!!! ERROR: Failed to move live photo movie {filepath} to backup: {e}")

        self._print_and_log(f"Moved {moved_count} live photo movies to backup.")

    def _order(self, filepaths):
        if not filepaths:
            return []

        sequence_numbers = {fp: _sequence_number(fp) for fp in filepaths}
        if all(n is not None for n in sequence_numbers.values()):
            self._print_and_log(f"Ordering {len(filepaths)} files by embedded 'N of TOTAL' sequence numbers.")
            return sorted(filepaths, key=lambda fp: sequence_numbers[fp])

        self._print_and_log(f"Ordering {len(filepaths)} files by natural filename sort.")
        return sorted(filepaths, key=_natural_sort_key)

    def run(self, filepaths, date):
        target_date = datetime.strptime(date, '%Y-%m-%d').date()

        filtered = self._filter_supported_media(filepaths)
        remaining, live_photo_movies = self._split_out_live_photo_movies(filtered)
        self._remove_live_photo_movies(live_photo_movies)

        ordered_filepaths = self._order(remaining)
        if not ordered_filepaths:
            self._print_and_log("No matching media files to assign.")
            return

        print(f"[-] Assigning {len(ordered_filepaths)} files to {target_date.isoformat()}")
        self.media = [media_class_factory.create_media_entry(fp) for fp in ordered_filepaths]

        # Synthetic same-day timestamps, one second apart, preserve the batch's
        # relative order without claiming any particular time of day is real.
        base_dt = datetime.combine(target_date, datetime.min.time()) + timedelta(seconds=1)
        for i, media_obj in enumerate(self.media):
            media_obj.dt = base_dt + timedelta(seconds=i)

        path_dir = helper.get_directory_for_year_month(str(target_date.year), str(target_date.month))
        if not os.path.exists(path_dir):
            if not self.dry_run:
                os.makedirs(path_dir, exist_ok=True)
            else:
                print(f"DRY RUN: Would create directory {path_dir}")

        existing_files = glob.glob(os.path.join(path_dir, target_date.strftime('%y%m%d') + '*')) \
            if os.path.exists(path_dir) else []
        idx = 1 + max(
            [0] + [helper.decompose_filename(helper.decompose_filepath(fp)['filename'])['media_index']
                   for fp in existing_files])

        backup_dir = None
        if not self.dry_run:
            backup_dir = helper.create_backup_directory('assign_date')
            for media_obj in self.media:
                shutil.copy2(media_obj.filepath, backup_dir)
            print(f"Backed up {len(self.media)} files to {backup_dir}")

        for media_obj in self.media:
            new_filepath = os.path.join(
                path_dir,
                target_date.strftime('%y%m%d') + str(idx).zfill(3) + '.' + media_obj.ext.value
            )
            if not self.dry_run:
                print(f'[-] Moving {media_obj.filepath} to {new_filepath}')
                media_obj.move(new_filepath)
            else:
                print(f"DRY RUN: Would move {media_obj.filepath} to {new_filepath}")
            idx += 1

        self._print_and_log(f"Finished assigning {len(self.media)} files to {target_date.isoformat()}.")

        if self.dry_run:
            self._print_and_log(f"DRY RUN: Would update metadata for year {target_date.year}")
            return

        print(f'[-] Updating metadata file for year {target_date.year}')
        metadata = [m.to_dict() for m in self.media]
        metadata_file = MetadataFile.get_instance(target_date.year)

        if os.path.exists(metadata_file.filepath):
            metadata_backup_dir = helper.create_backup_directory('assign_date_index_metadata')
            shutil.copy2(metadata_file.filepath, metadata_backup_dir)

        metadata_file.add_media_metadata(metadata)
        self._print_and_log(f"Finished updating metadata for {len(self.media)} files.")
