"""Tests for BitbucketAdapter."""
import pytest
from unittest.mock import MagicMock

from github2gitea.adapters.bitbucket import BitbucketAdapter

CONFIG = {
    "workspace": "myworkspace",
    "username": "testuser",
    "app_password": "secret",
}

SAMPLE_REPO = {
    "full_name": "myworkspace/my-repo",
    "is_private": False,
    "description": "A test repo",
    "language": "python",
    "links": {
        "clone": [
            {"name": "https", "href": "https://bitbucket.org/myworkspace/my-repo.git"},
            {"name": "ssh", "href": "git@bitbucket.org:myworkspace/my-repo.git"},
        ]
    },
}

PRIVATE_REPO = {
    "full_name": "myworkspace/private-repo",
    "is_private": True,
    "description": "",
    "language": "",
    "links": {
        "clone": [
            {"name": "https", "href": "https://bitbucket.org/myworkspace/private-repo.git"},
            {"name": "ssh", "href": "git@bitbucket.org:myworkspace/private-repo.git"},
        ]
    },
}


@pytest.fixture
def adapter():
    return BitbucketAdapter(config=CONFIG)


# ---------------------------------------------------------------------------
# Test 1: list_repos org mode with JSON next pagination (two pages)
# ---------------------------------------------------------------------------

def test_list_repos_org_mode_pagination(adapter):
    page1_url = "https://api.bitbucket.org/2.0/repositories/myworkspace"
    page2_url = "https://api.bitbucket.org/2.0/repositories/myworkspace?page=2"

    page1_resp = MagicMock()
    page1_resp.status_code = 200
    page1_resp.json.return_value = {"values": [SAMPLE_REPO], "next": page2_url}

    page2_resp = MagicMock()
    page2_resp.status_code = 200
    page2_resp.json.return_value = {"values": [PRIVATE_REPO]}  # no "next" key

    adapter._session.get = MagicMock(side_effect=[page1_resp, page2_resp])

    repos = adapter.list_repos(mode="org", org="myworkspace")

    assert len(repos) == 2
    assert repos[0].name == "my-repo"
    assert repos[1].name == "private-repo"

    calls = adapter._session.get.call_args_list
    assert len(calls) == 2
    assert calls[0][0][0] == page1_url
    assert calls[1][0][0] == page2_url


# ---------------------------------------------------------------------------
# Test 2: _normalize maps fields correctly including clone URL extraction
# ---------------------------------------------------------------------------

def test_normalize_maps_fields(adapter):
    repo = adapter._normalize(SAMPLE_REPO)
    assert repo.name == "my-repo"
    assert repo.clone_url == "https://bitbucket.org/myworkspace/my-repo.git"
    assert repo.private is False
    assert repo.owner == "myworkspace"
    assert repo.description == "A test repo"
    assert repo.language == "python"
    assert repo.topics == []
    assert repo.source_type == "bitbucket"


def test_normalize_private_repo(adapter):
    repo = adapter._normalize(PRIVATE_REPO)
    assert repo.private is True
    assert repo.description == ""
    assert repo.language == ""


def test_normalize_selects_https_clone_url(adapter):
    """Ensure https clone URL is picked, not SSH."""
    repo = adapter._normalize(SAMPLE_REPO)
    assert repo.clone_url.startswith("https://")
    assert "git@" not in repo.clone_url


# ---------------------------------------------------------------------------
# Test 3: create_mirror raises NotImplementedError
# ---------------------------------------------------------------------------

def test_create_mirror_raises(adapter):
    from github2gitea.adapters.base import Repo

    source_repo = Repo(
        name="my-repo",
        clone_url="https://bitbucket.org/myworkspace/my-repo.git",
        private=False,
        owner="myworkspace",
        description="",
    )

    with pytest.raises(NotImplementedError, match="does not support mirror creation"):
        adapter.create_mirror(source_repo)


# ---------------------------------------------------------------------------
# Test 4: list_repos star mode raises ValueError
# ---------------------------------------------------------------------------

def test_list_repos_star_mode_raises(adapter):
    with pytest.raises(ValueError, match="does not support star mode"):
        adapter.list_repos(mode="star", user="alice")


# ---------------------------------------------------------------------------
# Test 5: repo_exists — 200 → True, 404 → False
# ---------------------------------------------------------------------------

def test_repo_exists_true(adapter):
    resp = MagicMock()
    resp.status_code = 200
    adapter._session.get = MagicMock(return_value=resp)

    assert adapter.repo_exists("my-repo", "myworkspace") is True
    adapter._session.get.assert_called_once_with(
        "https://api.bitbucket.org/2.0/repositories/myworkspace/my-repo"
    )


def test_repo_exists_false(adapter):
    resp = MagicMock()
    resp.status_code = 404
    adapter._session.get = MagicMock(return_value=resp)

    assert adapter.repo_exists("nonexistent", "myworkspace") is False
