import os
from datetime import datetime

from src import constants, helper
from src.classes.entities.MetadataFile import MetadataFile
from src.classes.workflows.AnnotateMedia import AnnotateMedia
from src.classes.workflows.LibraryStats import LibraryStats
from src.tests.conftest import seed_media


def _seed(tmp_root):
    """2024: 4 photos with partial coverage. 2023: 2 fully-annotated photos
    (but no location/GPS/hash). Totals: titled 4/6, tagged 3/6, people 4/6,
    location 2/6, GPS 1/6, hashed 1/6."""
    f24 = seed_media(tmp_root, 2024, 6, [
        ('p1.jpg', datetime(2024, 6, 1, 10, 0)),
        ('p2.jpg', datetime(2024, 6, 2, 10, 0)),
        ('p3.jpg', datetime(2024, 6, 3, 10, 0)),
        ('p4.jpg', datetime(2024, 6, 4, 10, 0)),
    ])
    f23 = seed_media(tmp_root, 2023, 5, [
        ('q1.jpg', datetime(2023, 5, 1, 10, 0)),
        ('q2.jpg', datetime(2023, 5, 2, 10, 0)),
    ])
    AnnotateMedia(dry_run=False).run(
        [f24['p1.jpg']], title='Full', tags='x', people='Alice')
    AnnotateMedia(dry_run=False).run([f24['p2.jpg']], title='Title only')
    AnnotateMedia(dry_run=False).run([f24['p4.jpg']], people='Bob')
    AnnotateMedia(dry_run=False).run(
        [f23['q1.jpg'], f23['q2.jpg']], tags='y', people='Alice')
    AnnotateMedia(dry_run=False).run(
        [f23['q1.jpg'], f23['q2.jpg']], title='Old')
    mf24 = MetadataFile.get_instance(2024)
    _set_fields(mf24, f24['p1.jpg'],
                location_city='New York', latitude=40.7, longitude=-74.0,
                phash='abcd')
    _set_fields(mf24, f24['p4.jpg'], location_city='Boston')
    return {**f23, **f24}


def _set_fields(metadata_file, filepath, **fields):
    """add_media_metadata(update=True) replaces the whole row, so merge the
    new fields into the existing record first."""
    record = dict(metadata_file.get_media_metadata(filepath))
    record.update(fields)
    metadata_file.add_media_metadata(record, update=True)


def _page_path():
    return os.path.join(constants.REVIEW_DIR, 'library-health', 'index.html')


class TestCoverageCounters:
    def test_location_and_gps_counts(self, tmp_root):
        _seed(tmp_root)

        stats = LibraryStats._stats_for_year(MetadataFile.get_instance(2024).df)

        assert stats['with_location'] == 2
        assert stats['with_gps'] == 1


class TestHealthPage:
    def test_build_page_with_coverage_and_gaps(self, tmp_root):
        _seed(tmp_root)

        written = LibraryStats().build_health_page()

        assert written == _page_path()
        html = open(written).read()
        assert 'Library at a glance' in html
        assert 'Titled 67%' in html
        assert 'Tagged 50%' in html
        assert 'Location 33%' in html
        assert 'GPS 17%' in html
        assert 'Biggest gaps' in html
        assert 'Location: 4 missing overall — worst in 2023 (2 of 2, 100% missing)' in html
        assert 'GPS: 5 missing overall — worst in 2024 (3 of 4, 75% missing)' in html

    def test_serves_existing_until_regenerate(self, tmp_root, capsys):
        _seed(tmp_root)
        LibraryStats().build_health_page()
        before = open(_page_path()).read()
        capsys.readouterr()

        assert LibraryStats().build_health_page() == _page_path()
        assert 'already exists' in capsys.readouterr().out
        assert open(_page_path()).read() == before

        # Backfill 2023 locations; only --regenerate reflects it.
        mf23 = MetadataFile.get_instance(2023)
        for fp in list(mf23.df['filepath']):
            _set_fields(mf23, fp, location_city='Chicago')
        LibraryStats().build_health_page(regenerate=True)
        assert 'Location 67%' in open(_page_path()).read()

    def test_no_metadata_returns_none(self, tmp_root, capsys, monkeypatch):
        monkeypatch.setattr(helper, 'get_years_with_metadata', lambda: [])

        assert LibraryStats().build_health_page() is None
        assert 'No metadata found' in capsys.readouterr().out
