import os
import glob
from collections import Counter

from prettytable import PrettyTable

from src import constants, helper, media_class_controller
from src.classes.MediaEntry import MediaEntry
from src.classes.MetadataFile import MetadataFile


def identify_live_photo_movies(remove=False, verbose=True):
    media_filepaths = helper.get_filepaths_by_directory(constants.NEW_MEDIA_DIR, ignore_new_media=False)

    if len(media_filepaths) == 0:
        print('[-] No new files to work with')
        return

    if verbose:
        print(f"[-] Found {len(media_filepaths)} new files")

    exts = Counter([filename.rsplit('.', 1)[1].lower() for filename in media_filepaths])

    pt = PrettyTable(['Extension', '# of Files'])
    for ext, count in sorted(exts.items(), key=lambda item: item[1], reverse=True):
        pt.add_row([ext, count])
    if verbose:
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

    if verbose:
        print("[-] Found {} live photos".format(len(live_photos)))

    if remove:
        for base_filepath in live_photos:
            ext = constants.VideoExtension.MOV.name.lower() \
                if constants.VideoExtension.MOV.name.lower() in grouped_filenames[base_filepath]['video_extensions'] \
                else constants.VideoExtension.MOV.value.lower()
            mov_filepath = f'{base_filepath}.{ext}'
            if os.path.exists(mov_filepath):
                os.remove(mov_filepath)
                if verbose:
                    print(f'[-] Removed live photo movie: {mov_filepath}')

    if verbose:
        print(f'[*] Finished removing {len(live_photos)} live photo movies!')


def sort_and_rename_new_pictures(verbose=True):
    media_filepaths = helper.get_filepaths_by_directory(constants.NEW_MEDIA_DIR, ignore_new_media=False)

    if len(media_filepaths) == 0:
        print('[-] No new files found to sort')
        return

    if verbose:
        print('[-] Found {} files to sort'.format(len(media_filepaths)))

    media = [media_class_controller.create_media_entry(fp) for fp in media_filepaths]

    # organize by date
    files_by_date = {}
    for media_obj in media:
        dt = media_obj.dt.date()
        if dt not in files_by_date:
            files_by_date[dt] = []
        files_by_date[dt].append(media_obj)

    # move and rename photos into filesystem
    for date in files_by_date.keys():
        date_media = sorted(files_by_date[date])

        # identify any existing files on date
        idx = 1
        date_year = date.year
        date_month = date.month
        path_dir = helper.get_directory_for_year_month(str(date_year), str(date_month))
        os.makedirs(path_dir, exist_ok=True)
        existing_files = glob.glob(os.path.join(path_dir, date.strftime('%y%m%d') + '*'))
        idx += len(existing_files)

        for media_obj in date_media:
            new_filepath = os.path.join(
                path_dir,
                date.strftime('%y%m%d') + str(idx).zfill(3) + '.' + media_obj.ext.value
            )
            if verbose:
                print(f'[-] Moving {media_obj.filepath} to {new_filepath}')
            media_obj.move(new_filepath)
            idx += 1

    if verbose:
        print(f'[*] Finished sorting {len(media)} files!')

    return media


def index_metadata(media: list[MediaEntry], verbose=True):
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
        metadata_file.add_media_metadata(metadata)

        if verbose:
            print(f'[*] Finished updating metadata!')


def index_metadata_for_year(year):
    # typically used after deleting metadata file for year to completely reindex the year
    year_dir = helper.get_directory_for_year(year)

    if os.path.exists(os.path.join(year_dir, constants.METADATA_FILENAME)):
        print(
            f"[!!!] WARNING: Metadata file already exists for year {year}." +
            " If completely re-indexing, please manually delete file first.")
        return

    filepaths = helper.get_filepaths_by_directory(year_dir)
    media = [media_class_controller.create_media_entry(fp) for fp in filepaths]
    index_metadata(media, verbose=True)


def process_new_media(verbose=True):
    identify_live_photo_movies(remove=True, verbose=verbose)
    media = sort_and_rename_new_pictures(verbose=verbose)
    index_metadata(media, verbose=verbose)
    print("Finished processing new media!")


def main():
    process_new_media()


if __name__ == '__main__':
    main()
