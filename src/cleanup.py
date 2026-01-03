import os

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
        check_flag = False
        print("[!!!] WARNING: Found {} overlapping filenames:".format(len(metadata_agg)))
        print(metadata_agg)
        raise RuntimeError("[!!!] ACTION REQUIRED!")

    print("[-] No overlapping filenames found!")
    print("[*] Finished overlapping filename search!")
    return check_flag


def check_for_deleted_media(metadata_file: MetadataFile) -> bool:
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
    metadata_file.df = metadata_clean
    metadata_file.write()
    print(f"[-] check_for_deleted_media() reduced the metadata file from {original_size} to {final_size} rows")
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
        check_flag = False
        print("[!!!] WARNING: Found {} mismatched filenames and datetimes:".format(len(metadata)))
        print(metadata)
        raise RuntimeError("[!!!] ACTION REQUIRED!")

    print("[-] No mismatched filenames and datetimes found!")
    print("[*] Finished mismatched filename and datetime search!")
    return check_flag


def reorder_media_by_datetime(metadata_file: MetadataFile) -> bool:
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
    dates_with_issues = list(metadata[metadata['media_index'] != metadata['dt_index']]['filename_date'].unique())
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

    metadata['new_filepath'] = metadata.apply(
        lambda x: _helper_reconstruct_filepath(x['filepath'], x['dt_index']), axis=1)

    def _helper_construct_temp_filepath(filepath):
        decomposed_filepath = helper.decompose_filepath(filepath)
        dirname = decomposed_filepath['dirname']
        filename = decomposed_filepath['filename']
        return os.path.join(dirname, 'tmp_' + filename)

    metadata['tmp_filepath'] = metadata['filepath'].apply(lambda x: _helper_construct_temp_filepath(x))

    print("[-] Making the following changes:")
    records_to_change = metadata[metadata['media_index'] != metadata['dt_index']]
    print(records_to_change[['filepath', 'new_filepath']])

    # temporary rename to avoid collisions
    for _, row in records_to_change.iterrows():
        os.rename(row['filepath'], row['tmp_filepath'])

    # final renames
    for _, row in records_to_change.iterrows():
        os.rename(row['tmp_filepath'], row['new_filepath'])

    # update metadata file
    metadata['filepath'] = metadata['new_filepath']
    metadata_file.df = metadata[constants.METADATA_COLS]
    metadata_file.write()

    print(f"[*] Finished reordering media for {len(dates_with_issues)} dates!")
    return check_flag


def clean_up_metadata(year):
    print(f"[*] Initiating metadata cleanup checks for year [{year}]")
    metadata_file = MetadataFile.get_instance(year)
    check_flag = True

    check_flag &= identify_overlapping_filenames(metadata_file)
    check_flag &= check_for_deleted_media(metadata_file)
    check_flag &= check_for_unexpected_NAs(metadata_file)
    check_flag &= check_for_mismatching_filename_and_datetime(metadata_file)
    check_flag &= reorder_media_by_datetime(metadata_file)

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
    years_to_check = [
        2025
    ]

    for year in years_to_check:
        check_flag = clean_up_metadata(year)
        if not check_flag:
            break

    print(f"[*] Finished cleaning up years: {', '.join([str(year) for year in years_to_check])}")


if __name__ == '__main__':
    main()
