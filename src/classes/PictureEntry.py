from abc import ABC
from PIL import Image
import imagehash
import hashlib

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

    def _calculate_norm_pixel_hash(self, target_size: int = 512, pad_color=(0, 0, 0), mode='RGB'):
        img = Image.open(self.filepath)
        img = img.convert(mode)

        # Scale so longest side == target_size
        scale = target_size / max(self.width, self.height)
        new_width = round(self.width * scale)
        new_height = round(self.height * scale)

        img_resized = img.resize((new_width, new_height), Image.Resampling.BICUBIC)

        # Create padded canvas
        canvas = Image.new(mode, (target_size, target_size), pad_color)

        # Center the image
        offset_x = (target_size - new_width) // 2
        offset_y = (target_size - new_height) // 2

        canvas.paste(img_resized, (offset_x, offset_y))

        return hashlib.sha256(img.tobytes()).hexdigest()
