import hashlib
import html
import json
import os
import webbrowser
from datetime import datetime
from pathlib import Path

import ffmpeg
import pandas as pd
from PIL import Image
from pillow_heif import register_heif_opener

from src import constants, helper

register_heif_opener()

THUMBNAIL_MAX_DIMENSION = 480
MANIFEST_FILENAME = 'manifest.json'
REVIEWS_FILENAME = 'reviews.csv'
REVIEWS_COLS = ['filepath', 'last_reviewed']

_TAG_LABELS = {'keep': 'KEEP', 'remove': 'REMOVE', 'unsure': 'UNSURE'}


def _thumbnail_filename(filepath):
    digest = hashlib.sha1(filepath.encode('utf-8')).hexdigest()[:16]
    return f'{digest}.jpg'


def _make_picture_thumbnail(filepath, thumbnail_path):
    with Image.open(filepath) as img:
        img = img.convert('RGB')
        img.thumbnail((THUMBNAIL_MAX_DIMENSION, THUMBNAIL_MAX_DIMENSION))
        img.save(thumbnail_path, 'JPEG', quality=82)


def _make_video_thumbnail(filepath, thumbnail_path):
    (
        ffmpeg
        .input(filepath, ss=1)
        .output(thumbnail_path, vframes=1, **{'vf': f'scale={THUMBNAIL_MAX_DIMENSION}:-1'})
        .overwrite_output()
        .run(capture_stdout=True, capture_stderr=True)
    )


def _make_thumbnail(filepath, thumbnail_path):
    ext = filepath.rsplit('.', 1)[1].lower()
    if ext in constants.PICTURE_EXTENSIONS:
        _make_picture_thumbnail(filepath, thumbnail_path)
    elif ext in constants.VIDEO_EXTENSIONS:
        _make_video_thumbnail(filepath, thumbnail_path)
    else:
        raise ValueError(f"Unsupported extension for thumbnail: {filepath}")


def _file_uri(filepath):
    return Path(filepath).absolute().as_uri()


def _category_label(category):
    return category.replace('-', ' ').replace('_', ' ').title()


_PAGE_CSS = """
:root {
  --bg: #17151a;
  --surface: #201d24;
  --surface-hover: #29252d;
  --border: #322e38;
  --text: #ede9e4;
  --text-muted: #9891a0;
  --accent: #4c7fd6;
  --keep: #5fa575;
  --remove: #c9605a;
  --unsure: #d6a34c;
}

* { box-sizing: border-box; }

html, body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
}

body {
  font-family: 'Manrope', -apple-system, 'Segoe UI', sans-serif;
  font-size: 15px;
  line-height: 1.5;
}

a { color: var(--accent); }
a:focus-visible, button:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

header.site-header {
  position: sticky;
  top: 0;
  z-index: 10;
  display: flex;
  align-items: baseline;
  gap: 0.6rem;
  padding: 0.9rem 1.75rem;
  background: rgba(23, 21, 26, 0.94);
  backdrop-filter: blur(6px);
  border-bottom: 1px solid var(--border);
}

header.site-header .site-title {
  font-family: 'Fraunces', Georgia, serif;
  font-weight: 600;
  font-size: 1.2rem;
  letter-spacing: 0.01em;
  color: var(--text);
  text-decoration: none;
}

header.site-header .crumb-sep {
  color: var(--text-muted);
}

header.site-header .crumb {
  color: var(--text-muted);
  font-size: 0.95rem;
  text-decoration: none;
}

header.site-header .crumb.current {
  color: var(--text);
}

main {
  max-width: 1400px;
  margin: 0 auto;
  padding: 2rem 1.75rem 4rem;
}

section.group, section.category {
  margin-bottom: 2.75rem;
}

.group-heading, .category-heading {
  display: flex;
  align-items: baseline;
  gap: 0.75rem;
  margin: 0 0 0.35rem;
  font-size: 1.05rem;
  font-weight: 700;
  text-wrap: balance;
}

.group-count, .category-count {
  font-family: 'IBM Plex Mono', ui-monospace, monospace;
  font-size: 0.8rem;
  font-weight: 400;
  color: var(--text-muted);
}

.group-note {
  margin: 0 0 1.1rem;
  color: var(--text-muted);
  font-size: 0.88rem;
  max-width: 65ch;
}

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
  gap: 1rem;
}

.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 6px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  transition: transform 0.12s ease, border-color 0.12s ease;
}

@media (prefers-reduced-motion: reduce) {
  .card, .page-row { transition: none; }
}

.card:hover {
  border-color: var(--accent);
  transform: translateY(-2px);
}

.card .thumb-link {
  display: block;
  aspect-ratio: 1 / 1;
  background: #0f0e11;
}

.card .thumb-link img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.card .meta {
  padding: 0.55rem 0.65rem 0.7rem;
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}

.card .filename {
  font-family: 'IBM Plex Mono', ui-monospace, monospace;
  font-size: 0.72rem;
  color: var(--text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.card .label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}

.card .label {
  font-family: 'IBM Plex Mono', ui-monospace, monospace;
  font-size: 0.75rem;
  color: var(--text);
}

.chip {
  font-family: 'IBM Plex Mono', ui-monospace, monospace;
  font-size: 0.68rem;
  font-weight: 600;
  letter-spacing: 0.04em;
  padding: 0.15rem 0.45rem;
  border-radius: 3px;
  white-space: nowrap;
}

.chip.keep { color: var(--keep); background: color-mix(in srgb, var(--keep) 16%, transparent); }
.chip.remove { color: var(--remove); background: color-mix(in srgb, var(--remove) 16%, transparent); }
.chip.unsure { color: var(--unsure); background: color-mix(in srgb, var(--unsure) 16%, transparent); }

/* index page */
.page-list {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
  max-width: 720px;
}

.page-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.9rem 1.1rem;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 6px;
  text-decoration: none;
  color: var(--text);
  transition: border-color 0.12s ease, background 0.12s ease;
}

.page-row:hover {
  border-color: var(--accent);
  background: var(--surface-hover);
}

.page-row-main {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
}

.page-row .page-row-title {
  font-weight: 600;
}

.page-row .page-row-meta {
  font-family: 'IBM Plex Mono', ui-monospace, monospace;
  font-size: 0.78rem;
  color: var(--text-muted);
}

.review-pending {
  font-family: 'IBM Plex Mono', ui-monospace, monospace;
  font-size: 0.7rem;
  color: var(--text-muted);
  white-space: nowrap;
  flex-shrink: 0;
}

.page-row .chip {
  flex-shrink: 0;
}

.completed-disclosure {
  margin-top: 0.9rem;
}

.completed-disclosure summary {
  cursor: pointer;
  color: var(--text-muted);
  font-size: 0.85rem;
  font-weight: 600;
  padding: 0.4rem 0.1rem;
  list-style: none;
}

.completed-disclosure summary::-webkit-details-marker {
  display: none;
}

.completed-disclosure summary::before {
  content: '▸';
  display: inline-block;
  margin-right: 0.4rem;
  transition: transform 0.12s ease;
}

.completed-disclosure[open] summary::before {
  transform: rotate(90deg);
}

@media (prefers-reduced-motion: reduce) {
  .completed-disclosure summary::before { transition: none; }
}

.completed-disclosure summary:hover {
  color: var(--text);
}

.completed-disclosure .page-list {
  margin-top: 0.6rem;
}

.empty-state {
  color: var(--text-muted);
  font-size: 0.95rem;
}
"""

_FONT_LINK = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?'
    'family=Fraunces:wght@600&family=Manrope:wght@400;500;700&family=IBM+Plex+Mono:wght@400;600'
    '&display=swap" rel="stylesheet">'
)


def _render_head(page_title, site_title):
    full_title = f'{html.escape(page_title)} — {html.escape(site_title)}' if page_title else html.escape(site_title)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{full_title}</title>
{_FONT_LINK}
<style>{_PAGE_CSS}</style>
</head>"""


def _render_chip(tag):
    if not tag or tag not in _TAG_LABELS:
        return ''
    return f'<span class="chip {html.escape(tag)}">{_TAG_LABELS[tag]}</span>'


def _render_card(item):
    filename = html.escape(item['filename'])
    label = html.escape(item.get('label', ''))
    chip = _render_chip(item.get('tag'))
    label_row = f'<div class="label-row"><span class="label">{label}</span>{chip}</div>' \
        if (label or chip) else ''
    return f"""<a class="card" href="{item['original_uri']}" target="_blank" rel="noopener">
  <span class="thumb-link"><img src="{item['thumb_src']}" alt="{filename}" loading="lazy"></span>
  <span class="meta">
    <span class="filename">{filename}</span>
    {label_row}
  </span>
</a>"""


def _render_section(section):
    heading = html.escape(section['heading'])
    count = len(section['items'])
    note = f'<p class="group-note">{html.escape(section["note"])}</p>' if section.get('note') else ''
    cards = '\n'.join(_render_card(item) for item in section['items'])
    return f"""<section class="group">
  <h2 class="group-heading">{heading} <span class="group-count">{count} item{'s' if count != 1 else ''}</span></h2>
  {note}
  <div class="grid">
    {cards}
  </div>
</section>"""


def _render_page_html(site_title, category, title, sections):
    body_sections = '\n'.join(_render_section(section) for section in sections) \
        or '<p class="empty-state">Nothing to show on this page.</p>'
    category_label = html.escape(_category_label(category))
    return f"""{_render_head(title, site_title)}
<body>
<header class="site-header">
  <a class="site-title crumb" href="../index.html">{html.escape(site_title)}</a>
  <span class="crumb-sep">/</span>
  <span class="crumb">{category_label}</span>
  <span class="crumb-sep">/</span>
  <span class="crumb current">{html.escape(title)}</span>
</header>
<main>
{body_sections}
</main>
</body>
</html>"""


def _format_timestamp(iso_timestamp):
    try:
        return datetime.fromisoformat(iso_timestamp).strftime('%Y-%m-%d %H:%M')
    except ValueError:
        return iso_timestamp


def _render_review_chip(last_reviewed):
    if last_reviewed:
        return f'<span class="chip keep">REVIEWED · {html.escape(_format_timestamp(last_reviewed))}</span>'
    return '<span class="review-pending">Not reviewed</span>'


def _render_page_row(category, p):
    return f"""<a class="page-row" href="{html.escape(category)}/{html.escape(p['page_id'])}.html">
  <span class="page-row-main">
    <span class="page-row-title">{html.escape(p['title'])}</span>
    <span class="page-row-meta">{p['item_count']} item{'s' if p['item_count'] != 1 else ''}
      · updated {_format_timestamp(p['updated_at'])}</span>
  </span>
  {_render_review_chip(p.get('last_reviewed', ''))}
</a>"""


def _render_category_section(category, pages):
    label = html.escape(_category_label(category))
    pending = [p for p in pages if not p.get('last_reviewed')]
    reviewed = [p for p in pages if p.get('last_reviewed')]

    if pending:
        pending_block = f'<div class="page-list">{"".join(_render_page_row(category, p) for p in pending)}</div>'
    else:
        pending_block = '<p class="empty-state">Nothing pending — all reviewed.</p>'

    reviewed_block = ''
    if reviewed:
        reviewed_rows = ''.join(_render_page_row(category, p) for p in reviewed)
        reviewed_block = f"""<details class="completed-disclosure">
  <summary>Completed ({len(reviewed)})</summary>
  <div class="page-list">
    {reviewed_rows}
  </div>
</details>"""

    return f"""<section class="category">
  <h2 class="category-heading">{label} <span class="category-count">{len(pages)} page{'s' if len(pages) != 1 else ''}</span></h2>
  {pending_block}
  {reviewed_block}
</section>"""


def _render_index_html(site_title, categories):
    if categories:
        body = '\n'.join(_render_category_section(c['category'], c['pages']) for c in categories)
    else:
        body = '<p class="empty-state">No review pages yet.</p>'

    return f"""{_render_head('', site_title)}
<body>
<header class="site-header">
  <span class="site-title">{html.escape(site_title)}</span>
</header>
<main>
{body}
</main>
</body>
</html>"""


class GallerySite:
    """
    Generates a small local, static, multi-page site for visually reviewing batches
    of photos/videos -- a "contact sheet" for decisions that are hard to make from a
    printed filepath list alone (which duplicate to keep, whether a batch's order
    looks right, what's actually in an import folder).

    Persists across separate process invocations: review_root/{category}/manifest.json
    tracks every page ever added to that category, so review_root/index.html is
    rebuilt from what's actually on disk each time, not just from the current run.

    Not a web app: purely for viewing. Acting on what you decide (deleting a
    duplicate, running an assignment with --execute) still happens from the CLI.
    """

    def __init__(self, review_root, site_title='Pictures Review'):
        self.review_root = review_root
        self.site_title = site_title
        self.thumbnails_dir = os.path.join(review_root, 'thumbnails')

    def _manifest_path(self, category):
        return os.path.join(self.review_root, category, MANIFEST_FILENAME)

    def _load_manifest(self, category):
        manifest_path = self._manifest_path(category)
        if not os.path.exists(manifest_path):
            return []
        with open(manifest_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _reviews_path(self):
        return os.path.join(self.review_root, REVIEWS_FILENAME)

    def _load_reviews(self):
        reviews_path = self._reviews_path()
        if not os.path.exists(reviews_path):
            return pd.DataFrame([], columns=REVIEWS_COLS)
        return pd.read_csv(reviews_path, dtype=str, keep_default_na=False)

    def get_review_stats(self):
        """Returns (total_pages, pending_pages) from reviews.csv."""
        df = self._load_reviews()
        total = len(df)
        pending = int((df['last_reviewed'] == '').sum()) if total else 0
        return total, pending

    def _register_review_entry(self, page_path):
        """Adds page_path to reviews.csv with an empty last_reviewed, unless it's
        already tracked (in which case its existing review status is left alone)."""
        serialized = helper.serialize_filepath(page_path)
        df = self._load_reviews()
        if serialized in set(df['filepath']):
            return
        new_row = pd.DataFrame([{'filepath': serialized, 'last_reviewed': ''}], columns=REVIEWS_COLS)
        df = pd.concat([df, new_row], ignore_index=True)
        df.to_csv(self._reviews_path(), index=False)

    def mark_reviewed(self, page_path, when=None):
        """
        Marks the review page at page_path as reviewed and rebuilds index.html so
        the flag shows up immediately. Raises if page_path was never added via
        add_page() (no reviews.csv entry to update).
        """
        when = when or datetime.now()
        serialized = helper.serialize_filepath(page_path)
        df = self._load_reviews()
        if serialized not in set(df['filepath']):
            raise ValueError(f"No reviews.csv entry found for {page_path}.")
        df.loc[df['filepath'] == serialized, 'last_reviewed'] = when.isoformat(timespec='seconds')
        df.to_csv(self._reviews_path(), index=False)
        self._write_index()

    def _resolve_thumbnail(self, filepath):
        thumb_name = _thumbnail_filename(filepath)
        thumb_path = os.path.join(self.thumbnails_dir, thumb_name)
        if not os.path.exists(thumb_path):
            _make_thumbnail(filepath, thumb_path)
        return thumb_name

    def _render_sections(self, sections):
        rendered_sections = []
        for section in sections:
            rendered_items = []
            for item in section['items']:
                filepath = item['filepath']
                try:
                    thumb_name = self._resolve_thumbnail(filepath)
                except Exception as e:
                    print(f"!!! WARNING: Could not generate thumbnail for {filepath}: {e}")
                    continue
                rendered_items.append({
                    'thumb_src': f'../thumbnails/{thumb_name}',
                    'original_uri': _file_uri(filepath),
                    'filename': os.path.basename(filepath),
                    'label': item.get('label', ''),
                    'tag': item.get('tag'),
                })
            rendered_sections.append({
                'heading': section['heading'],
                'note': section.get('note', ''),
                'items': rendered_items,
            })
        return rendered_sections

    def add_page(self, category, page_id, title, sections):
        """
        Writes review_root/{category}/{page_id}.html (generating thumbnails as
        needed), updates that category's manifest, and rebuilds review_root/index.html
        from every category's current manifest. Re-running with the same page_id
        replaces that page's manifest entry rather than duplicating it.

        Returns the path to the page that was written.
        """
        category_dir = os.path.join(self.review_root, category)
        os.makedirs(category_dir, exist_ok=True)
        os.makedirs(self.thumbnails_dir, exist_ok=True)

        rendered_sections = self._render_sections(sections)
        item_count = sum(len(s['items']) for s in rendered_sections)

        page_html = _render_page_html(self.site_title, category, title, rendered_sections)
        page_path = os.path.join(category_dir, f'{page_id}.html')
        with open(page_path, 'w', encoding='utf-8') as f:
            f.write(page_html)

        self._register_review_entry(page_path)

        pages = [p for p in self._load_manifest(category) if p['page_id'] != page_id]
        pages.append({
            'page_id': page_id,
            'title': title,
            'item_count': item_count,
            'updated_at': datetime.now().isoformat(timespec='seconds'),
        })
        pages.sort(key=lambda p: p['updated_at'], reverse=True)
        with open(self._manifest_path(category), 'w', encoding='utf-8') as f:
            json.dump(pages, f, indent=2)

        self._write_index()

        return page_path

    def _write_index(self):
        reviews_df = self._load_reviews()
        reviews_lookup = dict(zip(reviews_df['filepath'], reviews_df['last_reviewed']))

        categories = []
        if os.path.isdir(self.review_root):
            for entry in sorted(os.listdir(self.review_root)):
                category_dir = os.path.join(self.review_root, entry)
                if not os.path.isdir(category_dir):
                    continue
                pages = self._load_manifest(entry)
                if not pages:
                    continue
                for page in pages:
                    page_path = os.path.join(category_dir, f"{page['page_id']}.html")
                    page['last_reviewed'] = reviews_lookup.get(helper.serialize_filepath(page_path), '')
                categories.append({'category': entry, 'pages': pages})

        index_html = _render_index_html(self.site_title, categories)
        with open(os.path.join(self.review_root, 'index.html'), 'w', encoding='utf-8') as f:
            f.write(index_html)

    def open_in_browser(self):
        index_path = os.path.join(self.review_root, 'index.html')
        webbrowser.open(_file_uri(index_path))
