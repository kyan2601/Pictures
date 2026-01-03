from abc import ABC

from src import constants
from src.classes.MediaEntry import MediaEntry


class PictureEntry(MediaEntry, ABC):

    def __init__(self, filepath):
        super().__init__(filepath)
        self.media_type = constants.MediaType.PICTURE
