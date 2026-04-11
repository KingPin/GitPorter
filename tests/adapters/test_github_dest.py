import pytest
from unittest.mock import MagicMock, patch
from github2gitea.adapters.github import GitHubAdapter
from github2gitea.adapters.base import Repo

SAMPLE_REPO = Repo(
    name="my-repo",
    clone_url="https://github.com/user/my-repo.git",
    description="A test repo",
    private=False,
    owner="user",
    topics=[],
    language="Python",
    source_type="github",
)


@pytest.fixture
def adapter():
    return GitHubAdapter(config={"token": "fake-token"})


def _make_post_response(status_code=201):
    resp = MagicMock()
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    return resp


def _make_subprocess_result(returncode=0, stderr=b""):
    result = MagicMock()
    result.returncode = returncode
    result.stderr = stderr
    return result


def test_create_mirror_no_dest_org(adapter):
    """create_mirror with no dest_org calls POST /user/repos and returns MIGRATED."""
    post_resp = _make_post_response(201)
    clone_result = _make_subprocess_result(0)
    push_result = _make_subprocess_result(0)

    with patch.object(adapter._session, "post", return_value=post_resp) as mock_post, \
         patch("subprocess.run", side_effect=[clone_result, push_result]) as mock_run, \
         patch("shutil.rmtree"):
        result = adapter.create_mirror(SAMPLE_REPO, dest_org=None)

    assert result.status == "MIGRATED"
    assert result.repo_name == "my-repo"
    call_url = mock_post.call_args[0][0]
    assert call_url.endswith("/user/repos")


def test_create_mirror_with_dest_org(adapter):
    """create_mirror with dest_org calls POST /orgs/{org}/repos and returns MIGRATED."""
    post_resp = _make_post_response(201)
    clone_result = _make_subprocess_result(0)
    push_result = _make_subprocess_result(0)

    with patch.object(adapter._session, "post", return_value=post_resp) as mock_post, \
         patch("subprocess.run", side_effect=[clone_result, push_result]), \
         patch("shutil.rmtree"):
        result = adapter.create_mirror(SAMPLE_REPO, dest_org="my-org")

    assert result.status == "MIGRATED"
    assert result.repo_name == "my-repo"
    call_url = mock_post.call_args[0][0]
    assert "/orgs/my-org/repos" in call_url


def test_create_mirror_subprocess_failure(adapter):
    """subprocess clone failure returns FAILED with error message."""
    post_resp = _make_post_response(201)
    clone_result = _make_subprocess_result(1, b"fatal: repository not found")

    with patch.object(adapter._session, "post", return_value=post_resp), \
         patch("subprocess.run", return_value=clone_result), \
         patch("shutil.rmtree"):
        result = adapter.create_mirror(SAMPLE_REPO)

    assert result.status == "FAILED"
    assert "repository not found" in result.reason


def test_repo_exists_true(adapter):
    """repo_exists returns True when API returns 200."""
    resp = MagicMock()
    resp.status_code = 200
    with patch.object(adapter._session, "get", return_value=resp):
        assert adapter.repo_exists("my-repo", "user") is True


def test_repo_exists_false(adapter):
    """repo_exists returns False when API returns 404."""
    resp = MagicMock()
    resp.status_code = 404
    with patch.object(adapter._session, "get", return_value=resp):
        assert adapter.repo_exists("missing-repo", "user") is False
