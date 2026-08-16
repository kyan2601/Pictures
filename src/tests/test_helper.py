import os

import pytest

from src import helper


class TestDecomposeFilepath:
    def test_splits_dirname_filename_and_ext(self):
        result = helper.decompose_filepath(os.path.join('2025', '10', '251025004.heic'))
        assert result['dirname'] == os.path.join('2025', '10')
        assert result['filename'] == '251025004.heic'
        assert result['filename_without_ext'] == '251025004'
        assert result['ext'] == 'heic'

    def test_ext_has_no_leading_dot(self):
        # Regression guard: every consumer of decompose_filepath()['ext'] (media_class_factory,
        # DuplicateImageCheck._compute_quality_score, backfill_hashes) assumes a dot-less value.
        assert helper.decompose_filepath('photo.HEIC')['ext'] == 'HEIC'


class TestDecomposeFilename:
    def test_filename_without_title(self):
        result = helper.decompose_filename('240207001.jpeg')
        assert result['date'] == '240207'
        assert result['date_obj'].isoformat() == '2024-02-07'
        assert result['media_index'] == 1
        assert result['title'] is None
        assert result['title_clean'] is None
        assert result['ext'] == 'jpeg'

    def test_filename_with_title(self):
        result = helper.decompose_filename('231231012_Christmas_Party.png')
        assert result['media_index'] == 12
        assert result['title'] == 'Christmas_Party'
        assert result['title_clean'] == 'Christmas Party'


class TestSerializeDeserializeFilepath:
    def test_roundtrip(self, tmp_root):
        original = os.path.join(str(tmp_root), '2025', '10', '251025004.heic')
        serialized = helper.serialize_filepath(original)
        assert serialized == f'2025|/10|/251025004.heic'
        assert helper.deserialize_filepath(serialized) == original


class TestGetYearFromFilepath:
    def test_extracts_year(self, tmp_root):
        filepath = os.path.join(str(tmp_root), '2025', '10', '251025004.heic')
        assert helper.get_year_from_filepath(filepath) == 2025

    def test_raises_for_new_media(self, tmp_root):
        new_media_path = os.path.join(str(tmp_root), 'new', '251025004.heic')
        with pytest.raises(RuntimeError):
            helper.get_year_from_filepath(new_media_path)


class TestGetFilepathsByDirectory:
    def test_finds_media_recursively_and_ignores_new(self, tmp_root):
        year_dir = tmp_root / '2025' / '10'
        year_dir.mkdir(parents=True)
        (year_dir / '251025001.jpg').write_bytes(b'x')
        (year_dir / '251025002.HEIC').write_bytes(b'x')
        (year_dir / 'notes.txt').write_bytes(b'x')

        new_dir = tmp_root / 'new'
        new_dir.mkdir()
        (new_dir / '999.jpg').write_bytes(b'x')

        found = helper.get_filepaths_by_directory(str(tmp_root))
        found_names = sorted(os.path.basename(f) for f in found)
        assert found_names == ['251025001.jpg', '251025002.HEIC']

    def test_dedupes_case_insensitive_matches_on_windows(self, tmp_root):
        # constants.MEDIA_EXTENSIONS contains both 'jpg' and 'JPG'; on a case-insensitive
        # filesystem both glob patterns match the same file, and results must be deduped.
        year_dir = tmp_root / '2025' / '10'
        year_dir.mkdir(parents=True)
        (year_dir / '251025001.jpg').write_bytes(b'x')

        found = helper.get_filepaths_by_directory(str(tmp_root))
        assert len(found) == 1


class TestKeywordIsName:
    def test_matches_camel_case_name(self):
        assert helper.keyword_is_name('JohnSmith') is True

    def test_rejects_plain_tag(self):
        assert helper.keyword_is_name('vacation') is False


class TestTryExcept:
    def test_returns_success_value(self):
        assert helper.try_except(lambda: 1 / 1, 'failed') == 1

    def test_returns_failure_value_on_exception(self):
        assert helper.try_except(lambda: 1 / 0, 'failed') == 'failed'

    def test_calls_failure_callable_on_exception(self):
        assert helper.try_except(lambda: 1 / 0, lambda: 'computed') == 'computed'

    def test_only_catches_specified_exceptions(self):
        with pytest.raises(ZeroDivisionError):
            helper.try_except(lambda: 1 / 0, 'failed', TypeError)
