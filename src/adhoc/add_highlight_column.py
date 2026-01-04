import os
import pandas as pd
from src import constants


def main():
    """
    This script migrates existing metadata.csv files to include the 'is_highlight' column.
    It iterates through all year directories, reads the metadata.csv, adds the new
    column with a default value of 0 if it doesn't exist, and re-orders the columns
    to match the schema in constants.py.
    """
    print("Starting migration to add 'is_highlight' column to metadata files.")

    # Discover all directories in the root that are named with years
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
            df = pd.read_csv(metadata_file)

            # Add 'is_highlight' column if it doesn't exist
            if 'is_highlight' not in df.columns:
                print("  'is_highlight' column not found. Adding it with default value 0.")
                df['is_highlight'] = 0
            else:
                print("  'is_highlight' column already exists. Filling missing values with 0.")
                df['is_highlight'] = df['is_highlight'].fillna(0)

            # Ensure the new column is of integer type
            df['is_highlight'] = df['is_highlight'].astype(int)

            # Add any other missing columns from the official schema
            for col in constants.METADATA_COLS:
                if col not in df.columns:
                    print(f"  Adding missing column '{col}' with NA value.")
                    df[col] = pd.NA

            # Reorder columns to match the canonical list and drop any extras
            # that might have been added by mistake in the past.
            df = df[constants.METADATA_COLS]

            # Save the updated dataframe
            df.to_csv(metadata_file, index=False)
            print(f"Finished processing year [{year}]")

        except Exception as e:
            print(f"Error processing file {metadata_file}: {e}")

    print("\nMigration complete.")


if __name__ == '__main__':
    main()
