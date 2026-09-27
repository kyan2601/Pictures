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
