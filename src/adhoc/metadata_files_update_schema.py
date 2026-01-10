import os
import pandas as pd

from src import constants


def main():
    """
    This script migrates existing metadata.csv files to the latest schema.
    It iterates through all year directories, reads the metadata.csv, adds any
    missing columns, and re-orders them to match the schema in constants.py.
    """
    print("Starting migration of metadata files to the latest schema.")

    try:
        year_dirs = [d for d in os.listdir(constants.ROOT_DIR) if
                     d.isdigit() and os.path.isdir(os.path.join(constants.ROOT_DIR, d))]
        print(f"Found year directories: {year_dirs}")
    except FileNotFoundError:
        print(f"Error: Root directory '{constants.ROOT_DIR}' not found. Aborting.")
        return

    for year in year_dirs:
        metadata_file = os.path.join(constants.ROOT_DIR, year, constants.METADATA_FILENAME)

        if not os.path.exists(metadata_file):
            print(f"No metadata file found for year {year}, skipping.")
            continue

        try:
            print(f"Processing {metadata_file}...")
            df = pd.read_csv(str(metadata_file))

            # Handle width and height types
            if 'width' in df.columns:
                df['width'] = df['width'].astype(int)
            if 'height' in df.columns:
                df['height'] = df['height'].astype(int)

            # Add new columns from the schema if they are missing
            for col in constants.METADATA_COLS:
                if col not in df.columns:
                    if col == 'is_highlight':
                        print("  'is_highlight' column not found. Adding it with default value 0.")
                        df[col] = 0
                    else:
                        print(f"  Adding missing column '{col}' with NA value.")
                        df[col] = pd.NA
            
            # Ensure 'is_highlight' is int and fill any potential NA values from other operations
            if 'is_highlight' in df.columns:
                df['is_highlight'] = df['is_highlight'].fillna(0).astype(int)

            # Reorder columns to match the canonical list and drop any extras
            df = df[constants.METADATA_COLS]

            # Save the updated dataframe
            df.to_csv(metadata_file, index=False)
            print(f"Finished processing year [{year}]")

        except Exception as e:
            print(f"Error processing file {metadata_file}: {e}")

    print("\nMigration complete.")


if __name__ == '__main__':
    main()
