from src import helper
from src.classes.entities.HEICPictureEntry import HEICPictureEntry
from src.classes.entities.JPEGPictureEntry import JPEGPictureEntry
from src.classes.entities.JPGPictureEntry import JPGPictureEntry
from src.classes.entities.MOVVideoEntry import MOVVideoEntry
from src.classes.entities.MP4VideoEntry import MP4VideoEntry
from src.classes.entities.PNGPictureEntry import PNGPictureEntry


def create_media_entry(filepath):
    if '.' not in filepath:
        raise RuntimeError(f"No extension detected in filepath [{filepath}]")

    ext = helper.decompose_filepath(filepath)['ext']
    ext = ext.lower()

    ext_map = {
        'jpg': JPGPictureEntry,
        'jpeg': JPEGPictureEntry,
        'png': PNGPictureEntry,
        'heic': HEICPictureEntry,

        'mov': MOVVideoEntry,
        'mp4': MP4VideoEntry,
    }

    if ext not in ext_map.keys():
        raise RuntimeError(f"Unknown extension [{ext}]")

    return ext_map[ext](filepath)
