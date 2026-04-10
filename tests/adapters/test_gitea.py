import pytest
from unittest.mock import MagicMock, patch
from github2gitea.adapters.gitea import GiteaAdapter
from github2gitea.adapters.base import Repo

SAMPLE_REPO = Repo(
    name="my-repo", clone_url="https://github.com/user/my-repo.git",
    description="A test repo", private=False, owner="user", source_type="github",
)

@pytest.fixture
def adapter():
    return GiteaAdapter(url="http://gitea:3000", token="fake-token")

def test_repo_exists_true(adapter):
    with patch.object(adapter._session, "get") as mock_get:
        mock_get.return_value.status_code = 200
        assert adapter.repo_exists("my-repo", "user") is True

def test_repo_exists_false(adapter):
    with patch.object(adapter._session, "get") as mock_get:
        mock_get.return_value.status_code = 404
        assert adapter.repo_exists("my-repo", "user") is False

def test_create_mirror_success(adapter):
    with patch.object(adapter._session, "post") as mock_post:
        mock_post.return_value.status_code = 201
        result = adapter.create_mirror(SAMPLE_REPO)
        assert result.status == "MIGRATED"

def test_create_mirror_already_exists(adapter):
    with patch.object(adapter._session, "post") as mock_post:
        mock_post.return_value.status_code = 409
        result = adapter.create_mirror(SAMPLE_REPO)
        assert result.status == "SKIPPED"
        assert "already exists" in result.reason

def test_create_mirror_422_allowed_domains(adapter):
    with patch.object(adapter._session, "post") as mock_post:
        mock_post.return_value.status_code = 422
        result = adapter.create_mirror(SAMPLE_REPO)
        assert result.status == "FAILED"
        assert "ALLOWED_DOMAINS" in result.reason
