from github2gitea.adapters.base import Repo, MigrationResult, BaseAdapter
import pytest

def test_repo_dataclass_defaults():
    repo = Repo(name="my-repo", clone_url="https://github.com/user/my-repo",
                description="test", private=False, owner="user")
    assert repo.topics == []
    assert repo.language == ""
    assert repo.source_type == ""

def test_migration_result_statuses():
    r = MigrationResult(repo_name="my-repo", status="MIGRATED")
    assert r.reason == ""
    r2 = MigrationResult(repo_name="my-repo", status="FAILED", reason="HTTP 500")
    assert r2.reason == "HTTP 500"

def test_base_adapter_cannot_instantiate():
    with pytest.raises(TypeError):
        BaseAdapter()
