from src import constants
from src.classes.JPEGPictureEntry import JPEGPictureEntry


class JPGPictureEntry(JPEGPictureEntry):
    # copy of JPEGPictureEntry, just with different extension

    def __init__(self, filepath):
        super().__init__(filepath)
        self.ext = constants.PictureExtension.JPG
