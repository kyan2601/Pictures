import os
import pandas as pd

from src import constants, helper
from src.classes.MetadataFile import MetadataFile


def identify_overlapping_filenames(metadata_file: MetadataFile) -> bool:
    print(f"[*] Initiating overlapping filename search [{metadata_file.year}]...")
    check_flag = True

    metadata = metadata_file.df.copy()
    metadata['filename_without_ext'] = metadata['filepath'].apply(
        lambda x: helper.decompose_filepath(x)['filename_without_ext'])

    metadata_agg = metadata.groupby(by='filename_without_ext').size().reset_index()
    metadata_agg.columns = ['filename_without_ext', 'count']
    metadata_agg = metadata_agg[metadata_agg['count'] > 1]
    metadata_agg = metadata_agg.sort_values(by=['count', 'filename_without_ext'], ascending=False)

    if len(metadata_agg) > 0:
        print("[!!!] WARNING: Found {} overlapping filenames:".format(len(metadata_agg)))
        print(metadata_agg)
        raise RuntimeError("[!!!] ACTION REQUIRED!")

    print("[-] No overlapping filenames found!")
    print("[*] Finished overlapping filename search!")
    return check_flag


def check_for_deleted_media(metadata_file: MetadataFile, dry_run=False) -> bool:
    print(f"[*] Searching for removed media to clean from metadata [{metadata_file.year}]...")
    check_flag = True

    metadata = metadata_file.df.copy()
    original_size = len(metadata)

    year_dir = helper.get_directory_for_year(metadata_file.year)
    filepaths = helper.get_filepaths_by_directory(year_dir)

    metadata_clean = metadata[metadata['filepath'].isin(filepaths)]
    final_size = len(metadata_clean)

    if original_size == final_size:
        print("[-] Found no removed metadata to clean up!")
        return check_flag

    check_flag = False
    metadata_deleted = metadata[~metadata['filepath'].isin(filepaths)]

    if dry_run:
        print(f"[!] DRY RUN: Would move {len(metadata_deleted)} records to {constants.METADATA_DELETED_FILENAME}")
        print(f"[!] DRY RUN: Would reduce the metadata file from {original_size} to {final_size} rows")
        return check_flag

    deleted_metadata_filepath = os.path.join(helper.get_directory_for_year(metadata_file.year),
                                             constants.METADATA_DELETED_FILENAME)

    if os.path.exists(deleted_metadata_filepath):
        deleted_df = pd.read_csv(str(deleted_metadata_filepath))
        deleted_df['filepath'] = deleted_df['filepath'].apply(lambda x: helper.deserialize_filepath(x))
        deleted_df = pd.concat([deleted_df, metadata_deleted]).drop_duplicates(subset=['filepath'], keep='last')
    else:
        deleted_df = metadata_deleted

    # sort by filepath to have a consistent order
    deleted_df = deleted_df.sort_values(by='filepath')

    # write to deleted metadata file
    deleted_df_to_write = deleted_df.copy()
    deleted_df_to_write['filepath'] = deleted_df_to_write['filepath'].apply(lambda x: helper.serialize_filepath(x))
    deleted_df_to_write = deleted_df_to_write[constants.METADATA_COLS]
    deleted_df_to_write = deleted_df_to_write.replace({None: pd.NA})
    deleted_df_to_write.to_csv(deleted_metadata_filepath, index=False)

    metadata_file.df = metadata_clean
    metadata_file.write()
    print(
        f"[!] check_for_deleted_media() moved {len(metadata_deleted)} records to {constants.METADATA_DELETED_FILENAME}")
    print(f"[!] check_for_deleted_media() reduced the metadata file from {original_size} to {final_size} rows")
    return check_flag


def check_for_unexpected_NAs(metadata_file: MetadataFile) -> bool:
    print(f"[*] Searching for unexpected NAs in metadata [{metadata_file.year}]...")
    check_flag = True

    metadata = metadata_file.df.copy()
    len_metadata = len(metadata)
    unexpected_NA_columns = constants.METADATA_COLS[:4]
    completion_check_cols = constants.METADATA_COLS[4:]

    print(f"[-] Expected columns check [{', '.join(unexpected_NA_columns)}]")
    for col in unexpected_NA_columns:
        metadata_null = metadata[metadata[col].isnull()]
        completion = 1.0 - len(metadata_null) / len_metadata
        print(f"Column: {col} - {completion:.1%}")

        if len(metadata_null) > 0:
            check_flag = False
            print(f"[!!!] WARNING: {len(metadata_null)} records total with NA. Here's a snapshot:")
            print(metadata_null.head())

    print(f"[-] Optional columns check [{', '.join(completion_check_cols)}]")
    for col in completion_check_cols:
        completion = sum(metadata[col].notnull()) / len_metadata
        print(f"Column: {col} - {completion:.1%}")

    return check_flag


def check_for_mismatching_filename_and_datetime(metadata_file: MetadataFile) -> bool:
    print(f"[*] Initiating mismatched filename and datetime search [{metadata_file.year}]...")
    check_flag = True

    metadata = metadata_file.df.copy()
    metadata['filename'] = metadata['filepath'].apply(lambda x: helper.decompose_filepath(x)['filename'])
    metadata['filename_date'] = metadata['filename'].apply(lambda x: helper.decompose_filename(x)['date_obj'])
    metadata['check'] = metadata.apply(lambda x: x['filename_date'] == x['dt'].date(), axis=1)
    metadata = metadata[~metadata['check']]

    if len(metadata) > 0:
        print("[!!!] WARNING: Found {} mismatched filenames and datetimes:".format(len(metadata)))
        print(metadata)
        raise RuntimeError("[!!!] ACTION REQUIRED!")

    print("[-] No mismatched filenames and datetimes found!")
    print("[*] Finished mismatched filename and datetime search!")
    return check_flag


def reorder_media_by_datetime(metadata_file: MetadataFile, dry_run=False) -> bool:
    print(f"[*] Searching for out of order media in year [{metadata_file.year}]...")
    check_flag = True

    metadata = metadata_file.df.copy()

    # extract relevant fields
    metadata['filename'] = metadata['filepath'].apply(
        lambda x: helper.decompose_filepath(x)['filename'])
    metadata['filename_date'] = metadata['filename'].apply(
        lambda x: helper.decompose_filename(x)['date_obj']
    )
    metadata['media_index'] = metadata['filename'].apply(
        lambda x: helper.decompose_filename(x)['media_index']
    )

    # identify correct order
    metadata['dt_index'] = metadata.sort_values(by=['filename_date', 'dt']).groupby(by='filename_date').cumcount() + 1

    # find dates with discrepancies
    records_to_change = metadata[metadata['media_index'] != metadata['dt_index']].copy()
    dates_with_issues = list(records_to_change['filename_date'].unique())
    dates_with_issues = sorted([date.strftime('%Y-%m-%d') for date in dates_with_issues])

    if len(dates_with_issues) == 0:
        print("[-] Did not have to reorder any media indices!")
        return check_flag

    check_flag = False
    print(f"[-] Found {len(dates_with_issues)} dates that need reordering: {', '.join(dates_with_issues)}")

    # reconstruct filename from dt_index instead of media_index
    def _helper_reconstruct_filepath(old_filepath, new_index):
        decomposed_filepath = helper.decompose_filepath(old_filepath)
        dirname = decomposed_filepath['dirname']
        filename = decomposed_filepath['filename']
        decomposed_filename = helper.decompose_filename(filename)

        new_filename = f"{decomposed_filename['date']}{str(new_index).zfill(3)}{'_' + decomposed_filename['title'] if decomposed_filename['title'] else ''}.{decomposed_filename['ext']}"
        return os.path.join(dirname, new_filename)

    records_to_change['new_filepath'] = records_to_change.apply(
        lambda x: _helper_reconstruct_filepath(x['filepath'], x['dt_index']), axis=1)

    path_map = dict(zip(records_to_change['filepath'], records_to_change['new_filepath']))

    # Pre-flight check for collisions with files not in the transaction
    source_paths = set(path_map.keys())
    for old_path, new_path in path_map.items():
        if os.path.exists(new_path) and new_path not in source_paths:
            raise RuntimeError(
                f"[!!!] Aborting reorder: planned rename would overwrite an existing file that is not part of the reorder batch. File: {new_path}")

    print("[-] Making the following changes:")
    print(records_to_change[['filepath', 'new_filepath']])

    if dry_run:
        print(f"[!] DRY RUN: Would rename {len(path_map)} files.")
        return check_flag

    tmp_map = {}
    renamed_to_final_map = {}
    try:
        # --- PHASE 1: RENAME TO TEMPORARY ---
        print("[-] Phase 1/3: Renaming files to temporary names...")
        for old_path, new_path in path_map.items():
            tmp_path = old_path + ".tmp_reorder"
            os.rename(old_path, tmp_path)
            tmp_map[old_path] = tmp_path
        print(f"[-]  - Renamed {len(tmp_map)} files to temporary names.")

        # --- PHASE 2: RENAME TO FINAL ---
        print("[-] Phase 2/3: Renaming temporary files to final names...")
        for old_path, tmp_path in tmp_map.items():
            new_path = path_map[old_path]
            os.rename(tmp_path, new_path)
            renamed_to_final_map[tmp_path] = new_path
        print(f"[-]  - Renamed {len(renamed_to_final_map)} files to their final names.")

        # --- PHASE 3: METADATA UPDATE ---
        print("[-] Phase 3/3: Updating metadata file...")
        new_filepaths = metadata['filepath'].map(path_map).fillna(metadata['filepath'])
        metadata['filepath'] = new_filepaths
        metadata_file.df = metadata[constants.METADATA_COLS]
        metadata_file.write()
        print("[-]  - Metadata file updated successfully.")

        print(f"[*] Finished reordering media for {len(dates_with_issues)} dates!")
        return check_flag

    except Exception as e:
        # --- ROLLBACK ---
        print(f"\n[!!!] ERROR: An error occurred during reordering: {e}")
        print("[!!!] Rolling back changes...")

        # Rollback phase 2 (rename final to temporary)
        for tmp_path, new_path in renamed_to_final_map.items():
            if os.path.exists(new_path):
                os.rename(new_path, tmp_path)

        # Rollback phase 1 (rename temporary to original)
        for old_path, tmp_path in tmp_map.items():
            if os.path.exists(tmp_path):
                os.rename(tmp_path, old_path)

        # Reload the original metadata to discard in-memory changes
        metadata_file.load()
        print(f"[!!!]  - Rolled back all file renames and metadata changes.")

        print("[!!!] Rollback complete.")
        raise


def clean_up_metadata(year, dry_run=True):
    print(f"[*] Initiating metadata cleanup checks for year [{year}]")
    if dry_run:
        print("[!] Running in DRY RUN mode. No changes will be made.")

    metadata_file = MetadataFile.get_instance(year)
    check_flag = True

    check_flag &= identify_overlapping_filenames(metadata_file)
    check_flag &= check_for_deleted_media(metadata_file, dry_run=dry_run)
    check_flag &= check_for_unexpected_NAs(metadata_file)
    check_flag &= check_for_mismatching_filename_and_datetime(metadata_file)
    check_flag &= reorder_media_by_datetime(metadata_file, dry_run=dry_run)

    print('--------------------------------------------------------------------------------------------')
    if check_flag:
        print(f"[*] Metadata checks all within expectations!")
    else:
        print(f"[!!!] WARNING: Metadata checks returned unexpected results. PLEASE REVIEW logs above.")

    return check_flag


########################################################################################################
# DRIVER
########################################################################################################


def main():
    # years_to_check = sorted([int(d) for d in os.listdir(constants.ROOT_DIR) if
    #                          d.isdigit() and os.path.isdir(os.path.join(constants.ROOT_DIR, d))])
    years_to_check = [
        2015,
    ]

    for year in years_to_check:
        check_flag = clean_up_metadata(year, dry_run=True)
        if not check_flag:
            break

    print(f"[*] Finished cleaning up years: {', '.join([str(year) for year in years_to_check])}")


if __name__ == '__main__':
    main()
