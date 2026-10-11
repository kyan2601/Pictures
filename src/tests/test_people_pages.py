import os
from datetime import datetime

from PIL import Image

from src import constants
from src.classes.workflows.AnnotateMedia import AnnotateMedia
from src.classes.workflows.PeoplePages import PeoplePages, _slugify
from src.tests.conftest import seed_media


def _write_jpeg(path):
    Image.new('RGB', (40, 40), color=(255, 0, 0)).save(str(path), 'JPEG')


def _seed(tmp_root):
    """Alice: 4 photos (2023 x2, 2024 x2, one highlight). Bob: 2. Carol: 1."""
    files = {}
    files.update(seed_media(tmp_root, 2023, 5, [
        ('a2023.jpg', datetime(2023, 5, 1, 10, 0)),
        ('b2023.jpg', datetime(2023, 5, 2, 10, 0)),
    ]))
    files.update(seed_media(tmp_root, 2024, 6, [
        ('a2024.jpg', datetime(2024, 6, 1, 10, 0)),
        ('b2024.jpg', datetime(2024, 6, 2, 10, 0)),
        ('c2024.jpg', datetime(2024, 6, 3, 10, 0)),
        ('solo.jpg', datetime(2024, 6, 4, 10, 0)),
    ]))
    for f in files.values():
        _write_jpeg(f)
    AnnotateMedia(dry_run=False).run([files['a2023.jpg']], people='Alice')
    AnnotateMedia(dry_run=False).run([files['b2023.jpg']], people='Alice')
    AnnotateMedia(dry_run=False).run(
        [files['a2024.jpg']], title='Beach day', is_highlight=True, people='Alice')
    AnnotateMedia(dry_run=False).run([files['b2024.jpg']], people='Alice; Bob')
    AnnotateMedia(dry_run=False).run([files['c2024.jpg']], people='Bob')
    AnnotateMedia(dry_run=False).run([files['solo.jpg']], people='Carol')
    return files


def _page(tmp_root, slug):
    return os.path.join(str(tmp_root), 'review', 'people', f'{slug}.html')


class TestSlugify:
    def test_basic(self):
        assert _slugify('Mary Jane', set()) == 'mary-jane'
        assert _slugify('Kevin', set()) == 'kevin'

    def test_collision_gets_suffix(self):
        taken = set()
        assert _slugify('Ann Lee', taken) == 'ann-lee'
        assert _slugify('Ann-Lee', taken) == 'ann-lee-2'


class TestPeoplePages:
    def test_builds_pages_at_or_above_min_photos(self, tmp_root):
        _seed(tmp_root)

        result = PeoplePages().run()  # default min_photos=3

        assert result == os.path.join(constants.REVIEW_DIR, 'people')
        assert os.path.exists(_page(tmp_root, 'alice'))
        assert not os.path.exists(_page(tmp_root, 'bob'))    # only 2 photos
        assert not os.path.exists(_page(tmp_root, 'carol'))  # only 1 photo

        html = open(_page(tmp_root, 'alice')).read()
        assert 'Alice at a glance' in html
        assert '4 photos · 2023–2024 · 1 highlight' in html
        assert 'Beach day' in html      # title used as the label
        assert '★ Beach day' in html    # highlight starred, first in its year

    def test_year_sections_group_photos(self, tmp_root):
        _seed(tmp_root)

        PeoplePages().run(min_photos=2)

        html = open(_page(tmp_root, 'bob')).read()
        assert 'Bob at a glance' in html
        assert '2 photos · 2024 · 0 highlights' in html

    def test_serves_existing_until_regenerate(self, tmp_root, capsys):
        files = _seed(tmp_root)
        PeoplePages().run()
        page = _page(tmp_root, 'alice')
        before = open(page).read()
        capsys.readouterr()

        result = PeoplePages().run()

        assert result == os.path.join(constants.REVIEW_DIR, 'people')
        assert 'already exist' in capsys.readouterr().out
        assert open(page).read() == before  # untouched

        # A new Alice photo lands; only --regenerate picks it up.
        extra = seed_media(tmp_root, 2024, 7,
                           [('extra.jpg', datetime(2024, 7, 4, 10, 0))])
        _write_jpeg(extra['extra.jpg'])
        AnnotateMedia(dry_run=False).run([extra['extra.jpg']], people='Alice')
        PeoplePages().run(regenerate=True)
        assert '5 photos · 2023–2024' in open(page).read()
        assert files  # silence unused

    def test_no_people_returns_none(self, tmp_root, capsys):
        seed_media(tmp_root, 2024, 1, [('x.jpg', datetime(2024, 1, 1, 10, 0))])

        assert PeoplePages().run() is None
        assert 'No people with at least 3' in capsys.readouterr().out
