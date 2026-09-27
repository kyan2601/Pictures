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
        years = years if years else helper.get_years()
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
