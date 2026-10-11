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

/* compare pages (duplicate review) */
body.compare main {
  max-width: 1600px;
}

.compare .grid {
  grid-template-columns: repeat(auto-fill, minmax(330px, 1fr));
  gap: 1.25rem;
}

.compare .card .thumb-link {
  aspect-ratio: 4 / 3;
}

.compare .card .thumb-link img {
  object-fit: contain;
}

.card .details {
  display: flex;
  flex-wrap: wrap;
  gap: 0.2rem 0.85rem;
  font-family: 'IBM Plex Mono', ui-monospace, monospace;
  font-size: 0.72rem;
  color: var(--text-muted);
}

.card .suggestion {
  font-family: 'IBM Plex Mono', ui-monospace, monospace;
  font-size: 0.7rem;
  color: var(--text-muted);
}

.compare .card {
  cursor: pointer;
}

.compare .card.selected {
  outline: 2px solid var(--accent);
  outline-offset: -2px;
}

.compare .card[data-decision="keep"] { box-shadow: inset 0 0 0 2px var(--keep); }
.compare .card[data-decision="remove"] { box-shadow: inset 0 0 0 2px var(--remove); }
.compare .card[data-decision="unsure"] { box-shadow: inset 0 0 0 2px var(--unsure); }

.decision-row {
  display: flex;
  gap: 0.4rem;
  padding: 0 0.65rem 0.7rem;
  margin-top: auto;
}

.decision-btn {
  flex: 1;
  font: inherit;
  font-size: 0.75rem;
  font-weight: 700;
  letter-spacing: 0.03em;
  padding: 0.35rem 0;
  border-radius: 4px;
  border: 1px solid var(--border);
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
}

.decision-btn:hover { border-color: var(--accent); color: var(--text); }
.decision-btn.active.keep { background: var(--keep); border-color: var(--keep); color: #101408; }
.decision-btn.active.remove { background: var(--remove); border-color: var(--remove); color: #140f10; }
.decision-btn.active.unsure { background: var(--unsure); border-color: var(--unsure); color: #141109; }

.compare-toolbar {
  position: sticky;
  top: 61px;
  z-index: 9;
  display: flex;
  align-items: center;
  gap: 1rem;
  flex-wrap: wrap;
  padding: 0.6rem 1.75rem;
  background: rgba(23, 21, 26, 0.94);
  backdrop-filter: blur(6px);
  border-bottom: 1px solid var(--border);
  font-family: 'IBM Plex Mono', ui-monospace, monospace;
  font-size: 0.8rem;
}

.compare-toolbar .toolbar-actions {
  display: flex;
  gap: 0.4rem;
}

.compare-toolbar button {
  font: inherit;
  font-size: 0.78rem;
  padding: 0.3rem 0.7rem;
  border-radius: 4px;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text);
  cursor: pointer;
}

.compare-toolbar button:hover { border-color: var(--accent); }

.compare-toolbar #copy-status { color: var(--keep); }

.compare-help {
  max-width: 1600px;
  margin: 0 auto;
  padding: 0.8rem 1.75rem 0;
  color: var(--text-muted);
  font-size: 0.82rem;
}

.compare-group.current .group-heading { color: var(--accent); }
"""

_FONT_LINK = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?'
    'family=Fraunces:wght@600&family=Manrope:wght@400;500;700&family=IBM+Plex+Mono:wght@400;600'
    '&display=swap" rel="stylesheet">'
)

# Interactive layer for compare pages: per-photo keep/remove/unsure decisions
# (kept in this browser's localStorage only — the page stays a static file),
# group navigation/progress, keyboard shortcuts, and a copy-out of the
# decisions as structured text lines the user can hand back for applying.
_COMPARE_SCRIPT = """
<script>
(function () {
  const PAGE_ID = __PAGE_ID_JSON__;
  const storeKey = 'duplicate-decisions:' + PAGE_ID;
  const groups = Array.from(document.querySelectorAll('section.compare-group'));
  const cards = Array.from(document.querySelectorAll('.compare .card[data-filename]'));
  const progressEl = document.getElementById('compare-progress');
  const copyStatusEl = document.getElementById('copy-status');
  let stored = {};
  try { stored = JSON.parse(localStorage.getItem(storeKey)) || {}; } catch (e) {}
  let selectedCard = null;
  let currentGroup = 0;

  function decisionOf(card) { return card.getAttribute('data-decision') || ''; }

  function applyDecision(card, decision) {
    if (decision) { card.setAttribute('data-decision', decision); }
    else { card.removeAttribute('data-decision'); }
    card.querySelectorAll('.decision-btn').forEach(function (btn) {
      btn.classList.toggle('active', btn.getAttribute('data-decision') === decision);
    });
  }

  function persist() {
    const out = {};
    cards.forEach(function (card) {
      const d = decisionOf(card);
      if (d) { out[card.getAttribute('data-filename')] = d; }
    });
    try { localStorage.setItem(storeKey, JSON.stringify(out)); } catch (e) {}
  }

  function setDecision(card, decision) {
    applyDecision(card, decisionOf(card) === decision ? '' : decision);
    persist();
    updateProgress();
  }

  function updateProgress() {
    let decided = 0;
    groups.forEach(function (group) {
      const groupCards = group.querySelectorAll('.card[data-filename]');
      if (groupCards.length && Array.from(groupCards).every(function (c) { return decisionOf(c); })) {
        decided += 1;
      }
      group.classList.toggle('current', groups.indexOf(group) === currentGroup);
    });
    progressEl.textContent = 'Group ' + (currentGroup + 1) + ' of ' + groups.length +
      ' \\u00b7 ' + decided + '/' + groups.length + ' groups fully decided';
  }

  function selectCard(card, scroll) {
    if (selectedCard) { selectedCard.classList.remove('selected'); }
    selectedCard = card;
    if (card) {
      card.classList.add('selected');
      currentGroup = parseInt(card.getAttribute('data-group'), 10) - 1;
      if (scroll) { card.scrollIntoView({block: 'nearest', behavior: 'smooth'}); }
    }
    updateProgress();
  }

  function gotoGroup(index) {
    const clamped = Math.max(0, Math.min(groups.length - 1, index));
    currentGroup = clamped;
    const firstCard = groups[clamped].querySelector('.card[data-filename]');
    if (firstCard) { selectCard(firstCard, false); }
    groups[clamped].scrollIntoView({block: 'start', behavior: 'smooth'});
    updateProgress();
  }

  function exportText() {
    const lines = [];
    groups.forEach(function (group, gi) {
      const byDecision = {keep: [], remove: [], unsure: []};
      group.querySelectorAll('.card[data-filename]').forEach(function (card) {
        const d = decisionOf(card);
        if (d) { byDecision[d].push(card.getAttribute('data-filename')); }
      });
      const segments = [];
      ['keep', 'remove', 'unsure'].forEach(function (d) {
        if (byDecision[d].length) { segments.push(d.toUpperCase() + ' ' + byDecision[d].join(' ')); }
      });
      if (segments.length) { lines.push(PAGE_ID + ' group ' + (gi + 1) + ': ' + segments.join(' / ')); }
    });
    return lines;
  }

  cards.forEach(function (card) {
    const saved = stored[card.getAttribute('data-filename')];
    if (saved) { applyDecision(card, saved); }
    card.addEventListener('click', function () { selectCard(card, false); });
    card.querySelectorAll('.decision-btn').forEach(function (btn) {
      btn.addEventListener('click', function (event) {
        event.stopPropagation();
        selectCard(card, false);
        setDecision(card, btn.getAttribute('data-decision'));
      });
    });
  });

  document.getElementById('prev-group').addEventListener('click', function () { gotoGroup(currentGroup - 1); });
  document.getElementById('next-group').addEventListener('click', function () { gotoGroup(currentGroup + 1); });
  document.getElementById('copy-decisions').addEventListener('click', function () {
    const lines = exportText();
    if (!lines.length) {
      copyStatusEl.textContent = 'No decisions yet.';
      return;
    }
    const text = lines.join('\\n');
    function done() { copyStatusEl.textContent = 'Copied ' + lines.length + ' group(s) \\u2014 paste them back to apply.'; }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, function () { window.prompt('Copy your decisions:', text); });
    } else {
      window.prompt('Copy your decisions:', text);
    }
  });

  document.addEventListener('keydown', function (event) {
    if (event.metaKey || event.ctrlKey || event.altKey) { return; }
    const idx = selectedCard ? cards.indexOf(selectedCard) : -1;
    if (event.key === 'ArrowRight') { event.preventDefault(); gotoGroup(currentGroup + 1); }
    else if (event.key === 'ArrowLeft') { event.preventDefault(); gotoGroup(currentGroup - 1); }
    else if (event.key === 'ArrowDown') { event.preventDefault(); if (idx < cards.length - 1) { selectCard(cards[idx + 1], true); } }
    else if (event.key === 'ArrowUp') { event.preventDefault(); if (idx > 0) { selectCard(cards[idx - 1], true); } }
    else if (selectedCard && (event.key === 'k' || event.key === 'K')) { setDecision(selectedCard, 'keep'); if (idx < cards.length - 1) { selectCard(cards[idx + 1], true); } }
    else if (selectedCard && (event.key === 'r' || event.key === 'R')) { setDecision(selectedCard, 'remove'); if (idx < cards.length - 1) { selectCard(cards[idx + 1], true); } }
    else if (selectedCard && (event.key === 'u' || event.key === 'U')) { setDecision(selectedCard, 'unsure'); if (idx < cards.length - 1) { selectCard(cards[idx + 1], true); } }
  });

  window.addEventListener('scroll', function () {
    let nearest = 0;
    groups.forEach(function (group, gi) {
      if (group.getBoundingClientRect().top <= 140) { nearest = gi; }
    });
    if (nearest !== currentGroup) { currentGroup = nearest; updateProgress(); }
  }, {passive: true});

  if (cards.length) { selectCard(cards[0], false); }
  updateProgress();
})();
</script>
"""


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


def _render_details(item):
    details = item.get('details') or []
    if not details:
        return ''
    spans = ''.join(f'<span>{html.escape(str(d))}</span>' for d in details)
    return f'<div class="details">{spans}</div>'


def _render_card(item, compare=False, group_index=0):
    filename = html.escape(item['filename'])
    label = html.escape(item.get('label', ''))
    details = _render_details(item)
    if compare:
        suggestion = ''
        if item.get('tag') in _TAG_LABELS:
            suggestion = f'<div class="suggestion">Suggested: {_TAG_LABELS[item["tag"]]}</div>'
        label_row = f'<div class="label-row"><span class="label">{label}</span></div>' \
            if label else ''
        return f"""<div class="card" data-filename="{filename}" data-group="{group_index}">
  <a class="thumb-link" href="{item['original_uri']}" target="_blank" rel="noopener"><img src="{item['thumb_src']}" alt="{filename}" loading="lazy"></a>
  <div class="meta">
    <span class="filename">{filename}</span>
    {label_row}
    {details}
    {suggestion}
  </div>
  <div class="decision-row">
    <button type="button" class="decision-btn keep" data-decision="keep">Keep</button>
    <button type="button" class="decision-btn remove" data-decision="remove">Remove</button>
    <button type="button" class="decision-btn unsure" data-decision="unsure">Unsure</button>
  </div>
</div>"""
    chip = _render_chip(item.get('tag'))
    label_row = f'<div class="label-row"><span class="label">{label}</span>{chip}</div>' \
        if (label or chip) else ''
    return f"""<a class="card" href="{item['original_uri']}" target="_blank" rel="noopener">
  <span class="thumb-link"><img src="{item['thumb_src']}" alt="{filename}" loading="lazy"></span>
  <span class="meta">
    <span class="filename">{filename}</span>
    {label_row}
    {details}
  </span>
</a>"""


def _render_section(section, index=0, compare=False):
    heading = html.escape(section['heading'])
    count = len(section['items'])
    note = f'<p class="group-note">{html.escape(section["note"])}</p>' if section.get('note') else ''
    cards = '\n'.join(
        _render_card(item, compare=compare, group_index=index + 1)
        for item in section['items'])
    if compare:
        return f"""<section class="group compare-group" id="group-{index + 1}" data-group="{index + 1}">
  <h2 class="group-heading">{heading} <span class="group-count">{count} item{'s' if count != 1 else ''}</span></h2>
  {note}
  <div class="grid">
    {cards}
  </div>
</section>"""
    return f"""<section class="group">
  <h2 class="group-heading">{heading} <span class="group-count">{count} item{'s' if count != 1 else ''}</span></h2>
  {note}
  <div class="grid">
    {cards}
  </div>
</section>"""


def _render_compare_toolbar(total_groups):
    return f"""<div class="compare-toolbar">
  <span id="compare-progress">Group 1 of {total_groups} &middot; 0/{total_groups} groups fully decided</span>
  <span class="toolbar-actions">
    <button type="button" id="prev-group">&larr; Prev group</button>
    <button type="button" id="next-group">Next group &rarr;</button>
    <button type="button" id="copy-decisions">Copy decisions</button>
  </span>
  <span id="copy-status"></span>
</div>
<p class="compare-help">Click a photo to select it, then decide: <b>K</b> keep &middot; <b>R</b> remove &middot;
<b>U</b> unsure &middot; <b>&uarr;/&darr;</b> move between photos &middot; <b>&larr;/&rarr;</b> jump between groups.
Decisions are stored in this browser only &mdash; use &ldquo;Copy decisions&rdquo; to hand them back for applying.</p>"""


def _render_page_html(site_title, category, title, sections, variant=None, page_id=''):
    compare = variant == 'compare'
    body_sections = '\n'.join(
        _render_section(section, index=i, compare=compare)
        for i, section in enumerate(sections)) \
        or '<p class="empty-state">Nothing to show on this page.</p>'
    category_label = html.escape(_category_label(category))
    toolbar = _render_compare_toolbar(len(sections)) if compare else ''
    script = _COMPARE_SCRIPT.replace('__PAGE_ID_JSON__', json.dumps(page_id)) if compare else ''
    body_class = ' class="compare"' if compare else ''
    return f"""{_render_head(title, site_title)}
<body{body_class}>
<header class="site-header">
  <a class="site-title crumb" href="../index.html">{html.escape(site_title)}</a>
  <span class="crumb-sep">/</span>
  <span class="crumb">{category_label}</span>
  <span class="crumb-sep">/</span>
  <span class="crumb current">{html.escape(title)}</span>
</header>
{toolbar}
<main>
{body_sections}
</main>
{script}
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
                    'details': item.get('details') or [],
                })
            rendered_sections.append({
                'heading': section['heading'],
                'note': section.get('note', ''),
                'items': rendered_items,
            })
        return rendered_sections

    def add_page(self, category, page_id, title, sections, variant=None):
        """
        Writes review_root/{category}/{page_id}.html (generating thumbnails as
        needed), updates that category's manifest, and rebuilds review_root/index.html
        from every category's current manifest. Re-running with the same page_id
        replaces that page's manifest entry rather than duplicating it.

        variant='compare' renders the side-by-side comparison layout (larger
        images, per-photo detail rows, and the interactive decision layer)
        used by duplicate review; anything else renders the standard layout.

        Returns the path to the page that was written.
        """
        category_dir = os.path.join(self.review_root, category)
        os.makedirs(category_dir, exist_ok=True)
        os.makedirs(self.thumbnails_dir, exist_ok=True)

        rendered_sections = self._render_sections(sections)
        item_count = sum(len(s['items']) for s in rendered_sections)

        page_html = _render_page_html(self.site_title, category, title,
                                      rendered_sections, variant=variant,
                                      page_id=page_id)
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
