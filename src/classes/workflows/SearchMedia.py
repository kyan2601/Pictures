from datetime import datetime, timedelta

import pandas as pd
from prettytable import PrettyTable

from src import helper
from src.classes.entities.MetadataFile import MetadataFile


class SearchMedia:
    """Queries metadata.csv files across years and prints matching media.

    Filters combine with AND. Multi-value filters (tags, people) match when
    ANY of the given values is present (case-insensitive); text filters
    (title, comments) are case-insensitive substring matches.
    """

    COLUMNS = ['filepath', 'dt', 'title', 'tags', 'people', 'event_id', 'is_highlight']

    @staticmethod
    def _matches_any(stored_value, wanted):
        if stored_value is None or (isinstance(stored_value, float) and pd.isna(stored_value)):
            return False
        stored = {part.strip().lower() for part in str(stored_value).split(';') if part.strip()}
        return bool(stored & {w.strip().lower() for w in wanted if w.strip()})

    @staticmethod
    def _split_values(value):
        return [part.strip() for part in str(value).replace(',', ';').split(';') if part.strip()]

    def run(self, years=None, tags=None, people=None, title=None, comments=None,
            event_id=None, is_highlight=None, start_date=None, end_date=None, limit=None):
        years = years if years else helper.get_years()
        frames = []
        for year in years:
            metadata_file = MetadataFile.get_instance(year)
            if metadata_file.df is None or metadata_file.df.empty:
                continue
            frames.append(metadata_file.df)
        if not frames:
            print('No metadata found.')
            return pd.DataFrame(columns=self.COLUMNS)

        df = pd.concat(frames, ignore_index=True)

        if tags:
            df = df[df['tags'].apply(lambda v: self._matches_any(v, self._split_values(tags)))]
        if people:
            df = df[df['people'].apply(lambda v: self._matches_any(v, self._split_values(people)))]
        if title:
            df = df[df['title'].str.contains(title, case=False, na=False)]
        if comments:
            df = df[df['comments'].str.contains(comments, case=False, na=False)]
        if event_id is not None:
            df = df[df['event_id'] == int(event_id)]
        if is_highlight:
            df = df[df['is_highlight'] == 1]
        if start_date:
            df = df[df['dt'] >= datetime.strptime(start_date, '%Y-%m-%d')]
        if end_date:
            df = df[df['dt'] < datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)]

        df = df.sort_values(by='dt').reset_index(drop=True)
        if limit is not None:
            df = df.head(limit)

        table = PrettyTable(['Filepath', 'Datetime', 'Title', 'Tags', 'People', 'Event', 'Highlight'])
        table.align = 'l'
        for _, row in df.iterrows():
            table.add_row([
                row['filepath'],
                row['dt'].strftime('%Y-%m-%d %H:%M') if pd.notna(row['dt']) else '',
                row['title'] if pd.notna(row['title']) else '',
                row['tags'] if pd.notna(row['tags']) else '',
                row['people'] if pd.notna(row['people']) else '',
                '' if pd.isna(row['event_id']) else int(row['event_id']),
                'yes' if row['is_highlight'] == 1 else '',
            ])
        print(table)
        print(f'{len(df)} result(s)')
        return df
