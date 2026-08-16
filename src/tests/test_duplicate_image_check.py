import os
from types import SimpleNamespace

from src.classes.workflows.DuplicateImageCheck import DuplicateImageCheck


def _make_check(tmp_root):
    # Bypasses __init__'s directory scan / metadata loading; tests drive
    # self.picture_entries directly since it's the shape all the grouping/
    # scoring logic actually operates on.
    return DuplicateImageCheck(str(tmp_root))


def _entry(phash, dhash, width=100, height=100):
    return SimpleNamespace(phash=phash, dhash=dhash, width=width, height=height)


class TestHashDistance:
    def test_identical_hashes_have_zero_distance(self):
        assert DuplicateImageCheck._hash_distance('ff00', 'ff00') == 0

    def test_counts_differing_bits(self):
        # 0xf0 = 1111 0000, 0x0f = 0000 1111 -> all 8 bits differ
        assert DuplicateImageCheck._hash_distance('f0', '0f') == 8


class TestGroupByPhash:
    def test_groups_images_within_threshold(self, tmp_root):
        check = _make_check(tmp_root)
        check.picture_entries = {
            'a.jpg': _entry(phash='0000000000000000', dhash='0'),
            'b.jpg': _entry(phash='0000000000000001', dhash='0'),  # 1 bit off a -> grouped
            'c.jpg': _entry(phash='ffffffffffffffff', dhash='0'),  # far from both -> singleton
        }

        groups = check._group_by_phash()

        assert len(groups) == 1
        assert set(groups[0]) == {'a.jpg', 'b.jpg'}

    def test_no_groups_when_all_dissimilar(self, tmp_root):
        check = _make_check(tmp_root)
        check.picture_entries = {
            'a.jpg': _entry(phash='0000000000000000', dhash='0'),
            'b.jpg': _entry(phash='ffffffffffffffff', dhash='0'),
        }

        assert check._group_by_phash() == []


class TestProcessGroup:
    def test_splits_duplicates_from_similar(self, tmp_root):
        check = _make_check(tmp_root)
        check.picture_entries = {
            'dup1.jpg': _entry(phash='0', dhash='0000000000000000'),
            'dup2.jpg': _entry(phash='0', dhash='0000000000000001'),  # 1 bit off dup1 -> duplicate
            'similar.jpg': _entry(phash='0', dhash='ffffffffffffffff'),  # far from both -> similar-only
        }

        categorized = check._process_group(['dup1.jpg', 'dup2.jpg', 'similar.jpg'])
        tags = {tag for tag, _ in categorized}

        assert DuplicateImageCheck.SimilarityTiers.DUPLICATE in tags
        # A lone leftover image has nothing to be "similar" to, so it's dropped, not tagged.
        assert DuplicateImageCheck.SimilarityTiers.SIMILAR not in tags

        duplicate_group = next(paths for tag, paths in categorized
                                if tag == DuplicateImageCheck.SimilarityTiers.DUPLICATE)
        assert set(duplicate_group) == {'dup1.jpg', 'dup2.jpg'}


class TestComputeQualityScore:
    def test_heic_gets_lower_filesize_weight_than_default(self, tmp_root):
        # Regression test for the bug where '.heic' (with a dot) was compared against
        # decompose_filepath()['ext'], which never has a leading dot -- HEIC files
        # silently always fell through to WEIGHT_FILESIZE_DEFAULT.
        check = _make_check(tmp_root)

        heic_path = str(tmp_root / 'photo.heic')
        jpg_path = str(tmp_root / 'photo.jpg')
        # Small dimensions + a comparatively large payload make the bytes-per-pixel term
        # (the one the filesize_weight scales) dominate the score, so the weight
        # difference survives round(..., 2) instead of vanishing into the megapixel term.
        payload = b'\x00' * 100_000
        (tmp_root / 'photo.heic').write_bytes(payload)
        (tmp_root / 'photo.jpg').write_bytes(payload)

        # Pre-populate width/height so _compute_quality_score skips opening the file as
        # an image (the payload above isn't a real image).
        check.picture_entries = {
            heic_path: _entry(phash='0', dhash='0', width=100, height=100),
            jpg_path: _entry(phash='0', dhash='0', width=100, height=100),
        }

        heic_score = check._compute_quality_score(heic_path)
        jpg_score = check._compute_quality_score(jpg_path)

        # Same megapixels and same bytes-per-pixel; only the filesize weight differs,
        # so the HEIC file (lower weight) must score lower than the JPG.
        assert heic_score < jpg_score


class TestHandleGroups:
    def test_removes_lower_scoring_duplicate_to_backup(self, tmp_root):
        # This is the step that actually decides what gets deleted -- everything
        # upstream (grouping, scoring) just feeds into this.
        check = _make_check(tmp_root)
        a_path, b_path = str(tmp_root / 'a.jpg'), str(tmp_root / 'b.jpg')
        (tmp_root / 'a.jpg').write_bytes(b'\x00' * 100_000)  # bigger -> higher score -> KEEP
        (tmp_root / 'b.jpg').write_bytes(b'\x00' * 1_000)    # smaller -> lower score -> REMOVE
        check.picture_entries = {
            a_path: _entry(phash='0', dhash='0000000000000000', width=100, height=100),
            b_path: _entry(phash='0', dhash='0000000000000001', width=100, height=100),
        }

        check._handle_groups([[a_path, b_path]], dry_run=False)

        assert os.path.exists(a_path)
        assert not os.path.exists(b_path)
        backup_dirs = list((tmp_root / 'backup').iterdir())
        assert len(backup_dirs) == 1
        assert (backup_dirs[0] / 'b.jpg').exists()

    def test_dry_run_removes_nothing(self, tmp_root):
        check = _make_check(tmp_root)
        a_path, b_path = str(tmp_root / 'a.jpg'), str(tmp_root / 'b.jpg')
        (tmp_root / 'a.jpg').write_bytes(b'\x00' * 100_000)
        (tmp_root / 'b.jpg').write_bytes(b'\x00' * 1_000)
        check.picture_entries = {
            a_path: _entry(phash='0', dhash='0000000000000000', width=100, height=100),
            b_path: _entry(phash='0', dhash='0000000000000001', width=100, height=100),
        }

        check._handle_groups([[a_path, b_path]], dry_run=True)

        assert os.path.exists(a_path)
        assert os.path.exists(b_path)
        assert not (tmp_root / 'backup').exists()

    def test_tied_scores_are_unsure_and_nothing_is_removed(self, tmp_root):
        check = _make_check(tmp_root)
        a_path, b_path = str(tmp_root / 'a.jpg'), str(tmp_root / 'b.jpg')
        (tmp_root / 'a.jpg').write_bytes(b'\x00' * 1_000)
        (tmp_root / 'b.jpg').write_bytes(b'\x00' * 1_000)  # identical size -> identical score
        check.picture_entries = {
            a_path: _entry(phash='0', dhash='0000000000000000', width=100, height=100),
            b_path: _entry(phash='0', dhash='0000000000000001', width=100, height=100),
        }

        check._handle_groups([[a_path, b_path]], dry_run=False)

        assert os.path.exists(a_path)
        assert os.path.exists(b_path)

    def test_similar_tier_is_never_removed(self, tmp_root):
        # SIMILAR is a manual-review-only bucket; _handle_groups has no removal
        # branch for it at all.
        check = _make_check(tmp_root)
        a_path, b_path = str(tmp_root / 'a.jpg'), str(tmp_root / 'b.jpg')
        (tmp_root / 'a.jpg').write_bytes(b'x')
        (tmp_root / 'b.jpg').write_bytes(b'x')
        check.picture_entries = {
            # Distinct dhashes far enough apart that they never cluster into a
            # DUPLICATE sub-group, so both fall into the SIMILAR leftover bucket.
            a_path: _entry(phash='0', dhash='0000000000000000', width=100, height=100),
            b_path: _entry(phash='0', dhash='ffffffffffffffff', width=100, height=100),
        }

        check._handle_groups([[a_path, b_path]], dry_run=False)

        assert os.path.exists(a_path)
        assert os.path.exists(b_path)
        # A backup dir is created eagerly whenever any dHash groups exist at all
        # (even SIMILAR-only ones), but nothing is ever moved into it.
        backup_dirs = list((tmp_root / 'backup').iterdir()) if (tmp_root / 'backup').exists() else []
        assert all(not any(d.iterdir()) for d in backup_dirs)

    def test_no_groups_is_a_no_op(self, tmp_root):
        check = _make_check(tmp_root)
        check.picture_entries = {}

        check._handle_groups([], dry_run=False)

        assert not (tmp_root / 'backup').exists()
