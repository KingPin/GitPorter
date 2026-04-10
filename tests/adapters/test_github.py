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
    return GitHubAdapter(token="fake-token")

def test_normalize_repo(adapter):
    repo = adapter._normalize(SAMPLE_REPO_JSON)
    assert repo.name == "my-repo"
    assert repo.private is False
    assert repo.topics == ["python", "tool"]
    assert repo.language == "Python"
    assert repo.source_type == "github"

def test_create_mirror_raises(adapter):
    with pytest.raises(NotImplementedError):
        adapter.create_mirror(MagicMock())

def test_delete_org_raises(adapter):
    with pytest.raises(NotImplementedError):
        adapter.delete_org("some-org")
