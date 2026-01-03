import os
from datetime import datetime

import ffmpeg

from src import constants, helper
from src.classes.VideoEntry import VideoEntry


class MOVVideoEntry(VideoEntry):

    def __init__(self, filepath):
        super().__init__(filepath)
        self.ext = constants.VideoExtension.MOV

    def _extract_metadata(self):
        data = ffmpeg.probe(self.filepath)

        # extract video and audio streams
        video_metadata = None
        audio_metadata = None
        for stream_metadata in data['streams']:
            codec_type = stream_metadata['codec_type']
            if codec_type == 'video':
                video_metadata = stream_metadata
            elif codec_type == 'audio':
                audio_metadata = stream_metadata

        if video_metadata is None:
            raise RuntimeError(f"No video stream found in {self.filepath}")

        self.dt = helper.try_except(
            lambda: datetime.fromisoformat(data['format']['tags']['com.apple.quicktime.creationdate']).replace(
                tzinfo=None),
            datetime.fromtimestamp(os.path.getctime(self.filepath))
        )
        self.width = helper.try_except(lambda: int(video_metadata['width']), None)
        self.height = helper.try_except(lambda: int(video_metadata['height']), None)
        self.latitude, self.longitude, self.altitude = helper.try_except(
            lambda: helper.lat_long_parser(data['format']['tags']['com.apple.quicktime.location.ISO6709']),
            (None, None, None))
        # Note: duration is extracted but not stored in metadata.csv as it's not in METADATA_COLS
        # If needed in the future, add it to constants.METADATA_COLS
        _duration = helper.try_except(lambda: float(data['format']['duration']), None)
