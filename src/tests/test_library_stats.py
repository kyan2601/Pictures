from datetime import datetime

import pytest

from src import helper
from src.classes.entities.MetadataFile import MetadataFile
from src.classes.workflows.AnnotateMedia import AnnotateMedia
from src.classes.workflows.GallerySite import GallerySite
from src.classes.workflows.LibraryStats import LibraryStats
from src.tests.conftest import seed_media


def _seed_library(tmp_root):
    files_2025 = seed_media(tmp_root, 2025, 6,
                            [('a.jpg', datetime(2025, 6, 1, 10, 0)),
                             ('b.png', datetime(2025, 6, 2, 11, 0)),
                             ('c.mp4', datetime(2025, 7, 3, 12, 0))])
    files_2024 = seed_media(tmp_root, 2024, 12, [('x.jpg', datetime(2024, 12, 24, 10, 0))])
    AnnotateMedia(dry_run=False).run(
        [files_2025['a.jpg']], title='Beach day', tags='beach', people='alice',
        is_highlight=True)
    # a metadata record with no file on disk
    MetadataFile.get_instance(2025).add_media_metadata(
        {'filepath': str(tmp_root / '2025' / '06' / 'ghost.jpg'),
         'dt': datetime(2025, 6, 5, 10, 0)})
    return {**files_2024, **files_2025}


class TestLibraryStats:
    def test_counts_by_type_and_year(self, tmp_root, events_file, capsys):
        _seed_library(tmp_root)

        per_year = LibraryStats().run()

        assert per_year[2025]['files'] == 4  # includes the ghost record
        assert per_year[2025]['pictures'] == 3
        assert per_year[2025]['videos'] == 1
        assert per_year[2024]['files'] == 1
        assert per_year[2024]['pictures'] == 1
        assert 'TOTAL' in capsys.readouterr().out

    def test_storage_counts_only_existing_files(self, tmp_root, events_file):
        _seed_library(tmp_root)

        per_year = LibraryStats().run()

        assert per_year[2025]['missing_files'] == 1
        expected_bytes = sum(len(name.encode()) for name in ('a.jpg', 'b.png', 'c.mp4'))
        assert per_year[2025]['bytes'] == expected_bytes

    def test_annotation_coverage(self, tmp_root, events_file):
        _seed_library(tmp_root)

        per_year = LibraryStats().run()

        stats = per_year[2025]
        assert stats['titled'] == 1
        assert stats['tagged'] == 1
        assert stats['with_people'] == 1
        assert stats['highlights'] == 1

    def test_month_breakdown(self, tmp_root, events_file):
        _seed_library(tmp_root)

        per_year = LibraryStats().run()

        assert per_year[2025]['months']['2025-06'] == 3
        assert per_year[2025]['months']['2025-07'] == 1
        assert per_year[2024]['months']['2024-12'] == 1

    def test_year_filter(self, tmp_root, events_file):
        _seed_library(tmp_root)

        per_year = LibraryStats().run(years=[2024])

        assert set(per_year) == {2024}

    def test_library_wide_lines(self, tmp_root, events_file, capsys):
        _seed_library(tmp_root)
        site = GallerySite(str(tmp_root / 'review'))
        site.add_page('duplicate-check', 'p1', 'Page 1', [])

        LibraryStats().run()

        out = capsys.readouterr().out
        assert 'Events: 0' in out
        assert 'Review pages: 1 total, 1 pending' in out

    def test_no_metadata(self, tmp_root, events_file, capsys, monkeypatch):
        monkeypatch.setattr(helper, 'get_years', lambda: [])

        per_year = LibraryStats().run()

        assert per_year == {}
        assert 'No metadata found.' in capsys.readouterr().out


class TestGetReviewStats:
    def test_counts_total_and_pending(self, tmp_root):
        site = GallerySite(str(tmp_root / 'review'))
        assert site.get_review_stats() == (0, 0)

        p1 = site.add_page('duplicate-check', 'p1', 'Page 1', [])
        site.add_page('duplicate-check', 'p2', 'Page 2', [])
        assert site.get_review_stats() == (2, 2)

        site.mark_reviewed(p1)
        assert site.get_review_stats() == (2, 1)
