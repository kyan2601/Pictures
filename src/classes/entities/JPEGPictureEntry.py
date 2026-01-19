import os
from datetime import datetime

import exif

from src import constants, helper
from src.classes.entities.PictureEntry import PictureEntry


class JPEGPictureEntry(PictureEntry):

    def __init__(self, filepath):
        super().__init__(filepath)
        self.ext = constants.PictureExtension.JPEG

    def _extract_metadata(self):
        img = exif.Image(self.filepath)

        dt_obj = helper.try_except(lambda: datetime.strptime(img['datetime_original'], '%Y:%m:%d %H:%M:%S'),
                                   datetime.fromtimestamp(os.path.getctime(self.filepath)))
        self.dt = dt_obj.replace(tzinfo=None) if dt_obj and dt_obj.tzinfo else dt_obj
        self.width = helper.try_except(lambda: img['pixel_x_dimension'], None)
        self.height = helper.try_except(lambda: img['pixel_y_dimension'], None)
        self.latitude, self.longitude = helper.try_except(
            lambda: helper.gps_coordinates_to_lat_long(img['gps_latitude_ref'],
                                                       img['gps_latitude'],
                                                       img['gps_longitude_ref'],
                                                       img['gps_longitude']),
            (None, None))
        self.altitude = helper.try_except(lambda: img['gps_altitude'], None)
        self.orientation = helper.try_except(lambda: img['gps_img_direction'], None)
        self.comments = helper.try_except(lambda: img['xp_comment'], None)

        keywords = helper.try_except(lambda: img['xp_keywords'], None)
        people = None
        tags = None
        if keywords:
            keywords = keywords.split(';')
            people = ';'.join([keyword for keyword in keywords if helper.keyword_is_name(keyword)])
            tags = ';'.join([keyword for keyword in keywords if not helper.keyword_is_name(keyword)])
        self.people = people if people else None
        self.tags = tags if tags else None
        self.phash = self._calculate_phash()
        self.norm_pixel_hash = self._calculate_norm_pixel_hash()
