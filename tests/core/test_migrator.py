from unittest.mock import MagicMock
from github2gitea.core.migrator import Migrator
from github2gitea.adapters.base import Repo, MigrationResult

def make_repo(name, language="Python"):
    return Repo(name=name, clone_url=f"https://github.com/user/{name}.git",
                description="", private=False, owner="user",
                topics=[], language=language, source_type="github")

def make_source(*names):
    m = MagicMock()
    m.list_repos.return_value = [make_repo(n) for n in names]
    return m

def make_dest(existing=None):
    m = MagicMock()
    existing = existing or []
    m.repo_exists.side_effect = lambda name, owner: name in existing
    m.create_mirror.side_effect = lambda repo, **kw: MigrationResult(repo.name, "MIGRATED")
    m.prepare_destination.return_value = {}
    return m

def test_dry_run_skips_migration():
    migrator = Migrator(make_source("a", "b"), make_dest(), dry_run=True)
    results = migrator.run(mode="user", user="user")
    assert all(r.status == "SKIPPED" for r in results)
    assert all("dry run" in r.reason for r in results)

def test_existing_repos_skipped():
    migrator = Migrator(make_source("a", "b", "c"), make_dest(existing=["a"]))
    results = migrator.run(mode="user", user="user")
    assert len([r for r in results if r.status == "SKIPPED"]) == 1
    assert len([r for r in results if r.status == "MIGRATED"]) == 2

def test_language_filter_applied():
    source = MagicMock()
    source.list_repos.return_value = [make_repo("py-repo", "Python"), make_repo("go-repo", "Go")]
    migrator = Migrator(source, make_dest(), language="go")
    results = migrator.run(mode="user", user="user")
    assert len(results) == 1
    assert results[0].repo_name == "go-repo"

def test_repo_mode_calls_fetch_one_repo():
    source = MagicMock()
    repo = make_repo("my-repo")
    source.fetch_one_repo.return_value = repo
    dest = make_dest()
    migrator = Migrator(source, dest)
    results = migrator.run(mode="repo", repo_url="https://github.com/user/my-repo.git")
    source.fetch_one_repo.assert_called_once_with("https://github.com/user/my-repo.git")
    source.list_repos.assert_not_called()
    assert len(results) == 1
    assert results[0].repo_name == "my-repo"
