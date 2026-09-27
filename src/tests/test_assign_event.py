import os
import shutil

import pytest

from src.classes.entities.EventsMetadataFile import EventsMetadataFile
from src.classes.entities.MetadataFile import MetadataFile
from src.classes.workflows.AssignEvent import AssignEvent
from src.tests.conftest import seed_media


def _make_event(events_file, title='Trip', start_date='2025-06-01', end_date='2025-06-01'):
    return EventsMetadataFile.get_instance().create_event(
        title=title, start_date=start_date, end_date=end_date)


def _event_dir(event):
    return event.get_directory()


class TestAssignEvent:
    def test_dry_run_changes_nothing(self, tmp_root, events_file, capsys):
        event = _make_event(events_file)
        files = seed_media(tmp_root, 2025, 7, [('a.jpg', '2025-07-04')])

        AssignEvent(dry_run=True).run([files['a.jpg']], event.event_id)

        out = capsys.readouterr().out
        assert '[dry run]' in out
        assert os.path.exists(files['a.jpg'])
        assert not os.path.exists(_event_dir(event))

    def test_execute_moves_files_and_updates_metadata(self, tmp_root, events_file):
        event = _make_event(events_file)
        files = seed_media(tmp_root, 2025, 7,
                           [('a.jpg', '2025-07-04'), ('b.jpg', '2025-07-05')])

        AssignEvent(dry_run=False).run([files['a.jpg'], files['b.jpg']], event.event_id)

        event_dir = _event_dir(event)
        for name in ('a.jpg', 'b.jpg'):
            new_path = os.path.join(event_dir, name)
            assert os.path.exists(new_path)
            assert not os.path.exists(files[name])
            md = MetadataFile.get_instance(2025).get_media_metadata(new_path)
            assert md['event_id'] == event.event_id

        # originals land in a timestamped backup directory
        backup_contents = []
        for entry in os.listdir(os.path.join(str(tmp_root), 'backup')):
            backup_contents += os.listdir(os.path.join(str(tmp_root), 'backup', entry))
        assert sorted(backup_contents) == ['a.jpg', 'b.jpg']

    def test_unknown_event_raises(self, tmp_root, events_file):
        files = seed_media(tmp_root, 2025, 7, [('a.jpg', '2025-07-04')])

        with pytest.raises(RuntimeError, match='No event found'):
            AssignEvent(dry_run=False).run([files['a.jpg']], 999)

    def test_file_without_metadata_is_skipped(self, tmp_root, events_file, capsys):
        event = _make_event(events_file)
        files = seed_media(tmp_root, 2025, 7, [('a.jpg', '2025-07-04')])
        ghost = str(tmp_root / '2025' / '07' / 'ghost.jpg')
        open(ghost, 'w').write('x')

        AssignEvent(dry_run=False).run([files['a.jpg'], ghost], event.event_id)

        assert '[skip] no metadata record' in capsys.readouterr().out
        assert os.path.exists(os.path.join(_event_dir(event), 'a.jpg'))

    def test_file_in_another_event_raises(self, tmp_root, events_file):
        event_a = _make_event(events_file, title='Trip A')
        event_b = _make_event(events_file, title='Trip B',
                              start_date='2025-08-01', end_date='2025-08-01')
        files = seed_media(tmp_root, 2025, 7, [('a.jpg', '2025-07-04')])
        AssignEvent(dry_run=False).run([files['a.jpg']], event_a.event_id)

        new_path = os.path.join(_event_dir(event_a), 'a.jpg')
        with pytest.raises(RuntimeError, match='already belongs to event'):
            AssignEvent(dry_run=False).run([new_path], event_b.event_id)

    def test_file_already_in_same_event_is_skipped(self, tmp_root, events_file, capsys):
        event = _make_event(events_file)
        files = seed_media(tmp_root, 2025, 7, [('a.jpg', '2025-07-04')])
        AssignEvent(dry_run=False).run([files['a.jpg']], event.event_id)

        new_path = os.path.join(_event_dir(event), 'a.jpg')
        AssignEvent(dry_run=False).run([new_path], event.event_id)

        assert 'already in event' in capsys.readouterr().out

    def test_name_collision_raises(self, tmp_root, events_file):
        event = _make_event(events_file)
        files = seed_media(tmp_root, 2025, 7, [('a.jpg', '2025-07-04')])
        other_dir = tmp_root / '2025' / '08'
        other_dir.mkdir(parents=True, exist_ok=True)
        # a different file that would land on the same target name
        clash = other_dir / 'a.jpg'
        clash.write_bytes(b'different-bytes')
        MetadataFile.get_instance(2025).add_media_metadata(
            {'filepath': str(clash), 'dt': '2025-08-01'})

        os.makedirs(_event_dir(event), exist_ok=True)
        open(os.path.join(_event_dir(event), 'a.jpg'), 'w').write('occupant')

        with pytest.raises(RuntimeError, match='already exists'):
            AssignEvent(dry_run=False).run([files['a.jpg'], str(clash)], event.event_id)

        # nothing was moved: the first file is still in place
        assert os.path.exists(files['a.jpg'])

    def test_copy_failure_rolls_back_copies(self, tmp_root, events_file, monkeypatch):
        event = _make_event(events_file)
        files = seed_media(tmp_root, 2025, 7,
                           [('a.jpg', '2025-07-04'), ('b.jpg', '2025-07-05')])

        real_copy2 = shutil.copy2

        def flaky_copy2(src, dst, *a, **k):
            if os.path.basename(src) == 'b.jpg':
                raise OSError('disk on fire')
            return real_copy2(src, dst, *a, **k)

        monkeypatch.setattr(shutil, 'copy2', flaky_copy2)

        with pytest.raises(OSError, match='disk on fire'):
            AssignEvent(dry_run=False).run([files['a.jpg'], files['b.jpg']], event.event_id)

        # the partial copy was cleaned up; originals and metadata untouched
        assert os.listdir(_event_dir(event)) == []
        assert os.path.exists(files['a.jpg'])
        assert os.path.exists(files['b.jpg'])
