import os
from datetime import datetime

from PIL import Image

from src import constants
from src.classes.entities.EventsMetadataFile import EventsMetadataFile
from src.classes.entities.MetadataFile import MetadataFile
from src.classes.workflows.AnnotateMedia import AnnotateMedia
from src.classes.workflows.YearInReview import YearInReview
from src.tests.conftest import seed_media


def _write_jpeg(path):
    Image.new('RGB', (40, 40), color=(255, 0, 0)).save(str(path), 'JPEG')


def _seed_year(tmp_root):
    files = seed_media(tmp_root, 2024, 1,
                       [('jan.jpg', datetime(2024, 1, 10, 10, 0))])
    files.update(seed_media(tmp_root, 2024, 2,
                            [('feb1.jpg', datetime(2024, 2, 5, 10, 0)),
                             ('feb2.jpg', datetime(2024, 2, 20, 10, 0)),
                             ('plain.jpg', datetime(2024, 2, 25, 10, 0))]))
    for f in files.values():
        _write_jpeg(f)
    AnnotateMedia(dry_run=False).run(
        [files['jan.jpg']], title='Snow', is_highlight=True,
        tags='winter; snow', people='Alice')
    AnnotateMedia(dry_run=False).run(
        [files['feb1.jpg']], title='Ski trip', is_highlight=True,
        tags='winter', people='Alice; Bob')
    AnnotateMedia(dry_run=False).run(
        [files['feb2.jpg']], is_highlight=True, tags='snow', people='Bob')
    return files


class TestBuildSections:
    def test_section_order_and_month_grouping(self, tmp_root):
        _seed_year(tmp_root)

        sections = YearInReview()._build_sections(
            2024, MetadataFile.get_instance(2024).df, per_month_limit=12)

        headings = [s['heading'] for s in sections]
        assert headings[:3] == ['2024 at a glance', 'January', 'February']
        feb = sections[2]
        assert len(feb['items']) == 2  # plain.jpg is not a highlight
        assert feb['items'][0]['label'] == 'Ski trip'
        assert feb['items'][1]['label'] == 'February 20'

    def test_summary_note_has_counts_and_month_breakdown(self, tmp_root):
        _seed_year(tmp_root)

        sections = YearInReview()._build_sections(
            2024, MetadataFile.get_instance(2024).df, per_month_limit=12)

        note = sections[0]['note']
        assert '4 files' in note
        assert '3 highlights' in note
        assert 'Jan 1' in note and 'Feb 3' in note

    def test_top_tags_and_people_ranked_by_count(self, tmp_root):
        _seed_year(tmp_root)

        sections = YearInReview()._build_sections(
            2024, MetadataFile.get_instance(2024).df, per_month_limit=12)

        by_heading = {s['heading']: s for s in sections}
        assert by_heading['Top tags']['note'].startswith('winter (2)')
        assert 'snow (2)' in by_heading['Top tags']['note']
        assert by_heading['Top people']['note'].startswith('Alice (2)')
        assert 'Bob (2)' in by_heading['Top people']['note']

    def test_events_section_lists_year_events(self, tmp_root, events_file):
        _seed_year(tmp_root)
        EventsMetadataFile.get_instance().create_event(
            title='December Gala', start_date='2024-12-24', end_date='2024-12-25')
        EventsMetadataFile.get_instance().create_event(
            title='Old Event', start_date='2023-06-01', end_date='2023-06-02')

        sections = YearInReview()._build_sections(
            2024, MetadataFile.get_instance(2024).df, per_month_limit=12)

        events = {s['heading']: s for s in sections}['Events']
        assert 'December Gala (Dec 24 – Dec 25)' in events['note']
        assert 'Old Event' not in events['note']

    def test_no_highlights_no_tags_sections_omitted(self, tmp_root):
        seed_media(tmp_root, 2024, 3, [('a.jpg', datetime(2024, 3, 1, 10, 0))])

        sections = YearInReview()._build_sections(
            2024, MetadataFile.get_instance(2024).df, per_month_limit=12)

        assert [s['heading'] for s in sections] == ['2024 at a glance']


class TestRun:
    def test_builds_gallery_page(self, tmp_root):
        _seed_year(tmp_root)

        page_path = YearInReview().run(year=2024)

        assert page_path is not None
        assert os.path.exists(page_path)
        html = open(page_path, encoding='utf-8').read()
        assert 'Year in Review — 2024' in html
        assert 'Ski trip' in html
        assert 'Top tags' in html

    def test_serves_existing_page_without_regenerating(self, tmp_root, capsys):
        _seed_year(tmp_root)
        page_path = YearInReview().run(year=2024)
        with open(page_path, 'a', encoding='utf-8') as f:
            f.write('\n<!-- sentinel -->')
        capsys.readouterr()

        again = YearInReview().run(year=2024)

        assert again == page_path
        assert 'already exists' in capsys.readouterr().out
        with open(page_path, encoding='utf-8') as f:
            assert '<!-- sentinel -->' in f.read()

    def test_regenerate_rebuilds_page(self, tmp_root):
        files = _seed_year(tmp_root)
        page_path = YearInReview().run(year=2024)
        AnnotateMedia(dry_run=False).run(
            [files['plain.jpg']], title='Late addition', is_highlight=True)

        YearInReview().run(year=2024, regenerate=True)

        with open(page_path, encoding='utf-8') as f:
            assert 'Late addition' in f.read()

    def test_defaults_to_latest_year(self, tmp_root, capsys):
        _seed_year(tmp_root)

        page_path = YearInReview().run()

        assert page_path is not None
        assert page_path.endswith(os.path.join('year-in-review', '2024.html'))
        assert 'Using 2024' in capsys.readouterr().out

    def test_year_without_metadata_returns_none(self, tmp_root, capsys):
        assert YearInReview().run(year=1999) is None
        assert 'No metadata found for 1999' in capsys.readouterr().out

    def test_page_path_uses_review_dir(self, tmp_root):
        path = YearInReview().page_path(2024)

        assert path == os.path.join(
            constants.REVIEW_DIR, 'year-in-review', '2024.html')
