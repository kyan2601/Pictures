import shutil
from datetime import datetime

from PIL import Image

from src import constants
from src.classes.entities.MetadataFile import MetadataFile
from src.classes.workflows import ProcessNewMedia as pnm_module
from src.classes.workflows.ProcessNewMedia import ProcessNewMedia


def _write_jpeg(path):
    Image.new('RGB', (4, 4), color=(0, 255, 0)).save(str(path), 'JPEG')


class _FakeMediaEntry:
    """
    Stands in for a real MediaEntry. ProcessNewMedia's sorting/renaming/indexing
    logic only depends on .filepath/.dt/.ext/.move()/.to_dict() -- it never inspects
    pixel or EXIF data itself, so a real JPEG/HEIC/MOV isn't needed to exercise it,
    and this sidesteps EXIF-less-file ctime flakiness and the ffmpeg dependency.
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

    def __lt__(self, other):
        return self.dt < other.dt

    def __gt__(self, other):
        return self.dt > other.dt


def _fake_factory(dt_by_filepath, ext_by_filepath):
    def create(filepath):
        return _FakeMediaEntry(filepath, dt_by_filepath[filepath], ext_by_filepath[filepath])
    return create


class TestDeleteDotUnderscoreFiles:
    def test_moves_dot_underscore_files_to_backup(self, tmp_root):
        new_dir = tmp_root / 'new'
        new_dir.mkdir()
        (new_dir / '._hidden.jpg').write_bytes(b'x')
        (new_dir / 'real.jpg').write_bytes(b'x')

        ProcessNewMedia(dry_run=False)._delete_dot_underscore_files()

        assert not (new_dir / '._hidden.jpg').exists()
        assert (new_dir / 'real.jpg').exists()
        backup_dirs = list((tmp_root / 'backup').iterdir())
        assert len(backup_dirs) == 1
        assert (backup_dirs[0] / '._hidden.jpg').exists()

    def test_dry_run_leaves_files_in_place(self, tmp_root):
        new_dir = tmp_root / 'new'
        new_dir.mkdir()
        (new_dir / '._hidden.jpg').write_bytes(b'x')

        ProcessNewMedia(dry_run=True)._delete_dot_underscore_files()

        assert (new_dir / '._hidden.jpg').exists()
        assert not (tmp_root / 'backup').exists()

    def test_logs_no_op_when_none_found(self, tmp_root):
        new_dir = tmp_root / 'new'
        new_dir.mkdir()
        (new_dir / 'real.jpg').write_bytes(b'x')

        pnm = ProcessNewMedia(dry_run=False)
        pnm._delete_dot_underscore_files()

        assert "No '._' files found to process." in pnm.run_log


class TestIdentifyLivePhotoMovies:
    def test_removes_mov_paired_with_a_same_named_picture(self, tmp_root):
        new_dir = tmp_root / 'new'
        new_dir.mkdir()
        _write_jpeg(new_dir / 'IMG_001.jpg')
        (new_dir / 'IMG_001.mov').write_bytes(b'fake-mov-bytes')
        _write_jpeg(new_dir / 'IMG_002.jpg')  # no paired .mov -> nothing to remove

        ProcessNewMedia(dry_run=False)._identify_live_photo_movies()

        assert not (new_dir / 'IMG_001.mov').exists()
        assert (new_dir / 'IMG_001.jpg').exists()  # the picture itself is untouched
        assert (new_dir / 'IMG_002.jpg').exists()
        backup_dirs = list((tmp_root / 'backup').iterdir())
        assert len(backup_dirs) == 1
        assert (backup_dirs[0] / 'IMG_001.mov').exists()

    def test_dry_run_leaves_files_in_place(self, tmp_root):
        new_dir = tmp_root / 'new'
        new_dir.mkdir()
        _write_jpeg(new_dir / 'IMG_001.jpg')
        (new_dir / 'IMG_001.mov').write_bytes(b'fake-mov-bytes')

        ProcessNewMedia(dry_run=True)._identify_live_photo_movies()

        assert (new_dir / 'IMG_001.mov').exists()
        assert not (tmp_root / 'backup').exists()

    def test_standalone_mov_without_a_picture_is_left_alone(self, tmp_root):
        new_dir = tmp_root / 'new'
        new_dir.mkdir()
        (new_dir / 'clip.mov').write_bytes(b'fake-mov-bytes')

        ProcessNewMedia(dry_run=False)._identify_live_photo_movies()

        assert (new_dir / 'clip.mov').exists()


class TestSortAndRenameNewPictures:
    def test_assigns_indices_in_datetime_order_not_filename_order(self, tmp_root, monkeypatch):
        new_dir = tmp_root / 'new'
        new_dir.mkdir()
        # 'a.jpg' sorts first alphabetically but is the *later* photo -- indices must
        # follow .dt, not filename/discovery order.
        (new_dir / 'a.jpg').write_bytes(b'x')
        (new_dir / 'b.jpg').write_bytes(b'x')

        a_path, b_path = str(new_dir / 'a.jpg'), str(new_dir / 'b.jpg')
        dt_by_path = {a_path: datetime(2025, 6, 15, 14, 0), b_path: datetime(2025, 6, 15, 9, 0)}
        ext_by_path = {a_path: constants.PictureExtension.JPG, b_path: constants.PictureExtension.JPG}
        monkeypatch.setattr(pnm_module.media_class_factory, 'create_media_entry',
                             _fake_factory(dt_by_path, ext_by_path))

        pnm = ProcessNewMedia(dry_run=False)
        pnm._sort_and_rename_new_pictures()

        month_dir = tmp_root / '2025' / '06'
        # b.jpg (earlier dt) must be index 1, a.jpg (later dt) must be index 2 --
        # resolve identity by dt since both files have identical dummy content.
        by_dt = {m.dt: m.filepath for m in pnm.media}
        assert by_dt[datetime(2025, 6, 15, 9, 0)] == str(month_dir / '250615001.jpg')
        assert by_dt[datetime(2025, 6, 15, 14, 0)] == str(month_dir / '250615002.jpg')

    def test_continues_numbering_after_existing_files_for_that_date(self, tmp_root, monkeypatch):
        month_dir = tmp_root / '2025' / '06'
        month_dir.mkdir(parents=True)
        (month_dir / '250615001.jpg').write_bytes(b'existing')

        new_dir = tmp_root / 'new'
        new_dir.mkdir()
        (new_dir / 'c.jpg').write_bytes(b'new')
        c_path = str(new_dir / 'c.jpg')
        monkeypatch.setattr(
            pnm_module.media_class_factory, 'create_media_entry',
            _fake_factory({c_path: datetime(2025, 6, 15, 10, 0)}, {c_path: constants.PictureExtension.JPG}))

        ProcessNewMedia(dry_run=False)._sort_and_rename_new_pictures()

        assert (month_dir / '250615002.jpg').read_bytes() == b'new'
        assert (month_dir / '250615001.jpg').read_bytes() == b'existing'

    def test_dry_run_does_not_move_or_create_directories(self, tmp_root, monkeypatch):
        new_dir = tmp_root / 'new'
        new_dir.mkdir()
        (new_dir / 'a.jpg').write_bytes(b'x')
        a_path = str(new_dir / 'a.jpg')
        monkeypatch.setattr(
            pnm_module.media_class_factory, 'create_media_entry',
            _fake_factory({a_path: datetime(2025, 6, 15, 10, 0)}, {a_path: constants.PictureExtension.JPG}))

        pnm = ProcessNewMedia(dry_run=True)
        pnm._sort_and_rename_new_pictures()

        assert (new_dir / 'a.jpg').exists()
        assert not (tmp_root / '2025').exists()
        # self.media is still populated even in dry-run (used by later steps' dry-run logging).
        assert len(pnm.media) == 1

    def test_separate_dates_get_independent_index_sequences(self, tmp_root, monkeypatch):
        new_dir = tmp_root / 'new'
        new_dir.mkdir()
        (new_dir / 'a.jpg').write_bytes(b'x')
        (new_dir / 'b.jpg').write_bytes(b'x')
        a_path, b_path = str(new_dir / 'a.jpg'), str(new_dir / 'b.jpg')
        monkeypatch.setattr(
            pnm_module.media_class_factory, 'create_media_entry',
            _fake_factory(
                {a_path: datetime(2025, 6, 15, 10, 0), b_path: datetime(2025, 7, 1, 10, 0)},
                {a_path: constants.PictureExtension.JPG, b_path: constants.PictureExtension.JPG}))

        ProcessNewMedia(dry_run=False)._sort_and_rename_new_pictures()

        assert (tmp_root / '2025' / '06' / '250615001.jpg').exists()
        assert (tmp_root / '2025' / '07' / '250701001.jpg').exists()


class TestIndexMetadata:
    def test_writes_metadata_rows_for_the_correct_year(self, tmp_root, monkeypatch):
        new_dir = tmp_root / 'new'
        new_dir.mkdir()
        (new_dir / 'a.jpg').write_bytes(b'x')
        a_path = str(new_dir / 'a.jpg')
        monkeypatch.setattr(
            pnm_module.media_class_factory, 'create_media_entry',
            _fake_factory({a_path: datetime(2025, 6, 15, 10, 0)}, {a_path: constants.PictureExtension.JPG}))

        pnm = ProcessNewMedia(dry_run=False)
        pnm._sort_and_rename_new_pictures()
        pnm._index_metadata()

        mf = MetadataFile.get_instance(2025)
        assert str(tmp_root / '2025' / '06' / '250615001.jpg') in set(mf.df['filepath'])

    def test_dry_run_does_not_write(self, tmp_root, monkeypatch):
        new_dir = tmp_root / 'new'
        new_dir.mkdir()
        (new_dir / 'a.jpg').write_bytes(b'x')
        a_path = str(new_dir / 'a.jpg')
        monkeypatch.setattr(
            pnm_module.media_class_factory, 'create_media_entry',
            _fake_factory({a_path: datetime(2025, 6, 15, 10, 0)}, {a_path: constants.PictureExtension.JPG}))

        pnm = ProcessNewMedia(dry_run=True)
        pnm._sort_and_rename_new_pictures()
        pnm._index_metadata()

        assert not (tmp_root / '2025').exists()

    def test_no_op_when_no_media_was_sorted(self, tmp_root):
        pnm = ProcessNewMedia(dry_run=False)
        pnm._index_metadata()

        assert "No new files to index metadata for." in pnm.run_log
