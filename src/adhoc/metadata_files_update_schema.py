import os
import pandas as pd

from src import constants, helper


def main():
    years = [
        # 2015,
        # 2019,
        # 2020,
        # 2021,
        # 2022,
        # 2023,
        # 2024,
        # 2025,
    ]

    for year in years:
        metadata_file = str(os.path.join(helper.get_directory_for_year(year), constants.METADATA_FILENAME))
        df = pd.read_csv(metadata_file)
        df['width'] = df['width'].astype(int)
        df['height'] = df['height'].astype(int)

        # add new columns
        for col in constants.METADATA_COLS:
            if col not in df.columns:
                df[col] = pd.NA

        df = df[constants.METADATA_COLS]
        df.to_csv(metadata_file, index=False)
        print(f"Finished processing year [{year}]")


if __name__ == '__main__':
    main()
