from abc import ABC

from src import constants
from src.classes.entities.MediaEntry import MediaEntry


class VideoEntry(MediaEntry, ABC):

    def __init__(self, filepath):
        super().__init__(filepath)
        self.media_type = constants.MediaType.VIDEO
