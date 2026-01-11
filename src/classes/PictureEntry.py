from abc import ABC
from PIL import Image
import imagehash

from src import constants
from src.classes.MediaEntry import MediaEntry


class PictureEntry(MediaEntry, ABC):

    def __init__(self, filepath):
        super().__init__(filepath)
        self.media_type = constants.MediaType.PICTURE

    def _calculate_phash(self):
        img = Image.open(self.filepath)
        phash = str(imagehash.phash(img))
        return phash
