from src import cli, helper
import os
import pytest


class _FakeWorkflow:
    """Records constructor args/kwargs and every run() call on each instance."""

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.run_calls = []
        self.instances.append(self)

    def run(self, *args, **kwargs):
        self.run_calls.append((args, kwargs))


def _fresh_fake_class():
    # A fresh 'instances' list per test avoids bleed-over between tests.
    return type('Fake', (_FakeWorkflow,), {'instances': []})


class TestProcessNew:
    def test_defaults_to_dry_run_and_no_directory_override(self, monkeypatch):
        fake = _fresh_fake_class()
        monkeypatch.setattr(cli, 'ProcessNewMedia', fake)

        cli.main(['process-new'])

        assert len(fake.instances) == 1
        assert fake.instances[0].kwargs == {'dry_run': True, 'directory': None}
        assert fake.instances[0].run_calls == [((), {})]

    def test_execute_flag_disables_dry_run(self, monkeypatch):
        fake = _fresh_fake_class()
        monkeypatch.setattr(cli, 'ProcessNewMedia', fake)

        cli.main(['process-new', '--execute'])

        assert fake.instances[0].kwargs == {'dry_run': False, 'directory': None}

    def test_directory_flag_is_passed_through(self, monkeypatch):
        fake = _fresh_fake_class()
        monkeypatch.setattr(cli, 'ProcessNewMedia', fake)

        cli.main(['process-new', '--directory', 'new/some_import'])

        assert fake.instances[0].kwargs == {'dry_run': True, 'directory': 'new/some_import'}


class TestCleanup:
    def test_runs_for_each_year_in_order(self, monkeypatch):
        fake = _fresh_fake_class()
        monkeypatch.setattr(cli, 'MetadataCleanupChecks', fake)

        cli.main(['cleanup', '--year', '2024', '2025'])

        assert [inst.kwargs['year'] for inst in fake.instances] == [2024, 2025]
        assert all(inst.run_calls == [((), {'dry_run': True})] for inst in fake.instances)

    def test_execute_flag_disables_dry_run(self, monkeypatch):
        fake = _fresh_fake_class()
        monkeypatch.setattr(cli, 'MetadataCleanupChecks', fake)

        cli.main(['cleanup', '--year', '2025', '--execute'])

        assert fake.instances[0].run_calls == [((), {'dry_run': False})]


class TestFindDuplicates:
    def test_month_given_scans_month_directory(self, tmp_root, monkeypatch):
        fake = _fresh_fake_class()
        monkeypatch.setattr(cli, 'DuplicateImageCheck', fake)

        cli.main(['find-duplicates', '--year', '2025', '--month', '10'])

        expected_dir = helper.get_directory_for_year_month(2025, 10)
        assert fake.instances[0].args == (expected_dir,)
        assert fake.instances[0].run_calls == [((), {'dry_run': True})]

    def test_month_omitted_scans_whole_year_directory(self, tmp_root, monkeypatch):
        fake = _fresh_fake_class()
        monkeypatch.setattr(cli, 'DuplicateImageCheck', fake)

        cli.main(['find-duplicates', '--year', '2025'])

        expected_dir = helper.get_directory_for_year(2025)
        assert fake.instances[0].args == (expected_dir,)

    def test_execute_flag_disables_dry_run(self, tmp_root, monkeypatch):
        fake = _fresh_fake_class()
        monkeypatch.setattr(cli, 'DuplicateImageCheck', fake)

        cli.main(['find-duplicates', '--year', '2025', '--execute'])

        assert fake.instances[0].run_calls == [((), {'dry_run': False})]


class TestCleanupBackups:
    def test_defaults_to_dry_run_and_thirty_days(self, monkeypatch):
        calls = []
        monkeypatch.setattr(cli, 'cleanup_backups_main', lambda **kwargs: calls.append(kwargs))

        cli.main(['cleanup-backups'])

        assert calls == [{'dry_run': True, 'retention_days': 30}]

    def test_execute_flag_disables_dry_run(self, monkeypatch):
        calls = []
        monkeypatch.setattr(cli, 'cleanup_backups_main', lambda **kwargs: calls.append(kwargs))

        cli.main(['cleanup-backups', '--execute'])

        assert calls == [{'dry_run': False, 'retention_days': 30}]

    def test_retention_days_is_passed_through(self, monkeypatch):
        calls = []
        monkeypatch.setattr(cli, 'cleanup_backups_main', lambda **kwargs: calls.append(kwargs))

        cli.main(['cleanup-backups', '--retention-days', '7'])

        assert calls == [{'dry_run': True, 'retention_days': 7}]


class TestAssignDate:
    def test_defaults_to_dry_run(self, monkeypatch):
        fake = _fresh_fake_class()
        monkeypatch.setattr(cli, 'AssignDate', fake)

        cli.main(['assign-date', '--files', 'a.jpg', 'b.jpg', '--date', '2025-06-15'])

        assert fake.instances[0].kwargs == {'dry_run': True}
        assert fake.instances[0].run_calls == [((['a.jpg', 'b.jpg'], '2025-06-15'), {})]

    def test_execute_flag_disables_dry_run(self, monkeypatch):
        fake = _fresh_fake_class()
        monkeypatch.setattr(cli, 'AssignDate', fake)

        cli.main(['assign-date', '--files', 'a.jpg', '--date', '2025-06-15', '--execute'])

        assert fake.instances[0].kwargs == {'dry_run': False}


class TestMarkReviewed:
    def _fake_gallery_site(self, instances):
        class FakeGallerySite:
            def __init__(self, review_root):
                self.review_root = review_root
                self.marked = []
                instances.append(self)

            def mark_reviewed(self, page_path):
                self.marked.append(page_path)

        return FakeGallerySite

    def test_marks_page_reviewed(self, tmp_root, monkeypatch):
        instances = []
        monkeypatch.setattr(cli, 'GallerySite', self._fake_gallery_site(instances))

        cli.main(['mark-reviewed', '--category', 'duplicate-check', '--page', '2022-05'])

        assert len(instances) == 1
        assert instances[0].review_root == str(tmp_root / 'review')
        expected = os.path.join(str(tmp_root / 'review'), 'duplicate-check', '2022-05.html')
        assert instances[0].marked == [expected]

    def test_propagates_error_for_unknown_page(self, tmp_root, monkeypatch):
        instances = []
        fake_class = self._fake_gallery_site(instances)

        def fail_mark_reviewed(self, page_path):
            raise ValueError(f'No review page found at {page_path}')

        fake_class.mark_reviewed = fail_mark_reviewed
        monkeypatch.setattr(cli, 'GallerySite', fake_class)

        with pytest.raises(ValueError, match='No review page found'):
            cli.main(['mark-reviewed', '--category', 'duplicate-check', '--page', 'nope'])


class TestAnnotate:
    def test_defaults_to_dry_run_and_passes_fields(self, monkeypatch):
        fake = _fresh_fake_class()
        monkeypatch.setattr(cli, 'AnnotateMedia', fake)

        cli.main(['annotate', '--files', 'a.jpg', 'b.jpg', '--title', 'Trip',
                  '--tags', 'beach,sun', '--people', 'alice', '--comments', 'nice',
                  '--highlight'])

        assert fake.instances[0].kwargs == {'dry_run': True}
        assert fake.instances[0].run_calls == [
            ((['a.jpg', 'b.jpg'],),
             {'title': 'Trip', 'tags': 'beach,sun', 'people': 'alice',
              'comments': 'nice', 'is_highlight': True})]

    def test_no_highlight_flag(self, monkeypatch):
        fake = _fresh_fake_class()
        monkeypatch.setattr(cli, 'AnnotateMedia', fake)

        cli.main(['annotate', '--files', 'a.jpg', '--no-highlight'])

        assert fake.instances[0].run_calls[0][1]['is_highlight'] is False

    def test_highlight_defaults_to_none(self, monkeypatch):
        fake = _fresh_fake_class()
        monkeypatch.setattr(cli, 'AnnotateMedia', fake)

        cli.main(['annotate', '--files', 'a.jpg', '--title', 'Trip'])

        assert fake.instances[0].run_calls[0][1]['is_highlight'] is None

    def test_execute_flag_disables_dry_run(self, monkeypatch):
        fake = _fresh_fake_class()
        monkeypatch.setattr(cli, 'AnnotateMedia', fake)

        cli.main(['annotate', '--files', 'a.jpg', '--title', 'Trip', '--execute'])

        assert fake.instances[0].kwargs == {'dry_run': False}


class _FakeEvent:
    event_id = 7
    title = 'Trip'

    def get_directory(self):
        return '/fake/event/dir'


class _FakeEventsFile:
    instances = []

    def __init__(self):
        self.preview_calls = []
        self.create_calls = []
        _FakeEventsFile.instances.append(self)

    @classmethod
    def get_instance(cls):
        return cls()

    def preview_event(self, **kwargs):
        self.preview_calls.append(kwargs)
        return (_FakeEvent(), 'media_df')

    def create_event(self, **kwargs):
        self.create_calls.append(kwargs)
        return _FakeEvent()


class TestCreateEvent:
    def test_dry_run_previews_without_creating(self, monkeypatch):
        _FakeEventsFile.instances = []
        monkeypatch.setattr(cli, 'EventsMetadataFile', _FakeEventsFile)

        cli.main(['create-event', '--title', 'Trip', '--start-date', '2025-06-01',
                  '--end-date', '2025-06-07', '--description', 'Fun',
                  '--nominal-month', 'June'])

        assert len(_FakeEventsFile.instances) == 1
        fake = _FakeEventsFile.instances[0]
        assert fake.preview_calls == [{'title': 'Trip', 'start_date': '2025-06-01',
                                       'end_date': '2025-06-07', 'nominal_month': 'June'}]
        assert fake.create_calls == []

    def test_execute_calls_create_event_with_backup_by_default(self, monkeypatch):
        _FakeEventsFile.instances = []
        monkeypatch.setattr(cli, 'EventsMetadataFile', _FakeEventsFile)

        cli.main(['create-event', '--title', 'Trip', '--start-date', '2025-06-01',
                  '--end-date', '2025-06-07', '--execute'])

        fake = _FakeEventsFile.instances[0]
        assert fake.preview_calls == []
        assert fake.create_calls == [{'title': 'Trip', 'start_date': '2025-06-01',
                                      'end_date': '2025-06-07', 'description': None,
                                      'nominal_month': None, 'backup': True}]

    def test_no_backup_flag(self, monkeypatch):
        _FakeEventsFile.instances = []
        monkeypatch.setattr(cli, 'EventsMetadataFile', _FakeEventsFile)

        cli.main(['create-event', '--title', 'Trip', '--start-date', '2025-06-01',
                  '--end-date', '2025-06-07', '--execute', '--no-backup'])

        assert _FakeEventsFile.instances[0].create_calls[0]['backup'] is False


class TestAssignEvent:
    def test_defaults_to_dry_run(self, monkeypatch):
        fake = _fresh_fake_class()
        monkeypatch.setattr(cli, 'AssignEvent', fake)

        cli.main(['assign-event', '--files', 'a.jpg', 'b.jpg', '--event-id', '3'])

        assert fake.instances[0].kwargs == {'dry_run': True}
        assert fake.instances[0].run_calls == [((['a.jpg', 'b.jpg'], 3), {})]

    def test_execute_flag_disables_dry_run(self, monkeypatch):
        fake = _fresh_fake_class()
        monkeypatch.setattr(cli, 'AssignEvent', fake)

        cli.main(['assign-event', '--files', 'a.jpg', '--event-id', '3', '--execute'])

        assert fake.instances[0].kwargs == {'dry_run': False}


class TestSearch:
    def test_passes_all_filters_through(self, monkeypatch):
        fake = _fresh_fake_class()
        monkeypatch.setattr(cli, 'SearchMedia', fake)

        cli.main(['search', '--year', '2024', '2025', '--tags', 'beach,sun',
                  '--people', 'alice', '--title', 'trip', '--comments', 'nice',
                  '--event-id', '3', '--highlight',
                  '--start-date', '2025-06-01', '--end-date', '2025-06-30',
                  '--limit', '10'])

        assert fake.instances[0].run_calls == [((), {
            'years': [2024, 2025], 'tags': 'beach,sun', 'people': 'alice',
            'title': 'trip', 'comments': 'nice', 'event_id': 3,
            'is_highlight': True, 'start_date': '2025-06-01',
            'end_date': '2025-06-30', 'limit': 10})]

    def test_defaults(self, monkeypatch):
        fake = _fresh_fake_class()
        monkeypatch.setattr(cli, 'SearchMedia', fake)

        cli.main(['search'])

        assert fake.instances[0].run_calls == [((), {
            'years': None, 'tags': None, 'people': None, 'title': None,
            'comments': None, 'event_id': None, 'is_highlight': False,
            'start_date': None, 'end_date': None, 'limit': None})]


class TestStats:
    def test_passes_years_through(self, monkeypatch):
        fake = _fresh_fake_class()
        monkeypatch.setattr(cli, 'LibraryStats', fake)

        cli.main(['stats', '--year', '2024', '2025'])

        assert fake.instances[0].args == ()
        assert fake.instances[0].kwargs == {}
        assert fake.instances[0].run_calls == [((), {'years': [2024, 2025]})]

    def test_year_defaults_to_none(self, monkeypatch):
        fake = _fresh_fake_class()
        monkeypatch.setattr(cli, 'LibraryStats', fake)

        cli.main(['stats'])

        assert fake.instances[0].run_calls == [((), {'years': None})]


class TestMemoryLane:
    def test_passes_args_through(self, monkeypatch):
        fake = _fresh_fake_class()
        monkeypatch.setattr(cli, 'MemoryLane', fake)

        cli.main(['memory-lane', '--month', '6', '--day', '15', '--limit', '5'])

        assert fake.instances[0].run_calls == [
            ((), {'month': 6, 'day': 15, 'limit_per_year': 5})]

    def test_defaults(self, monkeypatch):
        fake = _fresh_fake_class()
        monkeypatch.setattr(cli, 'MemoryLane', fake)

        cli.main(['memory-lane'])

        assert fake.instances[0].run_calls == [
            ((), {'month': None, 'day': None, 'limit_per_year': 12})]


class TestHighlightReel:
    def test_passes_args_through(self, monkeypatch):
        fake = _fresh_fake_class()
        monkeypatch.setattr(cli, 'HighlightReel', fake)

        cli.main(['highlight-reel', '--year', '2024', '--limit', '50'])

        assert fake.instances[0].run_calls == [
            ((), {'year': 2024, 'limit': 50})]

    def test_defaults(self, monkeypatch):
        fake = _fresh_fake_class()
        monkeypatch.setattr(cli, 'HighlightReel', fake)

        cli.main(['highlight-reel'])

        assert fake.instances[0].run_calls == [
            ((), {'year': None, 'limit': 100})]


def _fresh_faces_fake():
    class FakeFaces:
        instances = []

        def __init__(self, *args, **kwargs):
            self.calls = []
            FakeFaces.instances.append(self)

        def __getattr__(self, name):
            def rec(*args, **kwargs):
                self.calls.append((name, args, kwargs))
            return rec

    return FakeFaces


class TestFaces:
    def test_scan_passes_args_through(self, monkeypatch):
        fake = _fresh_faces_fake()
        monkeypatch.setattr(cli, 'FaceClustering', fake)

        cli.main(['faces', 'scan', '--years', '2024', '2025',
                  '--eps', '0.4', '--min-samples', '3', '--no-review'])

        assert fake.instances[0].calls == [
            ('scan', (), {'years': [2024, 2025], 'eps': 0.4,
                          'min_samples': 3, 'build_review': False})]

    def test_scan_defaults(self, monkeypatch):
        fake = _fresh_faces_fake()
        monkeypatch.setattr(cli, 'FaceClustering', fake)

        cli.main(['faces', 'scan'])

        assert fake.instances[0].calls == [
            ('scan', (), {'years': None, 'eps': 0.5,
                          'min_samples': 2, 'build_review': True})]

    def test_name(self, monkeypatch):
        fake = _fresh_faces_fake()
        monkeypatch.setattr(cli, 'FaceClustering', fake)

        cli.main(['faces', 'name', '--cluster', '3', '--name', 'Mom'])

        assert fake.instances[0].calls == [('name_cluster', (3, 'Mom'), {})]

    def test_apply_defaults_to_dry_run(self, monkeypatch):
        fake = _fresh_faces_fake()
        monkeypatch.setattr(cli, 'FaceClustering', fake)

        cli.main(['faces', 'apply'])

        assert fake.instances[0].calls == [('apply_names', (), {'dry_run': True})]

    def test_apply_execute(self, monkeypatch):
        fake = _fresh_faces_fake()
        monkeypatch.setattr(cli, 'FaceClustering', fake)

        cli.main(['faces', 'apply', '--execute'])

        assert fake.instances[0].calls == [('apply_names', (), {'dry_run': False})]

    def test_status(self, monkeypatch):
        fake = _fresh_faces_fake()
        monkeypatch.setattr(cli, 'FaceClustering', fake)

        cli.main(['faces', 'status'])

        assert fake.instances[0].calls == [('status', (), {})]
