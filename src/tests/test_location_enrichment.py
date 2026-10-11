import pandas as pd
import pytest

from src.classes.entities.MetadataFile import MetadataFile
from src.classes.workflows import LocationEnrichment as LE
from src.classes.workflows.LocationEnrichment import LocationEnrichment
from src.tests.conftest import seed_media


@pytest.fixture
def fake_geocode(monkeypatch):
    """Replaces the offline lookup with a deterministic fake."""
    calls = []

    def fake(coords):
        calls.append(list(coords))
        return [('Testville', 'Testland') for _ in coords]

    monkeypatch.setattr(LE, '_reverse_geocode', fake)
    return calls


def _seed_with_gps(tmp_root):
    files = seed_media(tmp_root, 2024, 5, [
        ('a.jpg', '2024:05:01 10:00:00'),
        ('b.jpg', '2024:05:02 10:00:00'),
        ('c.jpg', '2024:05:03 10:00:00'),
    ])
    mf = MetadataFile.get_instance(2024)
    for fp, (lat, lon) in [(files['a.jpg'], (40.7, -74.0)),
                           (files['b.jpg'], (40.7, -74.0)),
                           (files['c.jpg'], (None, None))]:
        record = mf.get_media_metadata(fp)
        record['latitude'] = lat
        record['longitude'] = lon
        mf.add_media_metadata(record, update=True, write=False)
    mf.write()
    return files


def _location_of(filepath):
    record = MetadataFile.get_instance(2024).get_media_metadata(filepath)
    return tuple(None if pd.isna(v) else v
                 for v in (record['location_city'], record['location_country']))


class TestEnrich:
    def test_fills_city_and_country(self, tmp_root, fake_geocode):
        files = _seed_with_gps(tmp_root)

        summary = LocationEnrichment().enrich(years=[2024], dry_run=False)

        assert summary[2024]['updated'] == 2
        assert _location_of(files['a.jpg']) == ('Testville', 'Testland')
        assert _location_of(files['b.jpg']) == ('Testville', 'Testland')
        # No GPS: untouched.
        assert _location_of(files['c.jpg']) == (None, None)
        assert summary[2024]['no_gps'] == 1

    def test_dedupes_identical_coordinates(self, tmp_root, fake_geocode):
        _seed_with_gps(tmp_root)

        LocationEnrichment().enrich(years=[2024], dry_run=False)

        assert len(fake_geocode) == 1
        assert fake_geocode[0] == [(40.7, -74.0)]

    def test_dry_run_reports_without_writing(self, tmp_root, fake_geocode):
        files = _seed_with_gps(tmp_root)

        summary = LocationEnrichment().enrich(years=[2024], dry_run=True)

        assert summary[2024]['updated'] == 2
        # CSV on disk still has no locations.
        df = pd.read_csv(tmp_root / '2024' / 'metadata.csv')
        assert df['location_city'].isna().all()
        assert _location_of(files['a.jpg']) == (None, None)

    def test_second_run_is_noop(self, tmp_root, fake_geocode):
        _seed_with_gps(tmp_root)
        LocationEnrichment().enrich(years=[2024], dry_run=False)
        fake_geocode.clear()

        summary = LocationEnrichment().enrich(years=[2024], dry_run=False)

        assert summary[2024] == {'updated': 0, 'already': 2, 'no_gps': 1}
        assert fake_geocode == []  # no lookups needed

    def test_old_csv_without_new_columns(self, tmp_root, fake_geocode):
        """CSVs written before location_city/location_country existed load fine."""
        files = _seed_with_gps(tmp_root)
        csv_path = tmp_root / '2024' / 'metadata.csv'
        df = pd.read_csv(csv_path).drop(columns=['location_city', 'location_country'])
        df.to_csv(csv_path, index=False)
        MetadataFile._instances = {}

        summary = LocationEnrichment().enrich(years=[2024], dry_run=False)

        assert summary[2024]['updated'] == 2
        assert _location_of(files['a.jpg']) == ('Testville', 'Testland')

    def test_country_code_mapping(self):
        assert LE._country_name('US') == 'United States'
        assert LE._country_name('GB') == 'United Kingdom'
        assert LE._country_name('XX') == 'XX'  # unknown codes pass through


class TestRealGeocoder:
    def test_offline_lookup_smoke(self):
        cities = LE._reverse_geocode([(40.7128, -74.0060)])
        city, country = cities[0]
        assert 'New York' in city
        assert country == 'United States'
