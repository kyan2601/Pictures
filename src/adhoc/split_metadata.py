from src import constants, helper

import os
import pandas as pd


def main(consolidated_file=os.path.join(constants.SOURCE_DIR, 'metadata_consolidated.csv')):
    consolidated_df = pd.read_csv(consolidated_file)

    # drop lake_tahoe_collage
    consolidated_df.drop(0, inplace=True)

    consolidated_df['year'] = consolidated_df['filepath'].apply(lambda x: helper.get_year_from_filepath(x))
    consolidated_df['filepath'] = consolidated_df['filepath'].apply(lambda x: helper.serialize_filepath(x))

    # clean up column types
    consolidated_df['width'] = consolidated_df['width'].astype(int)
    consolidated_df['height'] = consolidated_df['height'].astype(int)

    for year in consolidated_df['year'].unique():
        df_year = consolidated_df[consolidated_df['year'] == year].copy()
        df_year.drop(columns='year', inplace=True)
        metadata_filepath = os.path.join(helper.get_directory_for_year(year), constants.METADATA_FILENAME)
        df_year.to_csv(metadata_filepath, index=False)
        print(f"Wrote out metadata for year {year} at {metadata_filepath}")


if __name__ == '__main__':
    main()
