import os
from datetime import datetime

import PIL.ExifTags
import PIL.Image
from pillow_heif import register_heif_opener

from src import constants, helper
from src.classes.PictureEntry import PictureEntry


class HEICPictureEntry(PictureEntry):

    def __init__(self, filepath):
        super().__init__(filepath)
        self.ext = constants.PictureExtension.HEIC

    def _extract_metadata(self):
        register_heif_opener()
        image = PIL.Image.open(self.filepath)

        image_exif = image.getexif()
        metadata = {
            PIL.ExifTags.TAGS[k]: v
            for k, v in image_exif.items()
            if k in PIL.ExifTags.TAGS
        }

        ifd = image_exif.get_ifd(0x8825)
        gps_metadata = {
            PIL.ExifTags.GPSTAGS[k]: v
            for k, v in ifd.items()
            if k in PIL.ExifTags.GPSTAGS
        }

        self.dt = helper.try_except(lambda: datetime.strptime(metadata['DateTime'], '%Y:%m:%d %H:%M:%S'),
                                    datetime.fromtimestamp(os.path.getctime(self.filepath)))
        self.width = image.width
        self.height = image.height
        self.latitude, self.longitude = helper.try_except(
            lambda: helper.gps_coordinates_to_lat_long(gps_metadata['GPSLatitudeRef'],
                                                       gps_metadata['GPSLatitude'],
                                                       gps_metadata['GPSLongitudeRef'],
                                                       gps_metadata['GPSLongitude']),
            (None, None))

        self.altitude = helper.try_except(lambda: gps_metadata['GPSAltitude'], None)
        self.orientation = helper.try_except(lambda: gps_metadata['GPSImgDirection'], None)
        self.phash = self._calculate_phash()

    def _calculate_phash(self):
        register_heif_opener()
        return super()._calculate_phash()
