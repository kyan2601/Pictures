from src import helper
from src.classes.entities.MetadataFile import MetadataFile


class AnnotateMedia:
    """Edits annotation fields on existing metadata records.

    Annotatable fields: title, tags, people, comments, is_highlight.
    Multi-value fields (tags, people) accept comma- or semicolon-separated
    input and are stored ';'-separated, matching ingest behavior.
    Files are grouped by year so each metadata file is loaded and written once.
    """

    ANNOTATABLE_FIELDS = ('title', 'tags', 'people', 'comments', 'is_highlight')

    def __init__(self, dry_run=True):
        self.dry_run = dry_run

    @staticmethod
    def _normalize_list(value):
        if isinstance(value, str):
            value = value.replace(',', ';')
            parts = [part.strip() for part in value.split(';')]
        else:
            parts = [str(part).strip() for part in value]
        return ';'.join(part for part in parts if part)

    def run(self, files, title=None, tags=None, people=None, comments=None, is_highlight=None):
        updates = {}
        if title is not None:
            updates['title'] = title
        if tags is not None:
            updates['tags'] = self._normalize_list(tags)
        if people is not None:
            updates['people'] = self._normalize_list(people)
        if comments is not None:
            updates['comments'] = comments
        if is_highlight is not None:
            updates['is_highlight'] = int(is_highlight)
        if not updates:
            raise RuntimeError('No annotation fields provided; nothing to update.')

        files_by_year = {}
        for filepath in files:
            year = helper.get_year_from_filepath(filepath)
            files_by_year.setdefault(year, []).append(filepath)

        for year, year_files in sorted(files_by_year.items()):
            metadata_file = MetadataFile.get_instance(year)
            changed = []
            for filepath in year_files:
                if not metadata_file.has_media_metadata(filepath):
                    print(f'  [skip] no metadata record for {filepath}')
                    continue
                record = metadata_file.get_media_metadata(filepath)
                record.update(updates)
                changed.append(record)
            if not changed:
                continue
            if self.dry_run:
                print(f'[dry run] would update {len(changed)} record(s) '
                      f'in {year}/metadata.csv: {updates}')
            else:
                for record in changed:
                    metadata_file.add_media_metadata(record, update=True, write=False)
                metadata_file.write()
                print(f'Updated {len(changed)} record(s) in {year}/metadata.csv: {updates}')
