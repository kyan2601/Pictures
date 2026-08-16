import os
from datetime import datetime

import pytest
from conftest import seed_media

from src.classes.entities.MetadataFile import MetadataFile
from src.classes.workflows.MetadataCleanupChecks import MetadataCleanupChecks


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
