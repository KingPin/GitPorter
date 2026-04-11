import pytest
from unittest.mock import MagicMock
from github2gitea.adapters.github import GitHubAdapter

SAMPLE_REPO_JSON = {
    "name": "my-repo",
    "clone_url": "https://github.com/user/my-repo.git",
    "description": "A test repo",
    "visibility": "public",
    "private": False,
    "owner": {"login": "user"},
    "topics": ["python", "tool"],
    "language": "Python",
}

@pytest.fixture
def adapter():
    return GitHubAdapter(config={"token": "fake-token"})

def test_normalize_repo(adapter):
    repo = adapter._normalize(SAMPLE_REPO_JSON)
    assert repo.name == "my-repo"
    assert repo.private is False
    assert repo.topics == ["python", "tool"]
    assert repo.language == "Python"
    assert repo.source_type == "github"

def test_delete_org_raises(adapter):
    with pytest.raises(NotImplementedError):
        adapter.delete_org("some-org")

def test_normalize_repo_missing_optional_fields(adapter):
    """_normalize handles None description, None language, missing topics."""
    data = {
        "name": "minimal",
        "clone_url": "https://github.com/user/minimal.git",
        "description": None,
        "visibility": "public",
        "private": False,
        "owner": {"login": "user"},
    }
    repo = adapter._normalize(data)
    assert repo.description == ""
    assert repo.language == ""
    assert repo.topics == []

def test_list_repos_repo_mode_raises(adapter):
    with pytest.raises(ValueError, match="fetch_one_repo"):
        adapter.list_repos(mode="repo", user="user")
