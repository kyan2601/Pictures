import os

import pandas as pd
from prettytable import PrettyTable

from src import constants, helper
from src.classes.entities.EventsMetadataFile import EventsMetadataFile
from src.classes.entities.MetadataFile import MetadataFile
from src.classes.workflows.GallerySite import GallerySite


def _human_size(num_bytes):
    size = float(num_bytes)
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if size < 1024 or unit == 'TB':
            return f'{size:.1f} {unit}'
        size /= 1024


def _media_type(filepath):
    ext = filepath.rsplit('.', 1)[-1].lower() if '.' in str(filepath) else ''
    if ext in [e.value for e in constants.PictureExtension]:
        return 'picture'
    if ext in [e.value for e in constants.VideoExtension]:
        return 'video'
    return 'other'


def _has_text(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return False
    return str(value).strip() != ''


class LibraryStats:
    """Prints library-wide statistics: file counts, storage, annotation
    coverage, hash coverage, events, and review status."""

    def run(self, years=None):
        years = years if years else helper.get_years_with_metadata()
        per_year = {}
        for year in years:
            per_year[year] = self._stats_for_year(MetadataFile.get_instance(year).df)
        if not per_year:
            print('No metadata found.')
            return per_year
        self._print_tables(per_year)
        self._print_library_wide()
        return per_year

    @staticmethod
    def _stats_for_year(df):
        stats = {
            'files': 0, 'pictures': 0, 'videos': 0, 'other': 0,
            'bytes': 0, 'picture_bytes': 0, 'video_bytes': 0,
            'missing_files': 0,
            'titled': 0, 'tagged': 0, 'with_people': 0, 'commented': 0,
            'highlights': 0, 'in_events': 0, 'pictures_with_hash': 0,
            'with_location': 0, 'with_gps': 0,
            'months': {},
        }
        if df is None or df.empty:
            return stats
        for _, row in df.iterrows():
            stats['files'] += 1
            media_type = _media_type(row['filepath'])
            stats[media_type + 's' if media_type != 'other' else 'other'] += 1

            filepath = row['filepath']
            if filepath and os.path.exists(filepath):
                size = os.path.getsize(filepath)
                stats['bytes'] += size
                if media_type == 'picture':
                    stats['picture_bytes'] += size
                elif media_type == 'video':
                    stats['video_bytes'] += size
            else:
                stats['missing_files'] += 1

            if _has_text(row.get('title')):
                stats['titled'] += 1
            if _has_text(row.get('tags')):
                stats['tagged'] += 1
            if _has_text(row.get('people')):
                stats['with_people'] += 1
            if _has_text(row.get('comments')):
                stats['commented'] += 1
            if row.get('is_highlight') == 1:
                stats['highlights'] += 1
            if _has_text(row.get('event_id')):
                stats['in_events'] += 1
            if media_type == 'picture' and _has_text(row.get('phash')):
                stats['pictures_with_hash'] += 1
            if _has_text(row.get('location_city')):
                stats['with_location'] += 1
            if pd.notna(row.get('latitude')) and pd.notna(row.get('longitude')):
                stats['with_gps'] += 1

            dt = row.get('dt')
            month = dt.strftime('%Y-%m') if pd.notna(dt) else 'unknown'
            stats['months'][month] = stats['months'].get(month, 0) + 1
        return stats

    def _print_tables(self, per_year):
        totals = {key: 0 for key in
                  ('files', 'pictures', 'videos', 'other', 'bytes', 'missing_files')}

        overview = PrettyTable(['Year', 'Files', 'Pictures', 'Videos', 'Storage', 'Missing files'])
        overview.align = 'r'
        overview.align['Year'] = 'l'
        for year in sorted(per_year):
            s = per_year[year]
            for key in totals:
                totals[key] += s[key]
            overview.add_row([year, s['files'], s['pictures'], s['videos'],
                              _human_size(s['bytes']), s['missing_files']])
        overview.add_row(['TOTAL', totals['files'], totals['pictures'], totals['videos'],
                          _human_size(totals['bytes']), totals['missing_files']])
        print(overview)

        coverage = PrettyTable(['Year', 'Titled', 'Tagged', 'People', 'Comments',
                                'Highlights', 'In events', 'Pictures w/ hash'])
        coverage.align = 'r'
        coverage.align['Year'] = 'l'
        for year in sorted(per_year):
            s = per_year[year]
            coverage.add_row([year, f"{s['titled']}/{s['files']}", f"{s['tagged']}/{s['files']}",
                              f"{s['with_people']}/{s['files']}", f"{s['commented']}/{s['files']}",
                              s['highlights'], s['in_events'],
                              f"{s['pictures_with_hash']}/{s['pictures']}"])
        print(coverage)

        months = PrettyTable(['Month', 'Files'])
        months.align = 'r'
        months.align['Month'] = 'l'
        all_months = {}
        for s in per_year.values():
            for month, count in s['months'].items():
                all_months[month] = all_months.get(month, 0) + count
        for month in sorted(all_months):
            months.add_row([month, all_months[month]])
        print(months)

    def _print_library_wide(self):
        try:
            event_count = len(EventsMetadataFile.get_instance().df)
        except RuntimeError:
            event_count = 0
        total_pages, pending_pages = GallerySite(constants.REVIEW_DIR).get_review_stats()
        print(f'Events: {event_count}')
        print(f'Review pages: {total_pages} total, {pending_pages} pending')

    # ------------------------------------------------------------------
    # Library health page: the run() numbers as a persistent gallery page,
    # with coverage percentages and a biggest-gaps summary, so cleanup
    # effort can be aimed at the years/dimensions that need it most.
    # ------------------------------------------------------------------

    HEALTH_CATEGORY = 'library-health'

    # (stats key, denominator key, display label)
    _COVERAGE_DIMENSIONS = [
        ('titled', 'files', 'Titled'),
        ('tagged', 'files', 'Tagged'),
        ('with_people', 'files', 'People'),
        ('with_location', 'files', 'Location'),
        ('with_gps', 'files', 'GPS'),
        ('pictures_with_hash', 'pictures', 'Hashed'),
    ]

    @staticmethod
    def _pct(part, whole):
        return f'{100 * part / whole:.0f}%' if whole else '—'

    @staticmethod
    def _pct_value(part, whole):
        return 100 * part / whole if whole else 0.0

    def _bar_html(self, label, part, whole):
        pct = self._pct_value(part, whole)
        level = 'good' if pct >= 90 else 'ok' if pct >= 60 else 'low'
        return (f'<div class="bar-row"><span class="bar-name">{label}</span>'
                f'<span class="bar-track"><span class="bar-fill {level}" '
                f'style="width:{pct:.0f}%"></span></span>'
                f'<span class="bar-pct">{self._pct(part, whole)}</span></div>')

    def _bars_html(self, stats):
        rows = ''.join(
            self._bar_html(label, stats[key], stats[denom])
            for key, denom, label in self._COVERAGE_DIMENSIONS)
        return f'<div class="bars">{rows}</div>'

    @staticmethod
    def _cards_html(cards):
        inner = ''.join(
            f'<div class="stat-card"><div class="stat-value">{value}</div>'
            f'<div class="stat-label">{label}</div></div>'
            for value, label in cards)
        return f'<div class="dash-cards">{inner}</div>'

    def _health_sections(self, per_year):
        totals = {}
        for s in per_year.values():
            for key, value in s.items():
                if isinstance(value, int):
                    totals[key] = totals.get(key, 0) + value

        years = sorted(per_year)
        span = f'{years[0]}' if years[0] == years[-1] else f'{years[0]}–{years[-1]}'
        glance_html = self._cards_html([
            (f"{totals['files']:,}", 'Files'),
            (f"{totals['pictures']:,}", 'Photos'),
            (f"{totals['videos']:,}", 'Videos'),
            (_human_size(totals['bytes']), 'Storage'),
            (f"{totals['highlights']:,}", 'Highlights'),
            (f"{totals['in_events']:,}", 'In events'),
            (span, 'Years'),
        ]) + self._bars_html(totals)
        sections = [{'heading': 'Library at a glance',
                     'note': '', 'items': [], 'html': glance_html}]

        for year in sorted(per_year, reverse=True):
            s = per_year[year]
            sub = (f'<p class="dash-sub">{s["files"]:,} files · '
                   f'{_human_size(s["bytes"])} · {s["highlights"]} '
                   f'highlight{"s" if s["highlights"] != 1 else ""}</p>')
            sections.append({'heading': str(year), 'note': '', 'items': [],
                             'html': sub + self._bars_html(s)})

        gap_lines = []
        for key, denom, label in self._COVERAGE_DIMENSIONS:
            total_missing = totals[denom] - totals[key]
            if total_missing <= 0:
                continue
            worst_year, worst_missing, worst_denom = None, -1, 0
            for year in years:
                s = per_year[year]
                missing = s[denom] - s[key]
                if missing > worst_missing:
                    worst_year, worst_missing, worst_denom = year, missing, s[denom]
            gap_lines.append(
                f'{label}: {total_missing} missing overall — worst in '
                f'{worst_year} ({worst_missing} of {worst_denom}, '
                f'{self._pct(worst_missing, worst_denom)} missing)')
        gaps_html = ''.join(f'<p class="dash-sub">{line}</p>' for line in gap_lines) \
            if gap_lines else '<p class="dash-sub">No coverage gaps found.</p>'
        sections.append({
            'heading': 'Biggest gaps',
            'note': '',
            'items': [],
            'html': gaps_html,
        })
        return sections

    def build_health_page(self, regenerate=False):
        """Builds (or serves) review/library-health/index.html: per-year
        annotation/location/hash coverage with a biggest-gaps summary.
        Re-running serves the saved page; regenerate=True rebuilds it."""
        page_path = os.path.join(
            constants.REVIEW_DIR, self.HEALTH_CATEGORY, 'index.html')
        if os.path.exists(page_path) and not regenerate:
            print(f'Library health page already exists: {page_path}')
            print('Serving the existing page. '
                  'Re-run with --regenerate to rebuild it.')
            return page_path

        per_year = {}
        for year in helper.get_years_with_metadata():
            per_year[year] = self._stats_for_year(MetadataFile.get_instance(year).df)
        if not per_year:
            print('No metadata found.')
            return None

        sections = self._health_sections(per_year)
        written = GallerySite(constants.REVIEW_DIR).add_page(
            self.HEALTH_CATEGORY, 'index', 'Library Health', sections)
        total_files = sum(s['files'] for s in per_year.values())
        print(f'Library health: {total_files} file(s) across '
              f'{len(per_year)} year(s).')
        print(f'Page: {written}')
        return written
