import pandas as pd
import pytest

from src.classes.entities.MetadataFile import MetadataFile
from src.classes.workflows.AnnotateMedia import AnnotateMedia
from src.tests.conftest import seed_media


def _record_for(filepath, year):
    return MetadataFile.get_instance(year).get_media_metadata(filepath)


class TestAnnotateMedia:
    def test_dry_run_changes_nothing(self, tmp_root, capsys):
        files = seed_media(tmp_root, 2025, 6, [('a.jpg', '2025-06-01'), ('b.jpg', '2025-06-02')])

        AnnotateMedia(dry_run=True).run(
            [files['a.jpg'], files['b.jpg']], title='Beach day', is_highlight=True)

        out = capsys.readouterr().out
        assert '[dry run]' in out
        assert pd.isna(_record_for(files['a.jpg'], 2025)['title'])

    def test_execute_updates_all_fields(self, tmp_root):
        files = seed_media(tmp_root, 2025, 6, [('a.jpg', '2025-06-01')])

        AnnotateMedia(dry_run=False).run(
            [files['a.jpg']], title='Beach day', tags='beach, sunset;ocean',
            people='alice, bob', comments='great light', is_highlight=True)

        record = _record_for(files['a.jpg'], 2025)
        assert record['title'] == 'Beach day'
        assert record['tags'] == 'beach;sunset;ocean'
        assert record['people'] == 'alice;bob'
        assert record['comments'] == 'great light'
        assert record['is_highlight'] == 1

    def test_no_highlight_unmarks(self, tmp_root):
        files = seed_media(tmp_root, 2025, 6, [('a.jpg', '2025-06-01')])
        AnnotateMedia(dry_run=False).run([files['a.jpg']], is_highlight=True)
        assert _record_for(files['a.jpg'], 2025)['is_highlight'] == 1

        AnnotateMedia(dry_run=False).run([files['a.jpg']], is_highlight=False)
        assert _record_for(files['a.jpg'], 2025)['is_highlight'] == 0

    def test_partial_update_preserves_other_fields(self, tmp_root):
        files = seed_media(tmp_root, 2025, 6, [('a.jpg', '2025-06-01')])
        AnnotateMedia(dry_run=False).run([files['a.jpg']], title='Original', tags='x')

        AnnotateMedia(dry_run=False).run([files['a.jpg']], comments='added later')

        record = _record_for(files['a.jpg'], 2025)
        assert record['title'] == 'Original'
        assert record['tags'] == 'x'
        assert record['comments'] == 'added later'

    def test_missing_record_is_skipped(self, tmp_root, capsys):
        files = seed_media(tmp_root, 2025, 6, [('a.jpg', '2025-06-01')])
        ghost = str(tmp_root / '2025' / '06' / 'ghost.jpg')

        AnnotateMedia(dry_run=False).run([files['a.jpg'], ghost], title='Kept')

        assert '[skip]' in capsys.readouterr().out
        assert _record_for(files['a.jpg'], 2025)['title'] == 'Kept'

    def test_spanning_years(self, tmp_root):
        files_2024 = seed_media(tmp_root, 2024, 12, [('x.jpg', '2024-12-31')])
        files_2025 = seed_media(tmp_root, 2025, 1, [('y.jpg', '2025-01-01')])

        AnnotateMedia(dry_run=False).run(
            [files_2024['x.jpg'], files_2025['y.jpg']], tags='newyear')

        assert _record_for(files_2024['x.jpg'], 2024)['tags'] == 'newyear'
        assert _record_for(files_2025['y.jpg'], 2025)['tags'] == 'newyear'

    def test_no_fields_raises(self, tmp_root):
        files = seed_media(tmp_root, 2025, 6, [('a.jpg', '2025-06-01')])

        with pytest.raises(RuntimeError, match='No annotation fields'):
            AnnotateMedia(dry_run=False).run([files['a.jpg']])

    def test_empty_string_clears_field(self, tmp_root):
        files = seed_media(tmp_root, 2025, 6, [('a.jpg', '2025-06-01')])
        AnnotateMedia(dry_run=False).run([files['a.jpg']], title='Temp')
        AnnotateMedia(dry_run=False).run([files['a.jpg']], title='')

        assert _record_for(files['a.jpg'], 2025)['title'] == ''
