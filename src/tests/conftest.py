import os
import sys

# Ensure the project root (parent of the 'src' package) is importable regardless
# of how pytest is invoked, mirroring the sys.path handling in adhoc/ scripts.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import pandas as pd
import pytest

from src import constants
from src.classes.entities.EventsMetadataFile import EventsMetadataFile
from src.classes.entities.MetadataFile import MetadataFile


@pytest.fixture
def tmp_root(tmp_path, monkeypatch):
    """
    Redirects all filesystem-touching constants at a throwaway tmp_path directory
    and resets the MetadataFile singleton cache, so tests can never read from or
    write to the real photo library.
    """
    monkeypatch.setattr(constants, 'ROOT_DIR', str(tmp_path))
    monkeypatch.setattr(constants, 'NEW_MEDIA_DIR', str(tmp_path / 'new'))
    monkeypatch.setattr(constants, 'BACKUP_DIR', str(tmp_path / 'backup'))

    MetadataFile._instances = {}
    yield tmp_path
    MetadataFile._instances = {}


@pytest.fixture
def events_file(tmp_root, monkeypatch):
    """
    Redirects constants.EVENTS_FILEPATH (normally a fixed path next to constants.py,
    unrelated to ROOT_DIR) at a throwaway events.csv, and resets the EventsMetadataFile
    singleton cache.
    """
    events_path = tmp_root / 'events.csv'
    pd.DataFrame([], columns=constants.EVENTS_COLS).to_csv(events_path, index=False)
    monkeypatch.setattr(constants, 'EVENTS_FILEPATH', str(events_path))

    EventsMetadataFile._instances = {}
    yield events_path
    EventsMetadataFile._instances = {}


def seed_media(tmp_root, year, month, filename_dt_pairs):
    """
    Writes each (filename, dt) pair as a real (dummy-content) file under
    tmp_root/year/month/ and registers matching rows in that year's metadata file.
    Content is tagged with its own original filename so a test can tell which
    original file ended up where after a move/rename.
    Returns {filename: absolute_filepath_str}.
    """
    month_dir = tmp_root / str(year) / str(month).zfill(2)
    month_dir.mkdir(parents=True, exist_ok=True)

    records = []
    for filename, dt in filename_dt_pairs:
        filepath = month_dir / filename
        filepath.write_bytes(filename.encode())
        records.append({'filepath': str(filepath), 'dt': dt})

    MetadataFile.get_instance(year).add_media_metadata(records)
    return {filename: str(month_dir / filename) for filename, _ in filename_dt_pairs}
