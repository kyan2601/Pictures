import hashlib
import html
import os
import webbrowser
from pathlib import Path

import ffmpeg
from PIL import Image
from pillow_heif import register_heif_opener

from src import constants

register_heif_opener()

THUMBNAIL_MAX_DIMENSION = 480

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
  gap: 0.85rem;
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

header.site-header .page-title {
  color: var(--text-muted);
  font-size: 0.95rem;
}

main {
  max-width: 1400px;
  margin: 0 auto;
  padding: 2rem 1.75rem 4rem;
}

section.group {
  margin-bottom: 2.75rem;
}

section.group .group-heading {
  display: flex;
  align-items: baseline;
  gap: 0.75rem;
  margin: 0 0 0.35rem;
  font-size: 1.05rem;
  font-weight: 700;
  text-wrap: balance;
}

section.group .group-count {
  font-family: 'IBM Plex Mono', ui-monospace, monospace;
  font-size: 0.8rem;
  font-weight: 400;
  color: var(--text-muted);
}

section.group .group-note {
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
  .card { transition: none; }
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
  align-items: baseline;
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

@media (prefers-reduced-motion: reduce) {
  .page-row { transition: none; }
}

.page-row:hover {
  border-color: var(--accent);
  background: var(--surface-hover);
}

.page-row .page-row-title {
  font-weight: 600;
}

.page-row .page-row-count {
  font-family: 'IBM Plex Mono', ui-monospace, monospace;
  font-size: 0.82rem;
  color: var(--text-muted);
  flex-shrink: 0;
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


def _render_page_html(site_title, title, sections):
    body_sections = '\n'.join(_render_section(section) for section in sections) \
        or '<p class="empty-state">Nothing to show on this page.</p>'
    return f"""{_render_head(title, site_title)}
<body>
<header class="site-header">
  <a class="site-title" href="../index.html">{html.escape(site_title)}</a>
  <span class="crumb-sep">/</span>
  <span class="page-title">{html.escape(title)}</span>
</header>
<main>
{body_sections}
</main>
</body>
</html>"""


def _render_index_html(site_title, page_summaries):
    if page_summaries:
        rows = '\n'.join(
            f'<a class="page-row" href="pages/{html.escape(p["page_id"])}.html">'
            f'<span class="page-row-title">{html.escape(p["title"])}</span>'
            f'<span class="page-row-count">{p["item_count"]} item{"s" if p["item_count"] != 1 else ""}</span>'
            f'</a>'
            for p in page_summaries
        )
        body = f'<div class="page-list">{rows}</div>'
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

    Not a web app: purely for viewing. Acting on what you decide (deleting a
    duplicate, running an assignment with --execute) still happens from the CLI.
    """

    def __init__(self, output_dir, site_title='Pictures Review'):
        self.output_dir = output_dir
        self.site_title = site_title
        self.thumbnails_dir = os.path.join(output_dir, 'thumbnails')
        self.pages_dir = os.path.join(output_dir, 'pages')
        self._pages = []

    def add_page(self, page_id, title, sections):
        """
        sections: list of dicts, each {'heading': str, 'note': str (optional),
        'items': list of {'filepath': str, 'label': str (optional),
        'tag': 'keep'|'remove'|'unsure'|None (optional)}}
        """
        self._pages.append((page_id, title, sections))

    def _resolve_thumbnail(self, filepath):
        thumb_name = _thumbnail_filename(filepath)
        thumb_path = os.path.join(self.thumbnails_dir, thumb_name)
        if not os.path.exists(thumb_path):
            _make_thumbnail(filepath, thumb_path)
        return thumb_name

    def write(self):
        os.makedirs(self.thumbnails_dir, exist_ok=True)
        os.makedirs(self.pages_dir, exist_ok=True)

        page_summaries = []
        for page_id, title, sections in self._pages:
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

            item_count = sum(len(s['items']) for s in rendered_sections)
            page_html = _render_page_html(self.site_title, title, rendered_sections)
            with open(os.path.join(self.pages_dir, f'{page_id}.html'), 'w', encoding='utf-8') as f:
                f.write(page_html)

            page_summaries.append({'page_id': page_id, 'title': title, 'item_count': item_count})

        index_html = _render_index_html(self.site_title, page_summaries)
        index_path = os.path.join(self.output_dir, 'index.html')
        with open(index_path, 'w', encoding='utf-8') as f:
            f.write(index_html)

        return index_path

    def open_in_browser(self):
        index_path = os.path.join(self.output_dir, 'index.html')
        webbrowser.open(_file_uri(index_path))
