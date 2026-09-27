import pytest
from datetime import datetime

from src.classes.entities.MetadataFile import MetadataFile
from src.classes.workflows.AnnotateMedia import AnnotateMedia
from src.classes.workflows.SearchMedia import SearchMedia
from src.tests.conftest import seed_media


def _seed_and_tag(tmp_root):
    """Two years of tagged media; returns {filename: filepath}."""
    files_2024 = seed_media(tmp_root, 2024, 12, [('x.jpg', datetime(2024, 12, 24, 10, 0))])
    files_2025 = seed_media(tmp_root, 2025, 6,
                            [('a.jpg', datetime(2025, 6, 1, 10, 0)),
                             ('b.jpg', datetime(2025, 6, 2, 11, 0))])
    AnnotateMedia(dry_run=False).run(
        [files_2025['a.jpg']], title='Beach day', tags='beach;sunset',
        people='alice', is_highlight=True)
    AnnotateMedia(dry_run=False).run(
        [files_2025['b.jpg']], title='City night', tags='city',
        people='bob', comments='great lights')
    AnnotateMedia(dry_run=False).run(
        [files_2024['x.jpg']], title='Snow trip', tags='snow;beach',
        people='alice;carol')

    # put a.jpg in event 7 without moving files
    mf = MetadataFile.get_instance(2025)
    record = mf.get_media_metadata(files_2025['a.jpg'])
    record['event_id'] = 7
    mf.add_media_metadata(record, update=True)

    return {**files_2024, **files_2025}


class TestSearchMedia:
    def test_no_filters_returns_everything(self, tmp_root, capsys):
        _seed_and_tag(tmp_root)

        df = SearchMedia().run()

        assert len(df) == 3
        assert 'result(s)' in capsys.readouterr().out

    def test_year_filter(self, tmp_root):
        _seed_and_tag(tmp_root)

        df = SearchMedia().run(years=[2024])

        assert len(df) == 1
        assert df.iloc[0]['filepath'].endswith('x.jpg')

    def test_tags_match_any_case_insensitive(self, tmp_root):
        _seed_and_tag(tmp_root)

        df = SearchMedia().run(tags='BEACH')

        assert {r['filepath'][-5:] for _, r in df.iterrows()} == {'a.jpg', 'x.jpg'}

        df = SearchMedia().run(tags='beach,snow')

        assert len(df) == 2  # any-match, not all-match

    def test_people_filter(self, tmp_root):
        _seed_and_tag(tmp_root)

        df = SearchMedia().run(people='carol')

        assert len(df) == 1
        assert df.iloc[0]['filepath'].endswith('x.jpg')

    def test_title_substring(self, tmp_root):
        _seed_and_tag(tmp_root)

        df = SearchMedia().run(title='day')

        assert len(df) == 1
        assert df.iloc[0]['title'] == 'Beach day'

    def test_comments_substring(self, tmp_root):
        _seed_and_tag(tmp_root)

        df = SearchMedia().run(comments='lights')

        assert len(df) == 1
        assert df.iloc[0]['filepath'].endswith('b.jpg')

    def test_event_id_filter(self, tmp_root):
        _seed_and_tag(tmp_root)

        df = SearchMedia().run(event_id=7)

        assert len(df) == 1
        assert df.iloc[0]['filepath'].endswith('a.jpg')

    def test_highlight_filter(self, tmp_root):
        _seed_and_tag(tmp_root)

        df = SearchMedia().run(is_highlight=True)

        assert len(df) == 1
        assert df.iloc[0]['filepath'].endswith('a.jpg')

    def test_date_range_is_inclusive(self, tmp_root):
        _seed_and_tag(tmp_root)

        df = SearchMedia().run(start_date='2025-06-02', end_date='2025-06-02')

        assert len(df) == 1
        assert df.iloc[0]['filepath'].endswith('b.jpg')

    def test_filters_combine_with_and(self, tmp_root):
        _seed_and_tag(tmp_root)

        df = SearchMedia().run(tags='beach', people='carol')

        assert len(df) == 1
        assert df.iloc[0]['filepath'].endswith('x.jpg')

    def test_limit(self, tmp_root):
        _seed_and_tag(tmp_root)

        df = SearchMedia().run(limit=2)

        assert len(df) == 2

    def test_no_matches(self, tmp_root, capsys):
        _seed_and_tag(tmp_root)

        df = SearchMedia().run(tags='desert')

        assert df.empty
        assert '0 result(s)' in capsys.readouterr().out

    def test_results_sorted_by_datetime(self, tmp_root):
        _seed_and_tag(tmp_root)

        df = SearchMedia().run()

        dts = list(df['dt'])
        assert dts == sorted(dts)
