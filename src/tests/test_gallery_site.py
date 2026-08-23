import os

from PIL import Image

from src.classes.workflows.GallerySite import GallerySite


def _write_jpeg(path, color=(255, 0, 0)):
    Image.new('RGB', (40, 40), color=color).save(str(path), 'JPEG')


class TestWrite:
    def test_generates_index_and_page_with_thumbnails(self, tmp_path):
        source_dir = tmp_path / 'source'
        source_dir.mkdir()
        _write_jpeg(source_dir / 'a.jpg')
        _write_jpeg(source_dir / 'b.jpg')

        output_dir = tmp_path / 'review'
        site = GallerySite(str(output_dir), site_title='Test Review')
        site.add_page(
            page_id='group-1',
            title='Group 1',
            sections=[{
                'heading': 'Duplicate',
                'note': 'Pick a keeper.',
                'items': [
                    {'filepath': str(source_dir / 'a.jpg'), 'label': 'Score 24.5', 'tag': 'keep'},
                    {'filepath': str(source_dir / 'b.jpg'), 'label': 'Score 18.1', 'tag': 'remove'},
                ],
            }],
        )

        index_path = site.write()

        assert index_path == str(output_dir / 'index.html')
        assert os.path.exists(index_path)

        page_path = output_dir / 'pages' / 'group-1.html'
        assert page_path.exists()

        index_html = (output_dir / 'index.html').read_text(encoding='utf-8')
        assert 'Test Review' in index_html
        assert 'pages/group-1.html' in index_html
        assert '2 items' in index_html

        page_html = page_path.read_text(encoding='utf-8')
        assert 'Duplicate' in page_html
        assert 'Pick a keeper.' in page_html
        assert 'a.jpg' in page_html
        assert 'Score 24.5' in page_html
        assert '<span class="chip keep">KEEP</span>' in page_html
        assert '<span class="chip remove">REMOVE</span>' in page_html

        # Thumbnails were actually generated as real image files.
        thumbnails = list((output_dir / 'thumbnails').iterdir())
        assert len(thumbnails) == 2
        for thumb in thumbnails:
            with Image.open(thumb) as img:
                assert max(img.size) <= 480

    def test_page_links_reference_original_file_via_file_uri(self, tmp_path):
        source_dir = tmp_path / 'source'
        source_dir.mkdir()
        _write_jpeg(source_dir / 'a.jpg')

        output_dir = tmp_path / 'review'
        site = GallerySite(str(output_dir))
        site.add_page('p1', 'Page 1', [{'heading': 'Section', 'items': [
            {'filepath': str(source_dir / 'a.jpg')},
        ]}])
        site.write()

        page_html = (output_dir / 'pages' / 'p1.html').read_text(encoding='utf-8')
        assert 'file:///' in page_html
        assert 'a.jpg' in page_html

    def test_multiple_pages_all_listed_on_index(self, tmp_path):
        source_dir = tmp_path / 'source'
        source_dir.mkdir()
        _write_jpeg(source_dir / 'a.jpg')

        output_dir = tmp_path / 'review'
        site = GallerySite(str(output_dir))
        site.add_page('p1', 'First Page', [{'heading': 'S', 'items': [
            {'filepath': str(source_dir / 'a.jpg')}]}])
        site.add_page('p2', 'Second Page', [{'heading': 'S', 'items': [
            {'filepath': str(source_dir / 'a.jpg')}]}])
        site.write()

        index_html = (output_dir / 'index.html').read_text(encoding='utf-8')
        assert 'First Page' in index_html
        assert 'Second Page' in index_html
        assert (output_dir / 'pages' / 'p1.html').exists()
        assert (output_dir / 'pages' / 'p2.html').exists()

    def test_empty_page_shows_empty_state_instead_of_crashing(self, tmp_path):
        output_dir = tmp_path / 'review'
        site = GallerySite(str(output_dir))
        site.add_page('empty', 'Empty Page', [])
        site.write()

        page_html = (output_dir / 'pages' / 'empty.html').read_text(encoding='utf-8')
        assert 'Nothing to show' in page_html

    def test_thumbnail_generation_failure_is_skipped_not_fatal(self, tmp_path, capsys):
        source_dir = tmp_path / 'source'
        source_dir.mkdir()
        broken = source_dir / 'broken.jpg'
        broken.write_bytes(b'not a real image')
        _write_jpeg(source_dir / 'good.jpg')

        output_dir = tmp_path / 'review'
        site = GallerySite(str(output_dir))
        site.add_page('p1', 'Page 1', [{'heading': 'S', 'items': [
            {'filepath': str(broken)},
            {'filepath': str(source_dir / 'good.jpg')},
        ]}])
        site.write()

        page_html = (output_dir / 'pages' / 'p1.html').read_text(encoding='utf-8')
        assert 'broken.jpg' not in page_html
        assert 'good.jpg' in page_html
        assert 'Could not generate thumbnail' in capsys.readouterr().out

    def test_reuses_existing_thumbnail_instead_of_regenerating(self, tmp_path):
        source_dir = tmp_path / 'source'
        source_dir.mkdir()
        _write_jpeg(source_dir / 'a.jpg')

        output_dir = tmp_path / 'review'
        site = GallerySite(str(output_dir))
        site.add_page('p1', 'Page 1', [{'heading': 'S', 'items': [
            {'filepath': str(source_dir / 'a.jpg')}]}])
        site.add_page('p2', 'Page 2', [{'heading': 'S', 'items': [
            {'filepath': str(source_dir / 'a.jpg')}]}])
        site.write()

        # Same source file referenced from two pages -> one shared thumbnail, not two.
        assert len(list((output_dir / 'thumbnails').iterdir())) == 1


class TestOpenInBrowser:
    def test_opens_index_file_uri(self, tmp_path, monkeypatch):
        import src.classes.workflows.GallerySite as gallery_module

        output_dir = tmp_path / 'review'
        site = GallerySite(str(output_dir))
        site.add_page('empty', 'Empty', [])
        site.write()

        opened = []
        monkeypatch.setattr(gallery_module.webbrowser, 'open', lambda uri: opened.append(uri))

        site.open_in_browser()

        assert len(opened) == 1
        assert opened[0].startswith('file:')
        assert opened[0].endswith('index.html')
