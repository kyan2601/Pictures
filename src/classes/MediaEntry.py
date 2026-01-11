import os
from abc import ABC, abstractmethod

from src import constants, helper
from src.classes.MetadataFile import MetadataFile


class MediaEntry(ABC):

    def __init__(self, filepath):
        self.filepath = filepath
        self.dt = None
        self.metadata_file: MetadataFile | None = None
        # Initialize all metadata fields to None
        self.width = None
        self.height = None
        self.latitude = None
        self.longitude = None
        self.altitude = None
        self.orientation = None
        self.title = None
        self.tags = None
        self.people = None
        self.comments = None
        self.event_id = None
        self.is_highlight = 0
        self.phash = None
        self.norm_pixel_hash = None
        self.load()

    def _get_metadata_file(self):
        folder_year = helper.get_year_from_filepath(self.filepath)
        self.metadata_file = MetadataFile.get_instance(folder_year)

    def _metadata_exists(self):
        return self.metadata_file.has_media_metadata(self.filepath)

    def _load_metadata(self):
        metadata = self.metadata_file.get_media_metadata(self.filepath)
        for k, v in metadata.items():
            if k not in ['filepath']:
                setattr(self, k, v)

    @abstractmethod
    def _extract_metadata(self):
        pass

    def load(self):
        if not helper.is_new_media(self.filepath):
            self._get_metadata_file()

        if self.metadata_file and self._metadata_exists():
            self._load_metadata()
        else:
            self._extract_metadata()

    def to_dict(self):
        return {k: v for k, v in vars(self).items() if k in constants.METADATA_COLS}

    def __str__(self):
        return f"MediaEntry({self.filepath})"

    def __lt__(self, other):
        return self.dt < other.dt

    def __gt__(self, other):
        return self.dt > other.dt

    def __eq__(self, other):
        return self.filepath == other.filepath and self.dt == other.dt
