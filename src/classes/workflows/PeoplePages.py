import os
import re
from collections import defaultdict

import pandas as pd

from src import constants, helper
from src.classes.entities.MetadataFile import MetadataFile
from src.classes.workflows.GallerySite import GallerySite
from src.classes.workflows.YearInReview import _split_values


def _slugify(name, taken):
    """Maps a person's name to a unique page id ('Mary Jane' -> 'mary-jane')."""
    base = re.sub(r'[^a-z0-9]+', '-', str(name).lower()).strip('-') or 'person'
    slug, n = base, 2
    while slug in taken:
        slug = f'{base}-{n}'
        n += 1
    taken.add(slug)
    return slug


class PeoplePages:
    """Builds one gallery page per person from the `people` metadata column
    (populated by annotation and by `faces apply`): a summary line, then the
    person's photos grouped by year, highlights first within each year.

    Pages are written to review/people/ and then served as-is: re-running
    returns the existing pages untouched. Pass regenerate=True to rebuild —
    needed after new photos land or more face clusters get named/applied,
    since the saved pages otherwise go stale.
    """

    CATEGORY = 'people'

    def page_dir(self):
        return os.path.join(constants.REVIEW_DIR, self.CATEGORY)

    def _collect(self):
        """Returns {person: [{'filepath', 'dt', 'title', 'is_highlight', 'year'}]}."""
        people = defaultdict(list)
        for year in helper.get_years():
            df = MetadataFile.get_instance(year).df
            if df is None or df.empty or 'people' not in df.columns:
                continue
            for _, row in df.iterrows():
                names = _split_values(row.get('people'))
                if not names:
                    continue
                dt = row.get('dt')
                entry_year = dt.year if pd.notna(dt) else \
                    helper.get_year_from_filepath(row['filepath'])
                title = row.get('title')
                entry = {
                    'filepath': row['filepath'],
                    'dt': dt,
                    'title': title.strip() if isinstance(title, str) else '',
                    'is_highlight': row.get('is_highlight') == 1,
                    'year': entry_year,
                }
                for name in names:
                    people[name].append(entry)
        return people

    def _label(self, entry):
        if entry['title']:
            return entry['title']
        if pd.notna(entry['dt']):
            return entry['dt'].strftime('%B %d, %Y')
        return os.path.basename(entry['filepath'])

    def _sections_for(self, person, entries, per_year_limit):
        def _dt_key(entry):
            return entry['dt'] if pd.notna(entry['dt']) else pd.Timestamp.min

        dated = sorted((e for e in entries if e['year'] is not None),
                       key=lambda e: (e['year'], _dt_key(e)))
        undated = [e for e in entries if e['year'] is None]
        highlights = sum(1 for e in entries if e['is_highlight'])

        if dated:
            span = f"{dated[0]['year']}"
            if dated[-1]['year'] != dated[0]['year']:
                span += f"–{dated[-1]['year']}"
        else:
            span = 'dates unknown'
        summary = (f"{len(entries)} photo{'s' if len(entries) != 1 else ''} · "
                   f"{span} · {highlights} highlight{'s' if highlights != 1 else ''}")
        sections = [{'heading': f'{person} at a glance',
                     'note': summary, 'items': []}]

        by_year = defaultdict(list)
        for entry in dated:
            by_year[entry['year']].append(entry)
        for year in sorted(by_year):
            year_entries = sorted(
                by_year[year],
                key=lambda e: (not e['is_highlight'], _dt_key(e)))
            shown = year_entries[:per_year_limit]
            note = f"{len(year_entries)} photo{'s' if len(year_entries) != 1 else ''}"
            if len(shown) < len(year_entries):
                note += f' · showing {len(shown)}'
            items = []
            for entry in shown:
                label = self._label(entry)
                if entry['is_highlight']:
                    label = f'★ {label}'
                items.append({'filepath': entry['filepath'], 'label': label})
            sections.append({'heading': str(year), 'note': note, 'items': items})

        if undated:
            items = [{'filepath': e['filepath'], 'label': self._label(e)}
                     for e in undated[:per_year_limit]]
            sections.append({'heading': 'Date unknown',
                             'note': f"{len(undated)} photo(s)", 'items': items})
        return sections

    def run(self, regenerate=False, min_photos=3, per_year_limit=12):
        page_dir = self.page_dir()
        existing = []
        if os.path.isdir(page_dir):
            existing = [f for f in os.listdir(page_dir) if f.endswith('.html')]
        if existing and not regenerate:
            print(f'{len(existing)} people page(s) already exist: {page_dir}')
            print('Serving the existing pages. '
                  'Re-run with --regenerate to rebuild them.')
            return page_dir

        people = self._collect()
        ranked = sorted(people.items(),
                        key=lambda kv: (-len(kv[1]), kv[0].lower()))
        site = GallerySite(constants.REVIEW_DIR)
        taken = set()
        built = []
        for person, entries in ranked:
            if len(entries) < min_photos:
                continue
            slug = _slugify(person, taken)
            sections = self._sections_for(person, entries, per_year_limit)
            site.add_page(self.CATEGORY, slug, f'People — {person}', sections)
            built.append((person, len(entries)))

        if not built:
            print(f'No people with at least {min_photos} photo(s) found. '
                  'Annotate photos or run faces apply first.')
            return None

        skipped = len(ranked) - len(built)
        print(f'Built {len(built)} people page(s) in {page_dir}'
              + (f' ({skipped} below the {min_photos}-photo minimum).'
                 if skipped else '.'))
        for person, count in built[:10]:
            print(f'  {person}: {count} photo(s)')
        if len(built) > 10:
            print(f'  … and {len(built) - 10} more.')
        return page_dir
