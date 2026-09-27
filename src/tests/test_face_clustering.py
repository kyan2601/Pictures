import numpy as np
import pandas as pd
import pytest

from src.classes.entities.MetadataFile import MetadataFile
from src.classes.workflows import FaceClustering as FC
from src.classes.workflows.FaceClustering import FaceClustering
from src.tests.conftest import seed_media


def _emb(*vals):
    v = np.array(vals, dtype=np.float32)
    return v / np.linalg.norm(v)


# Two tight identity groups in embedding space.
G1 = [_emb(1.0, 0.05, 0.0, 0.0), _emb(1.0, -0.05, 0.0, 0.0), _emb(0.95, 0.10, 0.0, 0.0)]
G2 = [_emb(0.0, 1.0, 0.05, 0.0), _emb(0.05, 1.0, -0.05, 0.0)]


@pytest.fixture
def fake_faces(monkeypatch):
    """Maps filepath -> list of embeddings, bypassing InsightFace/cv2 entirely."""
    mapping = {}
    calls = []

    def fake(filepath, app):
        calls.append(str(filepath))
        return [([0.0, 0.0, 10.0, 10.0], emb, 0.99)
                for emb in mapping.get(str(filepath), [])]

    monkeypatch.setattr(FC, '_faces_for_file', fake)
    monkeypatch.setattr(FC, '_get_app', lambda: object())
    return mapping, calls


def _seed(tmp_root, files=None):
    return seed_media(tmp_root, 2024, 5, files or [
        ('a.jpg', '2024:05:01 10:00:00'),
        ('b.jpg', '2024:05:02 10:00:00'),
        ('c.jpg', '2024:05:03 10:00:00'),
        ('d.jpg', '2024:05:04 10:00:00'),
        ('e.jpg', '2024:05:05 10:00:00'),
    ])


def _write_jpg(path):
    from PIL import Image
    Image.new('RGB', (40, 40), color=(255, 0, 0)).save(str(path), 'JPEG')


def _cid(assignments, filepath):
    return assignments[f'{filepath}\x000']


class TestScan:
    def test_groups_identities_into_clusters(self, tmp_root, fake_faces):
        mapping, _ = fake_faces
        files = _seed(tmp_root)
        mapping[files['a.jpg']] = [G1[0]]
        mapping[files['b.jpg']] = [G1[1]]
        mapping[files['c.jpg']] = [G1[2]]
        mapping[files['d.jpg']] = [G2[0]]
        mapping[files['e.jpg']] = [G2[1]]

        summary = FaceClustering().scan(years=[2024], build_review=False)

        assert summary == {'n_faces': 5, 'n_clusters': 2, 'n_named': 0, 'n_unassigned': 0}
        assignments = FC._load_clusters()
        assert _cid(assignments, files['a.jpg']) == _cid(assignments, files['b.jpg'])
        assert _cid(assignments, files['b.jpg']) == _cid(assignments, files['c.jpg'])
        assert _cid(assignments, files['d.jpg']) == _cid(assignments, files['e.jpg'])
        assert _cid(assignments, files['a.jpg']) != _cid(assignments, files['d.jpg'])

    def test_loner_faces_are_unassigned(self, tmp_root, fake_faces):
        mapping, _ = fake_faces
        files = _seed(tmp_root)
        mapping[files['a.jpg']] = [G1[0]]
        mapping[files['b.jpg']] = [G1[1]]
        mapping[files['c.jpg']] = [G2[0]]  # only appearance of this identity

        summary = FaceClustering().scan(years=[2024], build_review=False)

        assert summary['n_clusters'] == 1
        assert summary['n_unassigned'] == 1

    def test_multiple_faces_per_photo(self, tmp_root, fake_faces):
        mapping, _ = fake_faces
        files = _seed(tmp_root)
        mapping[files['a.jpg']] = [G1[0], G2[0]]
        mapping[files['b.jpg']] = [G1[1], G2[1]]

        summary = FaceClustering().scan(years=[2024], build_review=False)

        assert summary == {'n_faces': 4, 'n_clusters': 2, 'n_named': 0, 'n_unassigned': 0}
        assignments = FC._load_clusters()
        assert assignments[f"{files['a.jpg']}\x000"] != assignments[f"{files['a.jpg']}\x001"]
        assert assignments[f"{files['a.jpg']}\x000"] == assignments[f"{files['b.jpg']}\x000"]
        assert assignments[f"{files['a.jpg']}\x001"] == assignments[f"{files['b.jpg']}\x001"]

    def test_no_faces(self, tmp_root, fake_faces):
        _seed(tmp_root)
        summary = FaceClustering().scan(years=[2024], build_review=False)
        assert summary == {'n_faces': 0, 'n_clusters': 0, 'n_named': 0, 'n_unassigned': 0}

    def test_detection_is_incremental(self, tmp_root, fake_faces):
        mapping, calls = fake_faces
        files = _seed(tmp_root)
        old_key = f"{files['a.jpg']}\x000"
        FC._save_index(2024,
                       {old_key: {'embedding': G1[0], 'bbox': [0, 0, 1, 1], 'score': 0.9}},
                       {files['a.jpg']})
        mapping[files['b.jpg']] = [G1[1]]

        FaceClustering().scan(years=[2024], build_review=False)

        assert files['a.jpg'] not in calls  # already scanned: not re-detected
        assert files['b.jpg'] in calls
        assignments = FC._load_clusters()
        assert assignments[old_key] == assignments[f"{files['b.jpg']}\x000"]

    def test_missing_files_are_skipped(self, tmp_root, fake_faces):
        mapping, calls = fake_faces
        files = _seed(tmp_root)
        mapping[files['a.jpg']] = [G1[0]]
        (tmp_root / '2024' / '05' / 'b.jpg').unlink()

        summary = FaceClustering().scan(years=[2024], build_review=False)

        assert summary['n_faces'] == 1
        assert str(tmp_root / '2024' / '05' / 'b.jpg') not in calls


class TestNames:
    def _scan_two_identities(self, tmp_root, fake_faces):
        mapping, _ = fake_faces
        files = _seed(tmp_root)
        mapping[files['a.jpg']] = [G1[0]]
        mapping[files['b.jpg']] = [G1[1]]
        mapping[files['c.jpg']] = [G2[0]]
        mapping[files['d.jpg']] = [G2[1]]
        FaceClustering().scan(years=[2024], build_review=False)
        return files

    def test_name_cluster_and_carry_forward(self, tmp_root, fake_faces):
        files = self._scan_two_identities(tmp_root, fake_faces)
        mapping, _ = fake_faces
        cid_a = _cid(FC._load_clusters(), files['a.jpg'])
        FaceClustering().name_cluster(cid_a, 'Mom')
        assert FC._load_names() == {str(cid_a): 'Mom'}

        # New photo of the same person; rescan carries the name forward.
        new = seed_media(tmp_root, 2024, 5, [('f.jpg', '2024:05:06 10:00:00')])
        mapping[new['f.jpg']] = [G1[2]]
        summary = FaceClustering().scan(years=[2024], build_review=False)

        assert summary['n_named'] == 1
        names = FC._load_names()
        new_cid = _cid(FC._load_clusters(), files['a.jpg'])
        assert names.get(str(new_cid)) == 'Mom'

    def test_apply_names_dry_run(self, tmp_root, fake_faces, capsys):
        files = self._scan_two_identities(tmp_root, fake_faces)
        cid_a = _cid(FC._load_clusters(), files['a.jpg'])
        FaceClustering().name_cluster(cid_a, 'Mom')

        FaceClustering().apply_names(dry_run=True)

        out = capsys.readouterr().out
        assert 'dry run' in out.lower()
        record = MetadataFile.get_instance(2024).get_media_metadata(files['a.jpg'])
        assert pd.isna(record.get('people'))

    def test_apply_names_writes_and_is_idempotent(self, tmp_root, fake_faces):
        files = self._scan_two_identities(tmp_root, fake_faces)
        cid_a = _cid(FC._load_clusters(), files['a.jpg'])
        FaceClustering().name_cluster(cid_a, 'Mom')

        FaceClustering().apply_names(dry_run=False)
        record = MetadataFile.get_instance(2024).get_media_metadata(files['a.jpg'])
        assert record['people'] == 'Mom'

        FaceClustering().apply_names(dry_run=False)
        record = MetadataFile.get_instance(2024).get_media_metadata(files['a.jpg'])
        assert record['people'] == 'Mom'  # not duplicated

    def test_apply_names_merges_with_existing_people(self, tmp_root, fake_faces):
        files = self._scan_two_identities(tmp_root, fake_faces)
        cid_a = _cid(FC._load_clusters(), files['a.jpg'])
        FaceClustering().name_cluster(cid_a, 'Mom')

        mf = MetadataFile.get_instance(2024)
        record = mf.get_media_metadata(files['a.jpg'])
        record['people'] = 'Dad'
        mf.add_media_metadata(record, update=True, write=False)
        mf.write()

        FaceClustering().apply_names(dry_run=False)
        record = mf.get_media_metadata(files['a.jpg'])
        assert record['people'] == 'Dad;Mom'

    def test_apply_names_without_names_is_noop(self, tmp_root, fake_faces, capsys):
        self._scan_two_identities(tmp_root, fake_faces)
        FaceClustering().apply_names(dry_run=False)
        assert 'No named clusters' in capsys.readouterr().out


class TestStatusAndReview:
    def test_status(self, tmp_root, fake_faces, capsys):
        mapping, _ = fake_faces
        files = _seed(tmp_root)
        mapping[files['a.jpg']] = [G1[0]]
        mapping[files['b.jpg']] = [G1[1]]
        FaceClustering().scan(years=[2024], build_review=False)

        FaceClustering().status()
        out = capsys.readouterr().out
        assert '2024' in out and 'cluster' in out

    def test_build_review_page(self, tmp_root, fake_faces):
        mapping, _ = fake_faces
        files = _seed(tmp_root)
        for fp in files.values():
            _write_jpg(fp)
        mapping[files['a.jpg']] = [G1[0]]
        mapping[files['b.jpg']] = [G1[1]]
        mapping[files['c.jpg']] = [G2[0]]

        summary = FaceClustering().scan(years=[2024], build_review=True)

        page = tmp_root / 'review' / 'face-clusters' / 'clusters.html'
        assert page.exists()
        html = page.read_text()
        assert 'Face clusters' in html
        assert 'faces name --cluster' in html
