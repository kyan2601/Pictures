from src import cli, helper


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
    def test_defaults_to_dry_run(self, monkeypatch):
        fake = _fresh_fake_class()
        monkeypatch.setattr(cli, 'ProcessNewMedia', fake)

        cli.main(['process-new'])

        assert len(fake.instances) == 1
        assert fake.instances[0].kwargs == {'dry_run': True}
        assert fake.instances[0].run_calls == [((), {})]

    def test_execute_flag_disables_dry_run(self, monkeypatch):
        fake = _fresh_fake_class()
        monkeypatch.setattr(cli, 'ProcessNewMedia', fake)

        cli.main(['process-new', '--execute'])

        assert fake.instances[0].kwargs == {'dry_run': False}


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
