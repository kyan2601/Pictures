import os

import pandas as pd
from datetime import datetime

import pytest
from conftest import seed_media
from PIL import Image

from src.classes.entities.MetadataFile import MetadataFile
from src.classes.workflows.MetadataCleanupChecks import MetadataCleanupChecks


def _write_png(path):
    # PNG needs no EXIF and has no external-binary dependency, so a real file here
    # exercises the real media_class_factory extraction path with zero fragility.
    Image.new('RGB', (4, 4), color=(255, 0, 0)).save(str(path), 'PNG')


class TestNoIssues:
    def test_returns_true_and_renames_nothing_when_already_in_order(self, tmp_root):
        paths = seed_media(tmp_root, 2025, 1, [
            ('250101001.jpg', datetime(2025, 1, 1, 9, 0)),
            ('250101002.jpg', datetime(2025, 1, 1, 10, 0)),
        ])

        checker = MetadataCleanupChecks(year=2025)
        result = checker._reorder_media_by_datetime(dry_run=False)

        assert result is True
        assert os.path.exists(paths['250101001.jpg'])
        assert os.path.exists(paths['250101002.jpg'])


class TestDryRun:
    def test_detects_but_does_not_rename(self, tmp_root):
        # dt order is reversed relative to filename index -> needs reordering.
        paths = seed_media(tmp_root, 2025, 1, [
            ('250101001.jpg', datetime(2025, 1, 1, 10, 0)),
            ('250101002.jpg', datetime(2025, 1, 1, 9, 0)),
        ])

        checker = MetadataCleanupChecks(year=2025)
        result = checker._reorder_media_by_datetime(dry_run=True)

        assert result is False
        # Nothing on disk should have moved.
        assert os.path.exists(paths['250101001.jpg'])
        assert os.path.exists(paths['250101002.jpg'])


class TestSuccessfulReorder:
    def test_renames_files_and_updates_metadata(self, tmp_root):
        # Three-way cyclic mismatch: every file's target name is another file's
        # current name, forcing the code through its tmp-rename staging (the whole
        # reason the 3-phase approach exists).
        paths = seed_media(tmp_root, 2025, 1, [
            ('250101001.jpg', datetime(2025, 1, 1, 12, 0)),  # should become ...003
            ('250101002.jpg', datetime(2025, 1, 1, 8, 0)),   # should become ...001
            ('250101003.jpg', datetime(2025, 1, 1, 10, 0)),  # should become ...002
        ])

        checker = MetadataCleanupChecks(year=2025)
        result = checker._reorder_media_by_datetime(dry_run=False)

        assert result is False  # issues were found (and fixed)

        month_dir = tmp_root / '2025' / '01'

        # It's a 3-way cyclic permutation, so all three original filenames still exist
        # afterward -- what matters is which *content* ended up under which name.
        assert (month_dir / '250101003.jpg').read_bytes() == b'250101001.jpg'
        assert (month_dir / '250101001.jpg').read_bytes() == b'250101002.jpg'
        assert (month_dir / '250101002.jpg').read_bytes() == b'250101003.jpg'

        # No leftover staging files.
        assert not any(f.name.endswith('.tmp_reorder') for f in month_dir.iterdir())

        # Metadata still points at exactly the same (now-renamed) locations on disk.
        mf = MetadataFile.get_instance(2025)
        assert set(mf.df['filepath']) == set(paths.values())


class TestRollbackOnFailure:
    def test_restores_original_filenames_and_metadata_on_mid_rename_failure(self, tmp_root, monkeypatch):
        paths = seed_media(tmp_root, 2025, 1, [
            ('250101001.jpg', datetime(2025, 1, 1, 12, 0)),
            ('250101002.jpg', datetime(2025, 1, 1, 8, 0)),
            ('250101003.jpg', datetime(2025, 1, 1, 10, 0)),
        ])
        original_metadata_csv = MetadataFile.get_instance(2025).filepath
        original_csv_contents = open(original_metadata_csv, 'rb').read()

        import src.classes.workflows.MetadataCleanupChecks as mcc_module
        real_rename = os.rename
        call_count = {'n': 0}

        def flaky_rename(src, dst):
            call_count['n'] += 1
            # Calls 1-3 are Phase 1 (original -> .tmp_reorder), all succeed.
            # Call 4 is the first Phase 2 rename (.tmp_reorder -> final), succeeds.
            # Call 5 is the second Phase 2 rename -- fail here, mid-phase.
            if call_count['n'] == 5:
                raise OSError("simulated rename failure")
            return real_rename(src, dst)

        monkeypatch.setattr(mcc_module.os, 'rename', flaky_rename)

        checker = MetadataCleanupChecks(year=2025)
        with pytest.raises(OSError):
            checker._reorder_media_by_datetime(dry_run=False)

        month_dir = tmp_root / '2025' / '01'

        # Every original file must be back under its original name.
        for filename in paths:
            assert (month_dir / filename).exists(), f"{filename} was not restored"

        # No file should be left in the intermediate .tmp_reorder state.
        assert not any(f.name.endswith('.tmp_reorder') for f in month_dir.iterdir())

        # The on-disk metadata file was never rewritten (failure happened before Phase 3).
        assert open(original_metadata_csv, 'rb').read() == original_csv_contents

        # The in-memory metadata_file was reloaded from the (untouched) disk state.
        reloaded_paths = set(MetadataFile.get_instance(2025).df['filepath'])
        assert reloaded_paths == set(paths.values())


class TestCheckForUnindexedMedia:
    def test_indexes_files_found_on_disk_but_missing_from_metadata(self, tmp_root):
        MetadataFile.get_instance(2025)  # ensures the (empty) metadata file exists
        month_dir = tmp_root / '2025' / '06'
        month_dir.mkdir(parents=True)
        _write_png(month_dir / '250615001.png')

        checker = MetadataCleanupChecks(year=2025)
        result = checker._check_for_unindexed_media(dry_run=False)

        assert result is False
        mf = MetadataFile.get_instance(2025)
        assert str(month_dir / '250615001.png') in set(mf.df['filepath'])

    def test_dry_run_detects_but_does_not_index(self, tmp_root):
        MetadataFile.get_instance(2025)
        month_dir = tmp_root / '2025' / '06'
        month_dir.mkdir(parents=True)
        _write_png(month_dir / '250615001.png')

        checker = MetadataCleanupChecks(year=2025)
        result = checker._check_for_unindexed_media(dry_run=True)

        assert result is False
        assert MetadataFile.get_instance(2025).df.empty

    def test_returns_true_when_nothing_unindexed(self, tmp_root):
        seed_media(tmp_root, 2025, 6, [('250615001.jpg', datetime(2025, 6, 15, 9, 0))])

        checker = MetadataCleanupChecks(year=2025)
        assert checker._check_for_unindexed_media(dry_run=False) is True

    def test_backs_up_metadata_before_modifying(self, tmp_root):
        seed_media(tmp_root, 2025, 6, [('250615001.jpg', datetime(2025, 6, 15, 9, 0))])
        month_dir = tmp_root / '2025' / '06'
        _write_png(month_dir / '250615002.png')

        checker = MetadataCleanupChecks(year=2025)
        checker._check_for_unindexed_media(dry_run=False)

        backup_dirs = list((tmp_root / 'backup').iterdir())
        assert len(backup_dirs) == 1
        assert (backup_dirs[0] / 'metadata.csv').exists()


class TestCheckForDeletedMedia:
    def test_removes_metadata_for_files_no_longer_on_disk(self, tmp_root):
        paths = seed_media(tmp_root, 2025, 6, [('250615001.jpg', datetime(2025, 6, 15, 9, 0))])
        os.remove(paths['250615001.jpg'])

        checker = MetadataCleanupChecks(year=2025)
        result = checker._check_for_deleted_media(dry_run=False)

        assert result is False
        assert MetadataFile.get_instance(2025).df.empty

    def test_dry_run_detects_but_does_not_modify(self, tmp_root):
        paths = seed_media(tmp_root, 2025, 6, [('250615001.jpg', datetime(2025, 6, 15, 9, 0))])
        os.remove(paths['250615001.jpg'])

        checker = MetadataCleanupChecks(year=2025)
        result = checker._check_for_deleted_media(dry_run=True)

        assert result is False
        assert not MetadataFile.get_instance(2025).df.empty

    def test_returns_true_when_nothing_deleted(self, tmp_root):
        seed_media(tmp_root, 2025, 6, [('250615001.jpg', datetime(2025, 6, 15, 9, 0))])

        checker = MetadataCleanupChecks(year=2025)
        assert checker._check_for_deleted_media(dry_run=False) is True

    def test_saves_deleted_rows_to_a_backup_csv(self, tmp_root):
        paths = seed_media(tmp_root, 2025, 6, [('250615001.jpg', datetime(2025, 6, 15, 9, 0))])
        os.remove(paths['250615001.jpg'])

        checker = MetadataCleanupChecks(year=2025)
        checker._check_for_deleted_media(dry_run=False)

        backup_dirs = list((tmp_root / 'backup').iterdir())
        assert len(backup_dirs) == 1
        deleted_csv = backup_dirs[0] / 'deleted_metadata_2025.csv'
        assert deleted_csv.exists()


def _write_jpeg(path, color=(255, 0, 0)):
    Image.new('RGB', (40, 40), color=color).save(str(path), 'JPEG')


def _seed_media_records(tmp_root, records):
    month_dir = tmp_root / '2025' / '06'
    month_dir.mkdir(parents=True, exist_ok=True)
    MetadataFile.get_instance(2025).add_media_metadata(records)
    return month_dir


class TestMissingPixelHashes:
    def _seed(self, tmp_root):
        month_dir = _seed_media_records(tmp_root, [
            {'filepath': str(tmp_root / '2025' / '06' / 'hashed.jpg'),
             'dt': datetime(2025, 6, 1, 10, 0), 'phash': 'abcd1234', 'dhash': 'efgh5678'},
            {'filepath': str(tmp_root / '2025' / '06' / 'nohash.jpg'),
             'dt': datetime(2025, 6, 2, 10, 0)},
        ])
        _write_jpeg(month_dir / 'hashed.jpg')
        _write_jpeg(month_dir / 'nohash.jpg', color=(0, 255, 0))
        return month_dir

    def test_dry_run_reports_but_does_not_backfill(self, tmp_root, capsys):
        self._seed(tmp_root)

        result = MetadataCleanupChecks(2025)._check_for_missing_pixel_hashes(dry_run=True)

        assert result is False
        assert '1 picture(s) missing pixel hashes' in capsys.readouterr().out
        record = MetadataFile.get_instance(2025).get_media_metadata(
            str(tmp_root / '2025' / '06' / 'nohash.jpg'))
        assert pd.isna(record['phash'])

    def test_execute_backfills_hashes(self, tmp_root):
        self._seed(tmp_root)

        result = MetadataCleanupChecks(2025)._check_for_missing_pixel_hashes(dry_run=False)

        assert result is True
        record = MetadataFile.get_instance(2025).get_media_metadata(
            str(tmp_root / '2025' / '06' / 'nohash.jpg'))
        assert record['phash'] and record['dhash']
        assert len(record['phash']) == 16  # imagehash hex digest

    def test_returns_true_when_all_hashes_present(self, tmp_root):
        month_dir = _seed_media_records(tmp_root, [
            {'filepath': str(tmp_root / '2025' / '06' / 'hashed.jpg'),
             'dt': datetime(2025, 6, 1, 10, 0), 'phash': 'abcd1234', 'dhash': 'efgh5678'},
        ])
        _write_jpeg(month_dir / 'hashed.jpg')

        assert MetadataCleanupChecks(2025)._check_for_missing_pixel_hashes(dry_run=False) is True

    def test_videos_are_not_required_to_have_hashes(self, tmp_root):
        month_dir = _seed_media_records(tmp_root, [
            {'filepath': str(tmp_root / '2025' / '06' / 'clip.mp4'),
             'dt': datetime(2025, 6, 1, 10, 0)},
        ])
        (month_dir / 'clip.mp4').write_bytes(b'fake-video-bytes')

        assert MetadataCleanupChecks(2025)._check_for_missing_pixel_hashes(dry_run=False) is True


class TestUnreadableFiles:
    def _seed(self, tmp_root):
        month_dir = _seed_media_records(tmp_root, [
            {'filepath': str(tmp_root / '2025' / '06' / 'good.jpg'),
             'dt': datetime(2025, 6, 1, 10, 0)},
            {'filepath': str(tmp_root / '2025' / '06' / 'corrupt.jpg'),
             'dt': datetime(2025, 6, 2, 10, 0)},
            {'filepath': str(tmp_root / '2025' / '06' / 'empty.mp4'),
             'dt': datetime(2025, 6, 3, 10, 0)},
            {'filepath': str(tmp_root / '2025' / '06' / 'gone.jpg'),
             'dt': datetime(2025, 6, 4, 10, 0)},
        ])
        _write_jpeg(month_dir / 'good.jpg')
        (month_dir / 'corrupt.jpg').write_bytes(b'this is not a jpeg')
        (month_dir / 'empty.mp4').write_bytes(b'')
        # gone.jpg is indexed but absent from disk: owned by _check_for_deleted_media
        return month_dir

    def test_flags_corrupt_and_empty_files(self, tmp_root, capsys):
        self._seed(tmp_root)

        result = MetadataCleanupChecks(2025)._check_for_unreadable_files()

        assert result is False
        out = capsys.readouterr().out
        assert 'corrupt.jpg' in out
        assert 'empty.mp4' in out
        assert 'good.jpg' not in out
        assert 'gone.jpg' not in out  # missing files belong to the deleted-media check

    def test_returns_true_when_all_readable(self, tmp_root):
        month_dir = _seed_media_records(tmp_root, [
            {'filepath': str(tmp_root / '2025' / '06' / 'good.jpg'),
             'dt': datetime(2025, 6, 1, 10, 0)},
        ])
        _write_jpeg(month_dir / 'good.jpg')

        assert MetadataCleanupChecks(2025)._check_for_unreadable_files() is True
