"""Tests for GitLabAdapter."""
import pytest
from unittest.mock import MagicMock, patch, call

from gitporter.adapters.gitlab import GitLabAdapter

CONFIG = {"url": "https://gitlab.example.com", "token": "test-token"}

SAMPLE_PROJECT = {
    "path": "my-repo",
    "http_url_to_repo": "https://gitlab.example.com/mygroup/my-repo.git",
    "visibility": "public",
    "namespace": {"path": "mygroup"},
    "description": "A test repo",
    "language": "Python",
    "topics": ["ml", "tool"],
}

PRIVATE_PROJECT = {**SAMPLE_PROJECT, "path": "private-repo", "visibility": "private"}


@pytest.fixture
def adapter():
    return GitLabAdapter(config=CONFIG)


# ---------------------------------------------------------------------------
# Test 1: list_repos org mode with X-Next-Page pagination (two pages)
# ---------------------------------------------------------------------------

def test_list_repos_org_mode_pagination(adapter):
    page1_resp = MagicMock()
    page1_resp.status_code = 200
    page1_resp.json.return_value = [SAMPLE_PROJECT]
    page1_resp.headers = {"X-Next-Page": "2"}

    page2_resp = MagicMock()
    page2_resp.status_code = 200
    page2_resp.json.return_value = [PRIVATE_PROJECT]
    page2_resp.headers = {"X-Next-Page": ""}

    adapter._session.get = MagicMock(side_effect=[page1_resp, page2_resp])

    repos = adapter.list_repos(mode="org", org="mygroup")

    assert len(repos) == 2
    assert repos[0].name == "my-repo"
    assert repos[1].name == "private-repo"

    # Verify both pages were fetched
    calls = adapter._session.get.call_args_list
    assert len(calls) == 2
    # Second call should include page=2
    assert "page=2" in calls[1][0][0]


# ---------------------------------------------------------------------------
# Test 2: list_repos user mode — single page, no next
# ---------------------------------------------------------------------------

def test_list_repos_user_mode_single_page(adapter):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = [SAMPLE_PROJECT]
    resp.headers = {"X-Next-Page": ""}

    adapter._session.get = MagicMock(return_value=resp)

    repos = adapter.list_repos(mode="user", user="alice")

    assert len(repos) == 1
    assert repos[0].name == "my-repo"
    assert repos[0].source_type == "gitlab"
    adapter._session.get.assert_called_once()


# ---------------------------------------------------------------------------
# Test 3: _normalize maps fields correctly
# ---------------------------------------------------------------------------

def test_normalize_maps_fields(adapter):
    repo = adapter._normalize(SAMPLE_PROJECT)
    assert repo.name == "my-repo"
    assert repo.clone_url == "https://gitlab.example.com/mygroup/my-repo.git"
    assert repo.private is False
    assert repo.owner == "mygroup"
    assert repo.description == "A test repo"
    assert repo.language == "Python"
    assert repo.topics == ["ml", "tool"]
    assert repo.source_type == "gitlab"


def test_normalize_private_repo(adapter):
    repo = adapter._normalize(PRIVATE_PROJECT)
    assert repo.private is True


def test_normalize_handles_missing_optional_fields(adapter):
    minimal = {
        "path": "bare",
        "http_url_to_repo": "https://gitlab.example.com/g/bare.git",
        "visibility": "public",
        "namespace": {"path": "g"},
    }
    repo = adapter._normalize(minimal)
    assert repo.description == ""
    assert repo.language == ""
    assert repo.topics == []


# ---------------------------------------------------------------------------
# Test 4: create_mirror calls subprocess, returns MIGRATED
# ---------------------------------------------------------------------------

def test_create_mirror_returns_migrated(adapter):
    from gitporter.adapters.base import Repo

    source_repo = Repo(
        name="my-repo",
        clone_url="https://gitlab.example.com/source/my-repo.git",
        private=False,
        owner="source",
        description="desc",
    )

    post_resp = MagicMock()
    post_resp.status_code = 201
    post_resp.raise_for_status = MagicMock()
    adapter._session.post = MagicMock(return_value=post_resp)

    ok_proc = MagicMock()
    ok_proc.returncode = 0

    with patch("subprocess.run", return_value=ok_proc) as mock_run:
        result = adapter.create_mirror(source_repo, dest_org="destgroup", namespace_id=42)

    assert result.status == "MIGRATED"
    assert result.repo_name == "my-repo"

    # Verify git clone --mirror and git push --mirror were called
    calls = mock_run.call_args_list
    assert any("clone" in str(c) and "--mirror" in str(c) for c in calls)
    assert any("push" in str(c) and "--mirror" in str(c) for c in calls)


def test_create_mirror_returns_skipped_on_409(adapter):
    from gitporter.adapters.base import Repo

    source_repo = Repo(
        name="existing-repo",
        clone_url="https://gitlab.example.com/source/existing-repo.git",
        private=False,
        owner="source",
        description="",
    )

    post_resp = MagicMock()
    post_resp.status_code = 409
    adapter._session.post = MagicMock(return_value=post_resp)

    result = adapter.create_mirror(source_repo, dest_org="destgroup")

    assert result.status == "SKIPPED"
    assert "already exists" in result.reason


# ---------------------------------------------------------------------------
# Test 5: repo_exists — 200 → True, 404 → False
# ---------------------------------------------------------------------------

def test_repo_exists_true(adapter):
    resp = MagicMock()
    resp.status_code = 200
    adapter._session.get = MagicMock(return_value=resp)

    assert adapter.repo_exists("my-repo", "mygroup") is True
    adapter._session.get.assert_called_once()
    url_called = adapter._session.get.call_args[0][0]
    assert "mygroup%2Fmy-repo" in url_called


def test_repo_exists_false(adapter):
    resp = MagicMock()
    resp.status_code = 404
    adapter._session.get = MagicMock(return_value=resp)

    assert adapter.repo_exists("nonexistent", "mygroup") is False


# ---------------------------------------------------------------------------
# Test 6: prepare_destination returns {"namespace_id": ...}
# ---------------------------------------------------------------------------

def test_prepare_destination(adapter):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"id": 99, "name": "mygroup"}
    resp.raise_for_status = MagicMock()
    adapter._session.get = MagicMock(return_value=resp)

    result = adapter.prepare_destination("mygroup")

    assert result == {"namespace_id": 99}
    adapter._session.get.assert_called_once_with(
        "https://gitlab.example.com/api/v4/groups/mygroup"
    )
