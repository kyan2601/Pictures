from datetime import datetime

import pytest
from conftest import seed_media

from src.classes.entities.EventsMetadataFile import EventsMetadataFile
from src.classes.entities.MetadataFile import MetadataFile


class TestNextEventId:
    def test_starts_at_one_when_empty(self, events_file):
        assert EventsMetadataFile.get_instance()._next_event_id() == 1

    def test_increments_from_max(self, events_file):
        emf = EventsMetadataFile.get_instance()
        emf.create_event(title='First', start_date='2025-01-01', end_date='2025-01-02')
        assert emf._next_event_id() == 2


class TestValidation:
    def test_rejects_start_after_end(self, events_file):
        emf = EventsMetadataFile.get_instance()
        with pytest.raises(RuntimeError):
            emf.create_event(title='Backwards', start_date='2025-01-10', end_date='2025-01-01')

    def test_rejects_overlapping_date_range(self, events_file):
        emf = EventsMetadataFile.get_instance()
        emf.create_event(title='First', start_date='2025-01-01', end_date='2025-01-10')

        with pytest.raises(RuntimeError, match='overlaps'):
            emf.create_event(title='Second', start_date='2025-01-05', end_date='2025-01-15')

        # The rejected event must not have been committed.
        assert len(EventsMetadataFile.get_instance().df) == 1

    def test_rejects_media_already_assigned_to_an_event(self, tmp_root, events_file):
        seed_media(tmp_root, 2025, 1, [('250101001.jpg', datetime(2025, 1, 1, 9, 0))])
        mf = MetadataFile.get_instance(2025)
        mf.df.loc[mf.df.index[0], 'event_id'] = 1
        mf.write()

        emf = EventsMetadataFile.get_instance()
        with pytest.raises(RuntimeError, match='already belong'):
            emf.create_event(title='Reuse', start_date='2025-01-01', end_date='2025-01-01')


class TestCreateEventWithoutMedia:
    def test_creates_event_entry_only(self, events_file):
        emf = EventsMetadataFile.get_instance()
        event = emf.create_event(title='Empty Range', start_date='2025-02-01', end_date='2025-02-02')

        assert event.event_id == 1
        reloaded = EventsMetadataFile.get_instance()
        assert list(reloaded.df['title']) == ['Empty Range']


class TestCreateEventWithBackup:
    def test_moves_media_into_event_directory_and_updates_metadata(self, tmp_root, events_file):
        paths = seed_media(tmp_root, 2025, 6, [
            ('250615001.jpg', datetime(2025, 6, 15, 9, 0)),
            ('250615002.jpg', datetime(2025, 6, 15, 10, 0)),
        ])

        emf = EventsMetadataFile.get_instance()
        event = emf.create_event(title='Summer Trip', start_date='2025-06-15', end_date='2025-06-15')

        event_dir = tmp_root / '2025' / f'06_1_June_Summer_Trip'
        assert (event_dir / '250615001.jpg').read_bytes() == b'250615001.jpg'
        assert (event_dir / '250615002.jpg').read_bytes() == b'250615002.jpg'

        # Originals are gone from their source location (moved to backup).
        assert not (tmp_root / '2025' / '06' / '250615001.jpg').exists()
        assert not (tmp_root / '2025' / '06' / '250615002.jpg').exists()

        mf = MetadataFile.get_instance(2025)
        assert set(mf.df['filepath']) == {str(event_dir / '250615001.jpg'), str(event_dir / '250615002.jpg')}
        assert (mf.df['event_id'] == event.event_id).all()

        events_df = EventsMetadataFile.get_instance().df
        assert list(events_df['title']) == ['Summer Trip']

    def test_leaves_originals_in_backup_on_failure_after_move(self, tmp_root, events_file, monkeypatch):
        # Once files are moved to the backup dir, the code documents this as a
        # CRITICAL, manually-recoverable state rather than auto-rolling-back --
        # this test pins down that documented (if uncomfortable) behavior.
        paths = seed_media(tmp_root, 2025, 6, [
            ('250615001.jpg', datetime(2025, 6, 15, 9, 0)),
        ])

        import src.classes.entities.EventsMetadataFile as emf_module

        def flaky_copy2(src, dst):
            raise OSError("simulated copy failure")

        monkeypatch.setattr(emf_module.shutil, 'copy2', flaky_copy2)

        emf = EventsMetadataFile.get_instance()
        with pytest.raises(OSError):
            emf.create_event(title='Summer Trip', start_date='2025-06-15', end_date='2025-06-15')

        # Original is gone from its source location...
        assert not (tmp_root / '2025' / '06' / '250615001.jpg').exists()
        # ...but recoverable from the backup directory.
        backup_dirs = list((tmp_root / 'backup').iterdir())
        assert len(backup_dirs) == 1
        assert (backup_dirs[0] / '250615001.jpg').read_bytes() == b'250615001.jpg'

        # No event was committed, and source metadata was left untouched.
        assert EventsMetadataFile.get_instance().df.empty
        assert set(MetadataFile.get_instance(2025).df['filepath']) == set(paths.values())


class TestCreateEventWithoutBackup:
    def test_rolls_back_event_directory_on_failure_before_deletion(self, tmp_root, events_file, monkeypatch):
        # backup=False copies originals into the event dir first and only deletes them
        # after metadata/events are committed -- a failure during the copy phase should
        # leave the originals completely untouched and clean up the partial event dir.
        paths = seed_media(tmp_root, 2025, 6, [
            ('250615001.jpg', datetime(2025, 6, 15, 9, 0)),
            ('250615002.jpg', datetime(2025, 6, 15, 10, 0)),
        ])

        import src.classes.entities.EventsMetadataFile as emf_module
        real_copy2 = emf_module.shutil.copy2
        call_count = {'n': 0}

        def flaky_copy2(src, dst):
            call_count['n'] += 1
            if call_count['n'] == 2:
                raise OSError("simulated copy failure")
            return real_copy2(src, dst)

        monkeypatch.setattr(emf_module.shutil, 'copy2', flaky_copy2)

        emf = EventsMetadataFile.get_instance()
        with pytest.raises(OSError):
            emf.create_event(title='Summer Trip', start_date='2025-06-15', end_date='2025-06-15', backup=False)

        # Originals were never touched.
        assert (tmp_root / '2025' / '06' / '250615001.jpg').read_bytes() == b'250615001.jpg'
        assert (tmp_root / '2025' / '06' / '250615002.jpg').read_bytes() == b'250615002.jpg'

        # The partially-populated event directory was cleaned up.
        event_dir = tmp_root / '2025' / '06_1_June_Summer_Trip'
        assert not event_dir.exists()

        # No event was committed, and source metadata was left untouched.
        assert EventsMetadataFile.get_instance().df.empty
        assert set(MetadataFile.get_instance(2025).df['filepath']) == set(paths.values())
