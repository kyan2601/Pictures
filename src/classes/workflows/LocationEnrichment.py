"""
Offline location enrichment: backfills `location_city` / `location_country`
for metadata rows that already have GPS coordinates.

Uses the `reverse_geocoder` package (kd-tree over GeoNames populated places,
no network) plus `pycountry` for ISO country codes -> country names.
"""

import pandas as pd
import pycountry
import reverse_geocoder as rg

from src import constants, helper
from src.classes.entities.MetadataFile import MetadataFile


def _country_name(country_code):
    try:
        return pycountry.countries.get(alpha_2=country_code).name
    except (AttributeError, LookupError):
        return country_code


def _reverse_geocode(coords):
    """coords: list of (lat, lon). Returns list of (city, country) tuples."""
    results = []
    for hit in rg.search(coords):
        results.append((hit['name'], _country_name(hit['cc'])))
    return results


def _has_value(value):
    return value is not None and not (isinstance(value, float) and pd.isna(value)) \
        and value != ''


class LocationEnrichment:
    """Backfills location_city/location_country from GPS coordinates."""

    def enrich(self, years=None, dry_run=True):
        """
        For every row with GPS coordinates but no location yet, looks up the
        nearest city offline and fills location_city/location_country.

        :param years: Year ints to process. Defaults to all years.
        :param dry_run: If True, only reports what would change. Defaults to True.
        :return: Dict of per-year stats.
        """
        years = years if years is not None else helper.get_years()
        summary = {}
        for year in years:
            summary[year] = self._enrich_year(year, dry_run)
        return summary

    def _enrich_year(self, year, dry_run):
        mf = MetadataFile.get_instance(year)
        # reset_index: add_media_metadata's concat can leave duplicate index
        # labels, which would make label-based .at access ambiguous.
        df = mf.df.reset_index(drop=True)
        # Columns that have never held a value load as float64; writing city
        # names into them needs object dtype.
        for col in ('location_city', 'location_country'):
            df[col] = df[col].astype(object)

        def needs_location(row):
            return _has_value(row['latitude']) and _has_value(row['longitude']) \
                and not _has_value(row.get('location_city'))

        mask = df.apply(needs_location, axis=1)
        has_gps = df['latitude'].apply(_has_value) & df['longitude'].apply(_has_value)
        no_gps = int((~has_gps).sum())
        already = int((has_gps & ~mask).sum())

        assignments = {}
        if mask.any():
            pairs = df.loc[mask, ['latitude', 'longitude']].drop_duplicates()
            coords = [(float(r['latitude']), float(r['longitude']))
                      for _, r in pairs.iterrows()]
            print(f'[{year}] reverse-geocoding {len(coords)} unique coordinate(s) '
                  f'for {int(mask.sum())} photo(s)...')
            lookups = dict(zip(coords, _reverse_geocode(coords)))
            for pos in df.index[mask]:
                assignments[pos] = lookups[(float(df.at[pos, 'latitude']),
                                            float(df.at[pos, 'longitude']))]

        updated = len(assignments)
        if dry_run:
            print(f'[{year}] dry run: would fill location for {updated} photo(s) '
                  f'({already} already have it, {no_gps} have no GPS).')
        else:
            for pos, (city, country) in assignments.items():
                df.at[pos, 'location_city'] = city
                df.at[pos, 'location_country'] = country
            if updated:
                mf.df = df
                mf.write()
            print(f'[{year}] filled location for {updated} photo(s) '
                  f'({already} already had it, {no_gps} have no GPS).')
        return {'updated': updated, 'already': already, 'no_gps': no_gps}
