from datetime import datetime

import pandas as pd

from src import constants, helper
from src.classes.entities.MetadataFile import MetadataFile
from src.classes.workflows.GallerySite import GallerySite


class MemoryLane:
    """Builds an 'on this day' gallery page: for the given month/day, one
    section per previous year with that day's photos, highlights first."""

    CATEGORY = 'memory-lane'

    def _collect_sections(self, month, day, limit_per_year):
        sections = []
        current_year = datetime.now().year
        for year in helper.get_years():
            if year >= current_year:
                continue
            df = MetadataFile.get_instance(year).df
            if df is None or df.empty:
                continue
            matches = df[df['dt'].apply(
                lambda v: pd.notna(v) and v.month == month and v.day == day)]
            if matches.empty:
                continue
            ranked = matches.assign(
                _highlight=(matches['is_highlight'] == 1).astype(int))
            ranked = ranked.sort_values(
                by=['_highlight', 'dt'], ascending=[False, True]).head(limit_per_year)

            items = []
            for _, row in ranked.iterrows():
                title = row.get('title')
                title = title.strip() if isinstance(title, str) and title.strip() else ''
                is_highlight = row['_highlight'] == 1
                items.append({
                    'filepath': row['filepath'],
                    'label': f"★ {title}" if is_highlight and title else
                             ('★' if is_highlight else title),
                })
            years_ago = current_year - year
            sections.append({
                'heading': f'{year} — {years_ago} year{"s" if years_ago != 1 else ""} ago',
                'note': f"{len(ranked)} photo{'s' if len(ranked) != 1 else ''} from "
                        f"{datetime(year, month, day).strftime('%B %d')}",
                'items': items,
            })
        return sections

    def run(self, month=None, day=None, limit_per_year=12):
        today = datetime.now()
        month = month if month is not None else today.month
        day = day if day is not None else today.day
        try:
            label = datetime(2000, month, day).strftime('%B %d')
        except ValueError:
            raise RuntimeError(f'Invalid month/day: {month}/{day}')

        sections = self._collect_sections(month, day, limit_per_year)
        if not sections:
            print(f'No photos found for {label} in previous years.')
            return None

        total = sum(len(s['items']) for s in sections)
        page_id = f'{month:02d}-{day:02d}'
        page_path = GallerySite(constants.REVIEW_DIR).add_page(
            self.CATEGORY, page_id, f'Memory Lane — {label}', sections)
        print(f'Memory lane for {label}: {total} photo(s) across {len(sections)} year(s).')
        print(f'Page: {page_path}')
        return page_path
