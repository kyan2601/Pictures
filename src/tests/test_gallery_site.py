import json
import os
from datetime import datetime

import pandas as pd
import pytest
from PIL import Image

from src.classes.workflows.GallerySite import GallerySite


def _write_jpeg(path, color=(255, 0, 0)):
    Image.new('RGB', (40, 40), color=color).save(str(path), 'JPEG')


class TestAddPage:
    def test_generates_page_manifest_and_index(self, tmp_root):
        source_dir = tmp_root / 'source'
        source_dir.mkdir()
        _write_jpeg(source_dir / 'a.jpg')
        _write_jpeg(source_dir / 'b.jpg')

        review_root = tmp_root / 'review'
        site = GallerySite(str(review_root), site_title='Test Review')
        page_path = site.add_page(
            category='duplicate-check',
            page_id='2025-10',
            title='Duplicate check — 2025-10',
            sections=[{
                'heading': 'Group 1 — Duplicate',
                'note': 'Pick a keeper.',
                'items': [
                    {'filepath': str(source_dir / 'a.jpg'), 'label': 'Score 24.5', 'tag': 'keep'},
                    {'filepath': str(source_dir / 'b.jpg'), 'label': 'Score 18.1', 'tag': 'remove'},
                ],
            }],
        )

        assert page_path == str(review_root / 'duplicate-check' / '2025-10.html')
        assert os.path.exists(page_path)

        page_html = open(page_path, encoding='utf-8').read()
        assert 'Group 1 — Duplicate' in page_html
        assert 'Pick a keeper.' in page_html
        assert 'a.jpg' in page_html
        assert 'Score 24.5' in page_html
        assert '<span class="chip keep">KEEP</span>' in page_html
        assert '<span class="chip remove">REMOVE</span>' in page_html
        assert 'Duplicate Check' in page_html  # breadcrumb, title-cased from the slug

        manifest_path = review_root / 'duplicate-check' / 'manifest.json'
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        assert len(manifest) == 1
        assert manifest[0]['page_id'] == '2025-10'
        assert manifest[0]['item_count'] == 2

        index_html = (review_root / 'index.html').read_text(encoding='utf-8')
        assert 'Test Review' in index_html
        assert 'Duplicate Check' in index_html
        assert 'duplicate-check/2025-10.html' in index_html
        assert '2 items' in index_html

        thumbnails = list((review_root / 'thumbnails').iterdir())
        assert len(thumbnails) == 2

    def test_page_links_reference_original_file_via_file_uri(self, tmp_root):
        source_dir = tmp_root / 'source'
        source_dir.mkdir()
        _write_jpeg(source_dir / 'a.jpg')

        review_root = tmp_root / 'review'
        site = GallerySite(str(review_root))
        site.add_page('duplicate-check', 'p1', 'Page 1', [{'heading': 'Section', 'items': [
            {'filepath': str(source_dir / 'a.jpg')},
        ]}])

        page_html = (review_root / 'duplicate-check' / 'p1.html').read_text(encoding='utf-8')
        assert 'file:///' in page_html
        assert 'a.jpg' in page_html

    def test_rerunning_same_page_id_replaces_rather_than_duplicates(self, tmp_root):
        source_dir = tmp_root / 'source'
        source_dir.mkdir()
        _write_jpeg(source_dir / 'a.jpg')
        _write_jpeg(source_dir / 'b.jpg')

        review_root = tmp_root / 'review'
        site = GallerySite(str(review_root))
        site.add_page('duplicate-check', '2025-10', 'First run', [{'heading': 'S', 'items': [
            {'filepath': str(source_dir / 'a.jpg')}]}])
        site.add_page('duplicate-check', '2025-10', 'Second run', [{'heading': 'S', 'items': [
            {'filepath': str(source_dir / 'a.jpg')}, {'filepath': str(source_dir / 'b.jpg')}]}])

        manifest = json.loads((review_root / 'duplicate-check' / 'manifest.json').read_text(encoding='utf-8'))
        assert len(manifest) == 1
        assert manifest[0]['title'] == 'Second run'
        assert manifest[0]['item_count'] == 2

        index_html = (review_root / 'index.html').read_text(encoding='utf-8')
        assert 'Second run' in index_html
        assert 'First run' not in index_html

    def test_index_reflects_pages_from_separate_gallery_site_instances(self, tmp_root):
        # Each CLI invocation constructs a fresh GallerySite -- the index must be
        # rebuilt from what's on disk, not from in-memory state of a single instance.
        source_dir = tmp_root / 'source'
        source_dir.mkdir()
        _write_jpeg(source_dir / 'a.jpg')

        review_root = tmp_root / 'review'
        GallerySite(str(review_root)).add_page('duplicate-check', '2025-09', 'September', [
            {'heading': 'S', 'items': [{'filepath': str(source_dir / 'a.jpg')}]}])
        GallerySite(str(review_root)).add_page('duplicate-check', '2025-10', 'October', [
            {'heading': 'S', 'items': [{'filepath': str(source_dir / 'a.jpg')}]}])

        index_html = (review_root / 'index.html').read_text(encoding='utf-8')
        assert 'September' in index_html
        assert 'October' in index_html

    def test_multiple_categories_get_separate_sections_on_index(self, tmp_root):
        source_dir = tmp_root / 'source'
        source_dir.mkdir()
        _write_jpeg(source_dir / 'a.jpg')

        review_root = tmp_root / 'review'
        site = GallerySite(str(review_root))
        site.add_page('duplicate-check', 'p1', 'Dup page', [
            {'heading': 'S', 'items': [{'filepath': str(source_dir / 'a.jpg')}]}])
        site.add_page('assign-date', 'p2', 'Assign page', [
            {'heading': 'S', 'items': [{'filepath': str(source_dir / 'a.jpg')}]}])

        index_html = (review_root / 'index.html').read_text(encoding='utf-8')
        assert 'Duplicate Check' in index_html
        assert 'Assign Date' in index_html
        assert 'duplicate-check/p1.html' in index_html
        assert 'assign-date/p2.html' in index_html

    def test_empty_page_shows_empty_state_instead_of_crashing(self, tmp_root):
        review_root = tmp_root / 'review'
        site = GallerySite(str(review_root))
        site.add_page('duplicate-check', 'empty', 'Empty Page', [])

        page_html = (review_root / 'duplicate-check' / 'empty.html').read_text(encoding='utf-8')
        assert 'Nothing to show' in page_html

    def test_thumbnail_generation_failure_is_skipped_not_fatal(self, tmp_root, capsys):
        source_dir = tmp_root / 'source'
        source_dir.mkdir()
        broken = source_dir / 'broken.jpg'
        broken.write_bytes(b'not a real image')
        _write_jpeg(source_dir / 'good.jpg')

        review_root = tmp_root / 'review'
        site = GallerySite(str(review_root))
        site.add_page('duplicate-check', 'p1', 'Page 1', [{'heading': 'S', 'items': [
            {'filepath': str(broken)},
            {'filepath': str(source_dir / 'good.jpg')},
        ]}])

        page_html = (review_root / 'duplicate-check' / 'p1.html').read_text(encoding='utf-8')
        assert 'broken.jpg' not in page_html
        assert 'good.jpg' in page_html
        assert 'Could not generate thumbnail' in capsys.readouterr().out

    def test_reuses_existing_thumbnail_instead_of_regenerating(self, tmp_root):
        source_dir = tmp_root / 'source'
        source_dir.mkdir()
        _write_jpeg(source_dir / 'a.jpg')

        review_root = tmp_root / 'review'
        site = GallerySite(str(review_root))
        site.add_page('duplicate-check', 'p1', 'Page 1', [{'heading': 'S', 'items': [
            {'filepath': str(source_dir / 'a.jpg')}]}])
        site.add_page('duplicate-check', 'p2', 'Page 2', [{'heading': 'S', 'items': [
            {'filepath': str(source_dir / 'a.jpg')}]}])

        # Same source file referenced from two pages -> one shared thumbnail, not two.
        assert len(list((review_root / 'thumbnails').iterdir())) == 1

    def test_thumbnails_are_resized(self, tmp_root):
        source_dir = tmp_root / 'source'
        source_dir.mkdir()
        _write_jpeg(source_dir / 'a.jpg')

        review_root = tmp_root / 'review'
        GallerySite(str(review_root)).add_page('duplicate-check', 'p1', 'Page 1', [{'heading': 'S', 'items': [
            {'filepath': str(source_dir / 'a.jpg')}]}])

        thumbnails = list((review_root / 'thumbnails').iterdir())
        assert len(thumbnails) == 1
        with Image.open(thumbnails[0]) as img:
            assert max(img.size) <= 480


class TestReviews:
    def test_new_page_gets_a_reviews_csv_entry_with_empty_last_reviewed(self, tmp_root):
        source_dir = tmp_root / 'source'
        source_dir.mkdir()
        _write_jpeg(source_dir / 'a.jpg')

        review_root = tmp_root / 'review'
        GallerySite(str(review_root)).add_page('duplicate-check', 'p1', 'Page 1', [
            {'heading': 'S', 'items': [{'filepath': str(source_dir / 'a.jpg')}]}])

        reviews = pd.read_csv(review_root / 'reviews.csv', dtype=str, keep_default_na=False)
        assert len(reviews) == 1
        assert reviews.iloc[0]['last_reviewed'] == ''

        index_html = (review_root / 'index.html').read_text(encoding='utf-8')
        assert 'Not reviewed' in index_html
        assert 'REVIEWED' not in index_html

    def test_mark_reviewed_sets_timestamp_and_updates_index(self, tmp_root):
        source_dir = tmp_root / 'source'
        source_dir.mkdir()
        _write_jpeg(source_dir / 'a.jpg')

        review_root = tmp_root / 'review'
        site = GallerySite(str(review_root))
        page_path = site.add_page('duplicate-check', 'p1', 'Page 1', [
            {'heading': 'S', 'items': [{'filepath': str(source_dir / 'a.jpg')}]}])

        site.mark_reviewed(page_path, when=datetime(2026, 8, 22, 14, 30))

        reviews = pd.read_csv(review_root / 'reviews.csv', dtype=str, keep_default_na=False)
        assert reviews.iloc[0]['last_reviewed'] == '2026-08-22T14:30:00'

        index_html = (review_root / 'index.html').read_text(encoding='utf-8')
        assert 'REVIEWED · 2026-08-22 14:30' in index_html
        assert 'Not reviewed' not in index_html

    def test_rerunning_add_page_does_not_clear_an_existing_review(self, tmp_root):
        source_dir = tmp_root / 'source'
        source_dir.mkdir()
        _write_jpeg(source_dir / 'a.jpg')

        review_root = tmp_root / 'review'
        site = GallerySite(str(review_root))
        page_path = site.add_page('duplicate-check', 'p1', 'First run', [
            {'heading': 'S', 'items': [{'filepath': str(source_dir / 'a.jpg')}]}])
        site.mark_reviewed(page_path, when=datetime(2026, 8, 22, 14, 30))

        # Re-run the same check (e.g. find-duplicates run again on the same month).
        site.add_page('duplicate-check', 'p1', 'Second run', [
            {'heading': 'S', 'items': [{'filepath': str(source_dir / 'a.jpg')}]}])

        reviews = pd.read_csv(review_root / 'reviews.csv', dtype=str, keep_default_na=False)
        assert len(reviews) == 1  # not duplicated
        assert reviews.iloc[0]['last_reviewed'] == '2026-08-22T14:30:00'  # not cleared

        index_html = (review_root / 'index.html').read_text(encoding='utf-8')
        assert 'REVIEWED · 2026-08-22 14:30' in index_html

    def test_mark_reviewed_raises_for_untracked_page(self, tmp_root):
        review_root = tmp_root / 'review'
        site = GallerySite(str(review_root))
        site.add_page('duplicate-check', 'empty', 'Empty', [])

        with pytest.raises(ValueError):
            site.mark_reviewed(str(review_root / 'duplicate-check' / 'nonexistent.html'))

    def test_reviewed_pages_are_tucked_inside_a_collapsed_disclosure(self, tmp_root):
        source_dir = tmp_root / 'source'
        source_dir.mkdir()
        _write_jpeg(source_dir / 'a.jpg')

        review_root = tmp_root / 'review'
        site = GallerySite(str(review_root))
        pending_path = site.add_page('duplicate-check', 'p-pending', 'Pending page', [
            {'heading': 'S', 'items': [{'filepath': str(source_dir / 'a.jpg')}]}])
        reviewed_path = site.add_page('duplicate-check', 'p-reviewed', 'Reviewed page', [
            {'heading': 'S', 'items': [{'filepath': str(source_dir / 'a.jpg')}]}])
        site.mark_reviewed(reviewed_path)

        index_html = (review_root / 'index.html').read_text(encoding='utf-8')

        # The pending page sits in the plain, always-visible list...
        before_details = index_html.split('<details')[0]
        assert 'Pending page' in before_details

        # ...while the reviewed one is inside the <details> disclosure, collapsed by
        # default (no 'open' attribute) and labeled with the completed count.
        assert '<details class="completed-disclosure">' in index_html
        assert 'Completed (1)' in index_html
        details_block = index_html.split('<details class="completed-disclosure">')[1]
        assert 'Reviewed page' in details_block
        assert 'Pending page' not in details_block

    def test_all_reviewed_category_shows_nothing_pending_message(self, tmp_root):
        source_dir = tmp_root / 'source'
        source_dir.mkdir()
        _write_jpeg(source_dir / 'a.jpg')

        review_root = tmp_root / 'review'
        site = GallerySite(str(review_root))
        page_path = site.add_page('duplicate-check', 'p1', 'Page 1', [
            {'heading': 'S', 'items': [{'filepath': str(source_dir / 'a.jpg')}]}])
        site.mark_reviewed(page_path)

        index_html = (review_root / 'index.html').read_text(encoding='utf-8')
        assert 'Nothing pending — all reviewed.' in index_html


class TestOpenInBrowser:
    def test_opens_index_file_uri(self, tmp_root, monkeypatch):
        import src.classes.workflows.GallerySite as gallery_module

        review_root = tmp_root / 'review'
        site = GallerySite(str(review_root))
        site.add_page('duplicate-check', 'empty', 'Empty', [])

        opened = []
        monkeypatch.setattr(gallery_module.webbrowser, 'open', lambda uri: opened.append(uri))

        site.open_in_browser()

        assert len(opened) == 1
        assert opened[0].startswith('file:')
        assert opened[0].endswith('index.html')
