import pandas as pd

from src import constants, helper
from src.classes.entities.MetadataFile import MetadataFile
from src.classes.workflows.GallerySite import GallerySite


class HighlightReel:
    """Builds a best-of-year gallery page from is_highlight media, grouped
    into one section per month."""

    CATEGORY = 'highlight-reel'

    def _latest_year_with_highlights(self):
        for year in sorted(helper.get_years_with_metadata(), reverse=True):
            df = MetadataFile.get_instance(year).df
            if df is not None and not df.empty and (df['is_highlight'] == 1).any():
                return year
        return None

    def _collect_sections(self, year, limit):
        df = MetadataFile.get_instance(year).df
        if df is None or df.empty:
            return []
        highlights = df[df['is_highlight'] == 1].copy()
        highlights = highlights[highlights['dt'].apply(pd.notna)]
        if highlights.empty:
            return []
        highlights = highlights.sort_values(by='dt').head(limit)

        sections = []
        for (month, month_df) in highlights.groupby(highlights['dt'].apply(lambda v: v.month), sort=True):
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

    def run(self, year=None, limit=100):
        if year is None:
            year = self._latest_year_with_highlights()
            if year is None:
                print('No highlights found in any year. Mark some with: '
                      'python -m src.cli annotate --files <paths...> --highlight --execute')
                return None
            print(f'Using {year}, the latest year with highlights.')

        sections = self._collect_sections(year, limit)
        if not sections:
            print(f'No highlights found for {year}.')
            return None

        total = sum(len(s['items']) for s in sections)
        page_path = GallerySite(constants.REVIEW_DIR).add_page(
            self.CATEGORY, str(year), f'Highlights — {year}', sections)
        print(f'Highlight reel for {year}: {total} photo(s) across {len(sections)} month(s).')
        print(f'Page: {page_path}')
        return page_path
