import os
from datetime import datetime

import PIL.Image

from src import constants, helper
from src.classes.entities.PictureEntry import PictureEntry


class PNGPictureEntry(PictureEntry):

    def __init__(self, filepath):
        super().__init__(filepath)
        self.ext = constants.PictureExtension.PNG

    def _extract_metadata(self):
        image = PIL.Image.open(self.filepath)
        image.load()

        self.dt = datetime.fromtimestamp(os.path.getctime(self.filepath))
        self.width = helper.try_except(lambda: image.width, None)
        self.height = helper.try_except(lambda: image.height, None)
        self.phash = self._calculate_phash()
        self.norm_pixel_hash = self._calculate_norm_pixel_hash()
