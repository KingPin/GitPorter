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
    return GiteaAdapter(config={"url": "http://gitea:3000", "token": "fake-token"})

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

def test_create_mirror_retries_on_transient_failure(adapter):
    """create_mirror retries on 5xx and succeeds when a later attempt returns 201."""
    responses = [
        MagicMock(status_code=500),
        MagicMock(status_code=201),
    ]
    with patch.object(adapter._session, "post", side_effect=responses):
        with patch("github2gitea.adapters.gitea.time.sleep"):  # don't actually sleep
            result = adapter.create_mirror(SAMPLE_REPO)
    assert result.status == "MIGRATED"


def test_create_mirror_with_lfs(adapter):
    """create_mirror with enable_lfs=True sends 'lfs': True in the POST payload."""
    with patch.object(adapter._session, "post") as mock_post:
        mock_post.return_value.status_code = 201
        adapter.create_mirror(SAMPLE_REPO, enable_lfs=True)
        call_payload = mock_post.call_args[1]["json"]
        assert call_payload["lfs"] is True


def test_prepare_destination_returns_uid_and_calls_ensure_org(adapter):
    """prepare_destination calls ensure_org + get_org_uid and returns the uid dict."""
    with patch.object(adapter, "ensure_org") as mock_ensure, \
         patch.object(adapter, "get_org_uid", return_value=42) as mock_uid:
        result = adapter.prepare_destination("myorg")
    mock_ensure.assert_called_once_with("myorg", visibility="public")
    mock_uid.assert_called_once_with("myorg")
    assert result["uid"] == 42
    assert "auth_username" in result
    assert "auth_token" in result
