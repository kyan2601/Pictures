from datetime import datetime

import pytest
from PIL import Image

from src.classes.workflows.AnnotateMedia import AnnotateMedia
from src.classes.workflows.HighlightReel import HighlightReel
from src.tests.conftest import seed_media


def _write_jpeg(path):
    Image.new('RGB', (40, 40), color=(255, 0, 0)).save(str(path), 'JPEG')


def _seed_highlights(tmp_root):
    files = seed_media(tmp_root, 2024, 3,
                       [('jan.jpg', datetime(2024, 1, 10, 10, 0)),
                        ('feb1.jpg', datetime(2024, 2, 5, 10, 0)),
                        ('feb2.jpg', datetime(2024, 2, 20, 10, 0)),
                        ('plain.jpg', datetime(2024, 2, 25, 10, 0))])
    for f in files.values():
        _write_jpeg(f)
    AnnotateMedia(dry_run=False).run([files['jan.jpg']], title='Snow', is_highlight=True)
    AnnotateMedia(dry_run=False).run([files['feb1.jpg']], title='Ski trip', is_highlight=True)
    AnnotateMedia(dry_run=False).run([files['feb2.jpg']], is_highlight=True)
    return files


class TestCollectSections:
    def test_groups_by_month_in_order(self, tmp_root):
        _seed_highlights(tmp_root)

        sections = HighlightReel()._collect_sections(2024, limit=100)

        assert [s['heading'] for s in sections] == ['January', 'February']
        assert len(sections[0]['items']) == 1
        assert len(sections[1]['items']) == 2  # plain.jpg not highlighted

    def test_labels_fall_back_to_date(self, tmp_root):
        _seed_highlights(tmp_root)

        sections = HighlightReel()._collect_sections(2024, limit=100)

        feb_items = sections[1]['items']
        assert feb_items[0]['label'] == 'Ski trip'
        assert feb_items[1]['label'] == 'February 20'

    def test_limit_applies(self, tmp_root):
        _seed_highlights(tmp_root)

        sections = HighlightReel()._collect_sections(2024, limit=2)

        assert sum(len(s['items']) for s in sections) == 2

    def test_no_highlights_returns_empty(self, tmp_root):
        seed_media(tmp_root, 2024, 3, [('a.jpg', datetime(2024, 3, 1, 10, 0))])

        assert HighlightReel()._collect_sections(2024, limit=100) == []


class TestRun:
    def test_builds_gallery_page(self, tmp_root):
        _seed_highlights(tmp_root)

        page_path = HighlightReel().run(year=2024)

        assert page_path is not None
        html = open(page_path, encoding='utf-8').read()
        assert 'Highlights — 2024' in html
        assert 'January' in html and 'February' in html
        assert 'Ski trip' in html

    def test_defaults_to_latest_year_with_highlights(self, tmp_root, capsys):
        _seed_highlights(tmp_root)

        page_path = HighlightReel().run()

        assert page_path is not None
        assert 'Using 2024' in capsys.readouterr().out

    def test_no_highlights_anywhere_returns_none(self, tmp_root, capsys):
        seed_media(tmp_root, 2024, 3, [('a.jpg', datetime(2024, 3, 1, 10, 0))])

        assert HighlightReel().run() is None
        assert 'No highlights found' in capsys.readouterr().out
