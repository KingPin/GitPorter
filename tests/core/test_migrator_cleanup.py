from unittest.mock import MagicMock, call
from github2gitea.core.migrator import Migrator
from github2gitea.adapters.base import Repo, MigrationResult


def make_repo(name, language="Python"):
    return Repo(
        name=name,
        clone_url=f"https://github.com/user/{name}.git",
        description="",
        private=False,
        owner="user",
        topics=[],
        language=language,
        source_type="github",
    )


def make_source(*names):
    m = MagicMock()
    m.list_repos.return_value = [make_repo(n) for n in names]
    return m


def make_dest(existing=None, dest_repos=None):
    m = MagicMock()
    existing = existing or []
    dest_repos = dest_repos or []
    m.repo_exists.side_effect = lambda name, owner: name in existing
    m.create_mirror.side_effect = lambda repo, **kw: MigrationResult(repo.name, "MIGRATED")
    m.prepare_destination.return_value = {}
    m.list_dest_repos.return_value = dest_repos
    return m


def test_cleanup_archives_orphans():
    """After migration, repos in dest that are NOT in source are archived."""
    source = make_source("repo-a", "repo-b")
    dest = make_dest(dest_repos=["repo-a", "repo-b", "orphan-1", "orphan-2"])
    migrator = Migrator(
        source=source, dest=dest,
        dest_org="myorg", cleanup_action="archive",
    )
    migrator.run(mode="org", org="myorg")

    dest.list_dest_repos.assert_called_once_with("myorg")
    dest.archive_repo.assert_any_call("orphan-1", "myorg")
    dest.archive_repo.assert_any_call("orphan-2", "myorg")
    assert dest.archive_repo.call_count == 2
    dest.delete_repo.assert_not_called()


def test_cleanup_deletes_orphans():
    """With cleanup_action='delete', orphaned dest repos are deleted."""
    source = make_source("repo-a")
    dest = make_dest(dest_repos=["repo-a", "old-repo"])
    migrator = Migrator(
        source=source, dest=dest,
        dest_org="myorg", cleanup_action="delete",
    )
    migrator.run(mode="org", org="myorg")

    dest.list_dest_repos.assert_called_once_with("myorg")
    dest.delete_repo.assert_called_once_with("old-repo", "myorg")
    dest.archive_repo.assert_not_called()


def test_cleanup_skipped_in_dry_run():
    """When dry_run=True, no archive or delete calls are made."""
    source = make_source("repo-a")
    dest = make_dest(dest_repos=["repo-a", "orphan"])
    migrator = Migrator(
        source=source, dest=dest,
        dest_org="myorg", cleanup_action="archive", dry_run=True,
    )
    migrator.run(mode="org", org="myorg")

    dest.list_dest_repos.assert_not_called()
    dest.archive_repo.assert_not_called()
    dest.delete_repo.assert_not_called()


def test_cleanup_only_runs_when_dest_org_set():
    """Without dest_org, cleanup phase is skipped entirely."""
    source = make_source("repo-a")
    dest = make_dest(dest_repos=["repo-a", "orphan"])
    migrator = Migrator(
        source=source, dest=dest,
        dest_org=None, cleanup_action="archive",
    )
    migrator.run(mode="user", user="someuser")

    dest.list_dest_repos.assert_not_called()
    dest.archive_repo.assert_not_called()
    dest.delete_repo.assert_not_called()


def test_cleanup_uses_pre_filter_source_names():
    """Repos filtered OUT from migration must not be treated as orphans in dest."""
    # Source has python-repo and go-repo; we filter to python only.
    # Dest has both. Without pre-filter names, go-repo would look like an orphan.
    source = MagicMock()
    source.list_repos.return_value = [
        make_repo("python-repo", "Python"),
        make_repo("go-repo", "Go"),
    ]
    dest = make_dest(dest_repos=["python-repo", "go-repo"])
    migrator = Migrator(
        source=source, dest=dest,
        dest_org="myorg", cleanup_action="delete",
        language="python",  # filter out go-repo
    )
    migrator.run(mode="org", org="myorg")

    # go-repo is in source (pre-filter), so it must NOT be deleted
    dest.list_dest_repos.assert_called_once_with("myorg")
    dest.delete_repo.assert_not_called()
