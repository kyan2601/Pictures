import os
import pandas as pd

from src import constants, helper


class MetadataFile:
    _instances = {}

    def __init__(self, year):
        if MetadataFile._get_key(year) in MetadataFile._instances.keys():
            raise RuntimeError("MetadataFile is a singleton class, please call static method get_instance() instead")

        self.year = year
        self.filepath: str = self._get_filepath()
        self.df = None
        self.load()

    @staticmethod
    def _get_key(year):
        return str(year)

    @staticmethod
    def get_instance(year: int):
        key = MetadataFile._get_key(year)
        if key not in MetadataFile._instances.keys():
            MetadataFile._instances[key] = MetadataFile(year)
        return MetadataFile._instances[key]

    def _get_filepath(self) -> str:
        return str(os.path.join(helper.get_directory_for_year(self.year), constants.METADATA_FILENAME))

    def _load_preprocessing(self):
        # try to keep this minimal
        self.df['filepath'] = self.df['filepath'].apply(lambda x: helper.deserialize_filepath(x))
        self.df['dt'] = pd.to_datetime(self.df['dt'])
        # Convert pd.NA/NaN back to None for consistency with Python objects
        # This ensures MediaEntry objects have None instead of pd.NA when loading from CSV
        self.df = self.df.where(pd.notna(self.df), None)

    def load(self):
        if not os.path.exists(self.filepath):
            dirname = helper.decompose_filepath(self.filepath)['dirname']
            os.makedirs(dirname, exist_ok=True)

            self.df = pd.DataFrame([], columns=constants.METADATA_COLS)
            self.write()
        else:
            self.df = pd.read_csv(self.filepath)
            self._load_preprocessing()

    def _write_preprocessing(self) -> pd.DataFrame:
        # try to keep this minimal
        df = self.df.copy()
        df['filepath'] = df['filepath'].apply(lambda x: helper.serialize_filepath(x))
        df = df[constants.METADATA_COLS]
        # Convert None values to pd.NA so CSV writes empty cells instead of "None"
        df = df.replace({None: pd.NA})
        return df

    def write(self):
        if self.df is None:
            raise RuntimeError(f"Tried to write out metadata file [{self.year}] but dataframe is None")

        df = self._write_preprocessing()
        df.to_csv(self.filepath, index=False)

    def has_media_metadata(self, filepath):
        return not self.df[self.df['filepath'] == filepath].empty

    def get_media_metadata(self, filepath):
        if not self.has_media_metadata(filepath):
            return {}
        return self.df[self.df['filepath'] == filepath].iloc[0].to_dict()

    def add_media_metadata(self, metadata: dict | list, update=False, write=True):
        if update:
            # default to new metadata so remove "stale" records
            if isinstance(metadata, dict):
                self.df = self.df[self.df['filepath'] != metadata['filepath']]
            elif isinstance(metadata, list):
                remove_df = pd.DataFrame(metadata, columns=constants.METADATA_COLS)
                self.df = self.df[~self.df['filepath'].isin(remove_df['filepath'])]

        additional_df = pd.DataFrame([], columns=constants.METADATA_COLS)
        if isinstance(metadata, dict):
            if 'filepath' not in metadata:
                raise RuntimeError(f"Could not add [{metadata}] to {self}")
            if self.has_media_metadata(metadata['filepath']):
                raise RuntimeError(
                    f"Filepath [{metadata['filepath']}] already exists in {self} during add. Please make sure update=True if you want this change to override existing metadata.")
            additional_df = pd.DataFrame([metadata], columns=constants.METADATA_COLS)
        elif isinstance(metadata, list):
            additional_df = pd.DataFrame(metadata, columns=constants.METADATA_COLS)
            if additional_df['filepath'].isnull().any():
                raise RuntimeError(f"Could not add [{metadata}] to {self}")
            overlapping_df = additional_df[additional_df['filepath'].isin(self.df['filepath'])]
            if not overlapping_df.empty:
                raise RuntimeError(f"{len(overlapping_df)} records already exist in {self}. Please make sure update=True if you want this change to override existing metadata.")
        else:
            raise RuntimeError(f"Not sure how to add metadata of type [{type(metadata)}]")

        if self.df is None or self.df.empty:
            self.df = additional_df
        else:
            self.df = pd.concat([self.df, additional_df]).sort_values(by='dt')

        if write:
            self.write()

    def __str__(self):
        return f"MetadataFile(year={self.year})"
