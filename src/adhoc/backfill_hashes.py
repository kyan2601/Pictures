import os
import pandas as pd

from src import constants, helper
from src.classes import media_class_factory
from src.classes.entities.MetadataFile import MetadataFile


def main():
    print("Starting backfill of hashes for pictures.")

    root_dir = constants.ROOT_DIR
    year_dirs = [d for d in os.listdir(root_dir) if os.path.isdir(os.path.join(root_dir, d)) and d.isdigit()]
    all_years = sorted([int(y) for y in year_dirs])
    all_years = [2021]

    for year in all_years:
        print(f"[*] Processing year: {year}")
        try:
            mf = MetadataFile.get_instance(year)
        except Exception as e:
            print(f"Could not get metadata file for year {year}. Error: {e}")
            continue

        if mf.df is None or mf.df.empty:
            print(f"No metadata found for year {year}. Skipping.")
            continue

        # Add new columns from the schema if they are missing
        default_value = pd.NA
        for col in constants.METADATA_COLS:
            if col not in mf.df.columns:
                print(f"  Adding missing column '{col}' with [{default_value}] value.")
                mf.df[col] = default_value

        updated = 0
        for index, row in mf.df.iterrows():
            filepath = row['filepath']
            ext = helper.decompose_filepath(filepath)['ext'].lower()

            if ext in constants.PICTURE_EXTENSIONS:
                if pd.isna(row['dhash']) or not row['dhash']:
                    try:
                        media_entry = media_class_factory.create_media_entry(filepath)
                        new_hash = media_entry._calculate_dhash()
                        if new_hash:
                            mf.df.loc[index, 'dhash'] = new_hash
                            updated += 1
                        else:
                            print(f"    - Warning: hash could not be calculated for {filepath}")
                    except Exception as e:
                        print(f"    - Error processing {filepath}: {e}")

        if updated:
            print(f"[*] Updated {updated} metadata for year {year}")
            mf.write()
        else:
            print(f"No updates needed for year {year}.")

    print("Finished backfill of hashes.")


if __name__ == '__main__':
    main()
