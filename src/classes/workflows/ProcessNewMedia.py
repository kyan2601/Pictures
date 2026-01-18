import os
import glob
import shutil
from collections import Counter

from prettytable import PrettyTable

from src import constants, helper
from src.classes import media_class_factory
from src.classes.entities.MediaEntry import MediaEntry
from src.classes.entities.MetadataFile import MetadataFile


class ProcessNewMedia:
    def __init__(self, verbose=True):
        self.verbose = verbose

    def _delete_dot_underscore_files(self):
        """
        Deletes (moves to backup) all files starting with '._' in the NEW_MEDIA_DIR.
        These are typically AppleDouble files.
        """
        dot_underscore_files = []
        for root, _, files in os.walk(constants.NEW_MEDIA_DIR):
            for file in files:
                if file.startswith('._'):
                    dot_underscore_files.append(os.path.join(root, file))

        if not dot_underscore_files:
            if self.verbose:
                print("[-] No '._' files found in NEW_MEDIA_DIR to process.")
            return

        if self.verbose:
            print(f"[-] Found {len(dot_underscore_files)} '._' files to move to backup.")

        backup_dir = helper.create_backup_directory('delete_dot_underscore_files')
        moved_count = 0
        for filepath in dot_underscore_files:
            try:
                shutil.move(str(filepath), backup_dir)
                moved_count += 1
                if self.verbose:
                    print(f"[-] Moved '._' file to backup: {filepath}")
            except Exception as e:
                print(f"!!! ERROR: Failed to move '._' file {filepath} to backup: {e}")

        if self.verbose:
            print(f"[*] Finished moving {moved_count} '._' files to backup.")

    def _identify_live_photo_movies(self):
        media_filepaths = helper.get_filepaths_by_directory(constants.NEW_MEDIA_DIR, ignore_new_media=False)

        if len(media_filepaths) == 0:
            print('[-] No new files to work with')
            return

        if self.verbose:
            print(f"[-] Found {len(media_filepaths)} new files")

        exts = Counter([filename.rsplit('.', 1)[1].lower() for filename in media_filepaths])

        pt = PrettyTable(['Extension', '# of Files'])
        for ext, count in sorted(exts.items(), key=lambda item: item[1], reverse=True):
            pt.add_row([ext, count])
        if self.verbose:
            print(pt)

        grouped_filenames = {}
        for filepath in media_filepaths:
            fname, ext = filepath.rsplit('.', 1)
            if fname not in grouped_filenames:
                grouped_filenames[fname] = {
                    'picture_extensions': [],
                    'video_extensions': [],
                }
            if ext.lower() in constants.PICTURE_EXTENSIONS:
                grouped_filenames[fname]['picture_extensions'].append(ext.lower())
            elif ext.lower() in constants.VIDEO_EXTENSIONS:
                grouped_filenames[fname]['video_extensions'].append(ext.lower())
            else:
                raise ValueError(f"[!!!] Unknown extension {ext} in {filepath}")

        live_photos = []
        for base_filepath in grouped_filenames.keys():
            if grouped_filenames[base_filepath]['picture_extensions'] and \
                    (constants.VideoExtension.MOV.name.lower() in grouped_filenames[base_filepath]['video_extensions'] or
                     constants.VideoExtension.MOV.value.lower() in grouped_filenames[base_filepath]['video_extensions']):
                # live photo identified; image file is accompanied by an .mov
                live_photos.append(base_filepath)

        if self.verbose:
            print(f"[-] Moving {len(live_photos)} live photo movies to backup...")

        backup_dir = helper.create_backup_directory('live_photo_removal')
        moved_count = 0
        for base_filepath in live_photos:
            ext = constants.VideoExtension.MOV.name.lower() \
                if constants.VideoExtension.MOV.name.lower() in grouped_filenames[base_filepath]['video_extensions'] \
                else constants.VideoExtension.MOV.value.lower()
            mov_filepath = f'{base_filepath}.{ext}'
            if os.path.exists(mov_filepath):
                shutil.move(mov_filepath, backup_dir)
                moved_count += 1
                if self.verbose:
                    print(f'[-] Moved live photo movie to backup: {mov_filepath}')
        if self.verbose:
            print(f'[*] Finished moving {moved_count} live photo movies to backup!')

    def _sort_and_rename_new_pictures(self):
        media_filepaths = helper.get_filepaths_by_directory(constants.NEW_MEDIA_DIR, ignore_new_media=False)

        if len(media_filepaths) == 0:
            print('[-] No new files found to sort')
            return

        if self.verbose:
            print('[-] Found {} files to sort'.format(len(media_filepaths)))
        
        backup_dir = helper.create_backup_directory('sort_and_rename_new_media')

        media = [media_class_factory.create_media_entry(fp) for fp in media_filepaths]

        files_by_date = {}
        for media_obj in media:
            dt = media_obj.dt.date()
            if dt not in files_by_date:
                files_by_date[dt] = []
            files_by_date[dt].append(media_obj)

        for date in files_by_date.keys():
            date_media = sorted(files_by_date[date])

            idx = 1
            date_year = date.year
            date_month = date.month
            path_dir = helper.get_directory_for_year_month(str(date_year), str(date_month))
            os.makedirs(path_dir, exist_ok=True)
            existing_files = glob.glob(os.path.join(path_dir, date.strftime('%y%m%d') + '*'))
            idx += len(existing_files)

            for media_obj in date_media:
                shutil.copy2(media_obj.filepath, backup_dir)
                if self.verbose:
                    print(f'[-] Backed up {media_obj.filepath} to {backup_dir}')

                new_filepath = os.path.join(
                    path_dir,
                    date.strftime('%y%m%d') + str(idx).zfill(3) + '.' + media_obj.ext.value
                )
                if self.verbose:
                    print(f'[-] Moving {media_obj.filepath} to {new_filepath}')
                media_obj.move(new_filepath)
                idx += 1

        if self.verbose:
            print(f'[*] Finished sorting {len(media)} files!')

        return media

    def _index_metadata(self, media: list[MediaEntry]):
        if not media:
            print('[-] No new files to index metadata for')
            return

        media_by_year = {}
        for media_obj in media:
            year = media_obj.dt.year
            if year not in media_by_year:
                media_by_year[year] = []
            media_by_year[year].append(media_obj)

        for year in media_by_year:
            print(f'[-] Updating metadata file for year {year}')
            metadata = [m.to_dict() for m in media_by_year[year]]
            metadata_file = MetadataFile.get_instance(year)

            if os.path.exists(metadata_file.filepath):
                backup_dir = helper.create_backup_directory('index_metadata')
                shutil.copy2(metadata_file.filepath, backup_dir)
                if self.verbose:
                    print(f'[-] Backed up existing metadata.csv for year {year} to {backup_dir}')

            metadata_file.add_media_metadata(metadata)

            if self.verbose:
                print(f'[*] Finished updating metadata!')

    def index_metadata_for_year(self, year):
        year_dir = helper.get_directory_for_year(year)

        if os.path.exists(os.path.join(year_dir, constants.METADATA_FILENAME)):
            print(
                f"[!!!] WARNING: Metadata file already exists for year {year}." +
                " If completely re-indexing, please manually delete file first.")
            return

        filepaths = helper.get_filepaths_by_directory(year_dir)
        media = [media_class_factory.create_media_entry(fp) for fp in filepaths]
        self._index_metadata(media)

    def run(self):
        self._delete_dot_underscore_files()
        self._identify_live_photo_movies()
        media = self._sort_and_rename_new_pictures()
        self._index_metadata(media)
        print("Finished processing new media!")


if __name__ == '__main__':
    ProcessNewMedia().run()
