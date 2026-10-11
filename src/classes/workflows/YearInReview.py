import os
from collections import Counter
from datetime import datetime

import pandas as pd

from src import constants, helper
from src.classes.entities.EventsMetadataFile import EventsMetadataFile
from src.classes.entities.MetadataFile import MetadataFile
from src.classes.workflows.GallerySite import GallerySite
from src.classes.workflows.LibraryStats import LibraryStats, _human_size


def _split_values(value):
    """Splits a ';'-separated multi-value metadata field (tags, people)."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    return [part.strip() for part in str(value).split(';') if part.strip()]


def _format_counter(counter_items):
    return ' · '.join(f'{name} ({count})' for name, count in counter_items)


class YearInReview:
    """Builds a 'year in review' gallery page for one year: a stats summary,
    highlights grouped by month, top tags, top people, and the year's events.

    The page is written to the review site on the library drive and then
    served as-is: re-running for a year that already has a page returns the
    existing page untouched. Pass regenerate=True to rebuild it — needed
    after retroactively adding photos to a past year, since the saved page
    otherwise goes stale."""

    CATEGORY = 'year-in-review'

    def page_path(self, year):
        return os.path.join(constants.REVIEW_DIR, self.CATEGORY, f'{year}.html')

    def _top_values(self, df, column, limit=10):
        counter = Counter()
        for value in df[column]:
            counter.update(_split_values(value))
        return counter.most_common(limit)

    def _events_for_year(self, year):
        try:
            events_df = EventsMetadataFile.get_instance().df
        except RuntimeError:
            return []
        if events_df is None or events_df.empty:
            return []
        events = []
        for _, row in events_df.iterrows():
            try:
                start = datetime.strptime(str(row['start_date']), '%Y-%m-%d')
                end = datetime.strptime(str(row['end_date']), '%Y-%m-%d')
            except (ValueError, TypeError):
                continue
            if start.year <= year <= end.year:
                events.append({'title': str(row['title']),
                               'start_date': start, 'end_date': end})
        return sorted(events, key=lambda e: e['start_date'])

    def _summary_section(self, year, df):
        stats = LibraryStats._stats_for_year(df)
        lines = [f"{stats['files']} file{'s' if stats['files'] != 1 else ''} · "
                 f"{stats['pictures']} photo{'s' if stats['pictures'] != 1 else ''} · "
                 f"{stats['videos']} video{'s' if stats['videos'] != 1 else ''} · "
                 f"{_human_size(stats['bytes'])} · "
                 f"{stats['highlights']} highlight{'s' if stats['highlights'] != 1 else ''}"]
        month_counts = []
        for month_key in sorted(stats['months']):
            if month_key == 'unknown':
                continue
            month_name = datetime.strptime(month_key, '%Y-%m').strftime('%b')
            month_counts.append(f"{month_name} {stats['months'][month_key]}")
        if month_counts:
            lines.append('Photos by month: ' + ' · '.join(month_counts))
        return {'heading': f'{year} at a glance',
                'note': '\n'.join(lines), 'items': []}

    def _highlight_sections(self, df, per_month_limit):
        highlights = df[(df['is_highlight'] == 1) & df['dt'].apply(pd.notna)].copy()
        if highlights.empty:
            return []
        highlights = highlights.sort_values(by='dt')
        sections = []
        for month, month_df in highlights.groupby(
                highlights['dt'].apply(lambda v: v.month), sort=True):
            month_df = month_df.head(per_month_limit)
            month_name = month_df['dt'].iloc[0].strftime('%B')
            items = []
            for _, row in month_df.iterrows():
                title = row.get('title')
                title = title.strip() if isinstance(title, str) and title.strip() else ''
                items.append({
                    'filepath': row['filepath'],
                    'label': title if title else row['dt'].strftime('%B %d'),
                })
            sections.append({
                'heading': month_name,
                'note': f"{len(items)} highlight{'s' if len(items) != 1 else ''}",
                'items': items,
            })
        return sections

    def _build_sections(self, year, df, per_month_limit):
        sections = [self._summary_section(year, df)]
        sections.extend(self._highlight_sections(df, per_month_limit))

        top_tags = self._top_values(df, 'tags')
        if top_tags:
            sections.append({'heading': 'Top tags',
                             'note': _format_counter(top_tags), 'items': []})
        top_people = self._top_values(df, 'people')
        if top_people:
            sections.append({'heading': 'Top people',
                             'note': _format_counter(top_people), 'items': []})

        events = self._events_for_year(year)
        if events:
            lines = []
            for event in events:
                start = event['start_date'].strftime('%b %d')
                if event['start_date'].date() == event['end_date'].date():
                    lines.append(f"{event['title']} ({start})")
                else:
                    end = event['end_date'].strftime('%b %d')
                    lines.append(f"{event['title']} ({start} – {end})")
            sections.append({'heading': 'Events',
                             'note': ' · '.join(lines), 'items': []})
        return sections

    def run(self, year=None, regenerate=False, per_month_limit=12):
        if year is None:
            years = helper.get_years()
            if not years:
                print('No years found in the library.')
                return None
            year = years[-1]
            print(f'Using {year}, the latest year in the library.')

        page_path = self.page_path(year)
        if os.path.exists(page_path) and not regenerate:
            print(f'Year in review for {year} already exists: {page_path}')
            print('Serving the existing page. Re-run with --regenerate to rebuild it.')
            return page_path

        df = MetadataFile.get_instance(year).df
        if df is None or df.empty:
            print(f'No metadata found for {year}.')
            return None

        sections = self._build_sections(year, df, per_month_limit)
        written = GallerySite(constants.REVIEW_DIR).add_page(
            self.CATEGORY, str(year), f'Year in Review — {year}', sections)
        stats = LibraryStats._stats_for_year(df)
        print(f"Year in review for {year}: {stats['files']} file(s), "
              f"{stats['highlights']} highlight(s) across "
              f"{len(sections)} section(s).")
        print(f'Page: {written}')
        return written
