import os
from enum import Enum

SOURCE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SOURCE_DIR)
NEW_MEDIA_DIR = os.path.join(ROOT_DIR, 'new')
BACKUP_DIR = os.path.join(ROOT_DIR, 'backup')

METADATA_FILENAME = 'metadata.csv'
METADATA_DELETED_FILENAME = 'metadata_DELETED.csv'
METADATA_COLS = ['filepath', 'dt', 'width', 'height',
                 'latitude', 'longitude', 'altitude', 'orientation',
                 'title', 'tags', 'people', 'comments', 'event_id', 'is_highlight', 'phash']

EVENTS_FILEPATH = os.path.join(SOURCE_DIR, 'events.csv')
EVENTS_COLS = ['event_id', 'event_index',
               'start_date', 'end_date', 'nominal_month',
               'title', 'description']


class MediaType(Enum):
    PICTURE = "picture"
    VIDEO = "video"


class PictureExtension(Enum):
    JPEG = "jpeg"
    JPG = "jpg"
    PNG = "png"
    HEIC = "heic"


class VideoExtension(Enum):
    MOV = "mov"
    MP4 = "mp4"


PICTURE_EXTENSIONS = [e.name for e in PictureExtension] + [e.value for e in PictureExtension]
VIDEO_EXTENSIONS = [e.name for e in VideoExtension] + [e.value for e in VideoExtension]
MEDIA_EXTENSIONS = PICTURE_EXTENSIONS + VIDEO_EXTENSIONS
