import shutil
from datetime import datetime

from src import constants
from src.classes.entities.MetadataFile import MetadataFile
from src.classes.workflows import AssignDate as assign_date_module
from src.classes.workflows.AssignDate import AssignDate


class _FakeMediaEntry:
    """
    Same rationale as ProcessNewMedia's tests: AssignDate's placement/renaming logic
    only depends on .filepath/.dt/.ext/.move()/.to_dict(), never on real pixel/EXIF
    data, so a real JPEG/HEIC/MOV isn't needed here.
    """

    def __init__(self, filepath, dt, ext):
        self.filepath = filepath
        self.dt = dt
        self.ext = ext

    def move(self, new_path):
        shutil.move(self.filepath, new_path)
        self.filepath = new_path

    def to_dict(self):
        return {'filepath': self.filepath, 'dt': self.dt}


def _fake_factory(ext=constants.PictureExtension.JPG):
    def create(filepath):
        return _FakeMediaEntry(filepath, datetime(2000, 1, 1), ext)
    return create


def _patch_factory(monkeypatch, ext=constants.PictureExtension.JPG):
    monkeypatch.setattr(assign_date_module.media_class_factory, 'create_media_entry', _fake_factory(ext))


class TestFilterAndOrder:
    def test_skips_dot_underscore_and_non_media_files(self, tmp_root, monkeypatch):
        _patch_factory(monkeypatch)
        new_dir = tmp_root / 'new'
        new_dir.mkdir()
        (new_dir / 'photo.jpg').write_bytes(b'x')
        (new_dir / '._photo.jpg').write_bytes(b'x')
        (new_dir / 'notes.txt').write_bytes(b'x')

        assigner = AssignDate(dry_run=False)
        assigner.run([str(new_dir / 'photo.jpg'), str(new_dir / '._photo.jpg'), str(new_dir / 'notes.txt')],
                     '2025-06-15')

        assert len(assigner.media) == 1
        assert (tmp_root / '2025' / '06' / '250615001.jpg').exists()

    def test_orders_by_embedded_sequence_number_when_all_files_have_it(self, tmp_root, monkeypatch):
        _patch_factory(monkeypatch)
        new_dir = tmp_root / 'new'
        new_dir.mkdir()
        # Deliberately named so alphabetical order would be wrong: 'b' sorts after 'a'
        # alphabetically but is sequence 5, which must come before sequence 89.
        (new_dir / 'b Trip - 89 of 491.jpg').write_bytes(b'first')
        (new_dir / 'a Trip - 5 of 491.jpg').write_bytes(b'second')

        assigner = AssignDate(dry_run=False)
        assigner.run(
            [str(new_dir / 'b Trip - 89 of 491.jpg'), str(new_dir / 'a Trip - 5 of 491.jpg')],
            '2025-06-15')

        month_dir = tmp_root / '2025' / '06'
        # Sequence 5 (originally 'second' content) must land at index 001.
        assert (month_dir / '250615001.jpg').read_bytes() == b'second'
        assert (month_dir / '250615002.jpg').read_bytes() == b'first'

    def test_falls_back_to_natural_sort_when_any_file_lacks_sequence_number(self, tmp_root, monkeypatch):
        _patch_factory(monkeypatch)
        new_dir = tmp_root / 'new'
        new_dir.mkdir()
        # One file has the 'N of TOTAL' pattern, one doesn't -- must fall back to
        # natural sort for the whole batch rather than partially trust the pattern.
        (new_dir / 'IMG_2.jpg').write_bytes(b'second')
        (new_dir / 'IMG_10 of 50.jpg').write_bytes(b'third')
        (new_dir / 'IMG_1.jpg').write_bytes(b'first')

        assigner = AssignDate(dry_run=False)
        assigner.run(
            [str(new_dir / 'IMG_2.jpg'), str(new_dir / 'IMG_10 of 50.jpg'), str(new_dir / 'IMG_1.jpg')],
            '2025-06-15')

        month_dir = tmp_root / '2025' / '06'
        # Natural sort: IMG_1 < IMG_2 < IMG_10 (not alphabetical, which would put IMG_10 second).
        assert (month_dir / '250615001.jpg').read_bytes() == b'first'
        assert (month_dir / '250615002.jpg').read_bytes() == b'second'
        assert (month_dir / '250615003.jpg').read_bytes() == b'third'

    def test_no_op_when_nothing_matches(self, tmp_root, monkeypatch):
        _patch_factory(monkeypatch)
        new_dir = tmp_root / 'new'
        new_dir.mkdir()
        (new_dir / 'notes.txt').write_bytes(b'x')

        assigner = AssignDate(dry_run=False)
        assigner.run([str(new_dir / 'notes.txt')], '2025-06-15')

        assert "No matching media files to assign." in assigner.run_log
        assert not (tmp_root / '2025').exists()


class TestLivePhotoMovies:
    def test_paired_mov_is_excluded_and_moved_to_backup(self, tmp_root, monkeypatch):
        _patch_factory(monkeypatch)
        new_dir = tmp_root / 'new'
        new_dir.mkdir()
        (new_dir / 'IMG_001.jpg').write_bytes(b'picture')
        (new_dir / 'IMG_001.mov').write_bytes(b'live-photo-video')
        (new_dir / 'IMG_002.jpg').write_bytes(b'unpaired')

        assigner = AssignDate(dry_run=False)
        assigner.run(
            [str(new_dir / 'IMG_001.jpg'), str(new_dir / 'IMG_001.mov'), str(new_dir / 'IMG_002.jpg')],
            '2025-06-15')

        # Only the two pictures were assigned; the paired .mov was excluded.
        assert len(assigner.media) == 2
        month_dir = tmp_root / '2025' / '06'
        assert {p.read_bytes() for p in month_dir.glob('*.jpg')} == {b'picture', b'unpaired'}

        # The .mov was moved to backup, not left in new/ and not assigned a date.
        assert not (new_dir / 'IMG_001.mov').exists()
        backup_dirs = list((tmp_root / 'backup').iterdir())
        live_photo_backup = [d for d in backup_dirs if d.name.endswith('live_photo_removal')]
        assert len(live_photo_backup) == 1
        assert (live_photo_backup[0] / 'IMG_001.mov').read_bytes() == b'live-photo-video'

    def test_unpaired_mov_is_kept_and_assigned(self, tmp_root, monkeypatch):
        _patch_factory(monkeypatch, ext=constants.VideoExtension.MOV)
        new_dir = tmp_root / 'new'
        new_dir.mkdir()
        (new_dir / 'clip.mov').write_bytes(b'standalone-video')

        assigner = AssignDate(dry_run=False)
        assigner.run([str(new_dir / 'clip.mov')], '2025-06-15')

        assert len(assigner.media) == 1
        assert (tmp_root / '2025' / '06' / '250615001.mov').read_bytes() == b'standalone-video'

    def test_dry_run_leaves_paired_mov_in_place(self, tmp_root, monkeypatch):
        _patch_factory(monkeypatch)
        new_dir = tmp_root / 'new'
        new_dir.mkdir()
        (new_dir / 'IMG_001.jpg').write_bytes(b'picture')
        (new_dir / 'IMG_001.mov').write_bytes(b'live-photo-video')

        assigner = AssignDate(dry_run=True)
        assigner.run([str(new_dir / 'IMG_001.jpg'), str(new_dir / 'IMG_001.mov')], '2025-06-15')

        assert (new_dir / 'IMG_001.mov').exists()
        assert not (tmp_root / 'backup').exists()
        assert len(assigner.media) == 1  # only the picture would be assigned


class TestSyntheticTimestamps:
    def test_assigns_one_second_increments_in_determined_order(self, tmp_root, monkeypatch):
        _patch_factory(monkeypatch)
        new_dir = tmp_root / 'new'
        new_dir.mkdir()
        (new_dir / 'a.jpg').write_bytes(b'x')
        (new_dir / 'b.jpg').write_bytes(b'x')
        (new_dir / 'c.jpg').write_bytes(b'x')

        assigner = AssignDate(dry_run=False)
        assigner.run(
            [str(new_dir / 'a.jpg'), str(new_dir / 'b.jpg'), str(new_dir / 'c.jpg')],
            '2025-06-15')

        mf = MetadataFile.get_instance(2025)
        dts = sorted(mf.df['dt'])
        assert [dt.time().isoformat() for dt in dts] == ['00:00:01', '00:00:02', '00:00:03']
        assert all(dt.date().isoformat() == '2025-06-15' for dt in dts)


class TestPlacement:
    def test_continues_numbering_after_existing_files(self, tmp_root, monkeypatch):
        _patch_factory(monkeypatch)
        month_dir = tmp_root / '2025' / '06'
        month_dir.mkdir(parents=True)
        (month_dir / '250615001.jpg').write_bytes(b'existing')

        new_dir = tmp_root / 'new'
        new_dir.mkdir()
        (new_dir / 'a.jpg').write_bytes(b'new')

        assigner = AssignDate(dry_run=False)
        assigner.run([str(new_dir / 'a.jpg')], '2025-06-15')

        assert (month_dir / '250615002.jpg').read_bytes() == b'new'
        assert (month_dir / '250615001.jpg').read_bytes() == b'existing'

    def test_dry_run_does_not_move_or_write_metadata(self, tmp_root, monkeypatch):
        _patch_factory(monkeypatch)
        new_dir = tmp_root / 'new'
        new_dir.mkdir()
        (new_dir / 'a.jpg').write_bytes(b'x')

        assigner = AssignDate(dry_run=True)
        assigner.run([str(new_dir / 'a.jpg')], '2025-06-15')

        assert (new_dir / 'a.jpg').exists()
        assert not (tmp_root / '2025').exists()

    def test_writes_metadata_for_the_target_year(self, tmp_root, monkeypatch):
        _patch_factory(monkeypatch)
        new_dir = tmp_root / 'new'
        new_dir.mkdir()
        (new_dir / 'a.jpg').write_bytes(b'x')

        assigner = AssignDate(dry_run=False)
        assigner.run([str(new_dir / 'a.jpg')], '2025-06-15')

        mf = MetadataFile.get_instance(2025)
        assert str(tmp_root / '2025' / '06' / '250615001.jpg') in set(mf.df['filepath'])
