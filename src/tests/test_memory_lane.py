from datetime import datetime

import pytest
from PIL import Image

from src.classes.workflows.AnnotateMedia import AnnotateMedia
from src.classes.workflows.MemoryLane import MemoryLane
from src.tests.conftest import seed_media


def _write_jpeg(path):
    Image.new('RGB', (40, 40), color=(255, 0, 0)).save(str(path), 'JPEG')


def _seed_on_this_day(tmp_root):
    """Photos on June 15 across two past years, plus one on June 16."""
    files_2023 = seed_media(tmp_root, 2023, 6, [('a.jpg', datetime(2023, 6, 15, 10, 0))])
    files_2024 = seed_media(tmp_root, 2024, 6,
                            [('b.jpg', datetime(2024, 6, 15, 11, 0)),
                             ('c.jpg', datetime(2024, 6, 15, 12, 0)),
                             ('d.jpg', datetime(2024, 6, 16, 10, 0))])
    for name, files in (('a.jpg', files_2023), ('b.jpg', files_2024),
                        ('c.jpg', files_2024), ('d.jpg', files_2024)):
        _write_jpeg(files[name])
    AnnotateMedia(dry_run=False).run([files_2024['b.jpg']], title='Picnic', is_highlight=True)
    AnnotateMedia(dry_run=False).run([files_2024['c.jpg']], title='Hike')
    return files_2023, files_2024


class TestCollectSections:
    def test_groups_by_year_excludes_other_days(self, tmp_root):
        _seed_on_this_day(tmp_root)

        sections = MemoryLane()._collect_sections(6, 15, limit_per_year=10)

        assert len(sections) == 2
        assert sections[0]['heading'].startswith('2023')
        assert sections[1]['heading'].startswith('2024')
        assert len(sections[0]['items']) == 1
        assert len(sections[1]['items']) == 2  # d.jpg (June 16) excluded

    def test_highlights_rank_first(self, tmp_root):
        _seed_on_this_day(tmp_root)

        sections = MemoryLane()._collect_sections(6, 15, limit_per_year=10)

        items_2024 = sections[1]['items']
        assert items_2024[0]['label'] == '★ Picnic'
        assert items_2024[1]['label'] == 'Hike'

    def test_limit_per_year(self, tmp_root):
        _seed_on_this_day(tmp_root)

        sections = MemoryLane()._collect_sections(6, 15, limit_per_year=1)

        assert all(len(s['items']) == 1 for s in sections)

    def test_no_matches_returns_empty(self, tmp_root):
        _seed_on_this_day(tmp_root)

        assert MemoryLane()._collect_sections(1, 1, limit_per_year=10) == []


class TestRun:
    def test_builds_gallery_page(self, tmp_root):
        _seed_on_this_day(tmp_root)

        page_path = MemoryLane().run(month=6, day=15)

        assert page_path is not None
        html = open(page_path, encoding='utf-8').read()
        assert 'Memory Lane' in html
        assert '2023' in html and '2024' in html
        assert '★ Picnic' in html

    def test_no_matches_returns_none(self, tmp_root, capsys):
        _seed_on_this_day(tmp_root)

        assert MemoryLane().run(month=1, day=1) is None
        assert 'No photos found' in capsys.readouterr().out

    def test_invalid_date_raises(self, tmp_root):
        with pytest.raises(RuntimeError, match='Invalid month/day'):
            MemoryLane().run(month=2, day=30)
