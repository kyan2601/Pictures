import os
import pandas as pd

from src import constants, helper, media_class_controller
from src.classes.MetadataFile import MetadataFile


def main():
    print("Starting backfill of phash for pictures.")

    root_dir = constants.ROOT_DIR
    year_dirs = [d for d in os.listdir(root_dir) if os.path.isdir(os.path.join(root_dir, d)) and d.isdigit()]
    all_years = sorted([int(y) for y in year_dirs])

    picture_extensions = [e.lower() for e in constants.PICTURE_EXTENSIONS]

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
            
        updated = 0
        for index, row in mf.df.iterrows():
            filepath = row['filepath']
            ext = helper.decompose_filepath(filepath)['ext'].lower()

            if ext in picture_extensions:
                if pd.isna(row['phash']) or not row['phash']:
                    try:
                        media_entry = media_class_controller.create_media_entry(filepath)
                        phash = media_entry._calculate_phash()
                        if phash:
                            mf.df.loc[index, 'phash'] = phash
                            updated += 1
                        else:
                            print(f"    - Warning: phash could not be calculated for {filepath}")
                    except Exception as e:
                        print(f"    - Error processing {filepath}: {e}")

        if updated:
            print(f"[*] Updated {updated} metadata for year {year}")
            mf.write()
        else:
            print(f"No updates needed for year {year}.")

    print("Finished backfill of phash.")


if __name__ == '__main__':
    main()
