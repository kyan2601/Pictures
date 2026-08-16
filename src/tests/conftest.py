import os
import sys

# Ensure the project root (parent of the 'src' package) is importable regardless
# of how pytest is invoked, mirroring the sys.path handling in adhoc/ scripts.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import pytest

from src import constants
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
