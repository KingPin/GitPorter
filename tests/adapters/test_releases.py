"""Tests for releases mirroring: GitHub fetch_releases and Gitea mirror_releases."""
import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_github_adapter(session=None, api_delay=0.0):
    from github2gitea.adapters.github import GitHubAdapter
    adapter = GitHubAdapter(config={"token": "tok"}, api_delay=api_delay)
    if session is not None:
        adapter._session = session
    return adapter


def _make_gitea_adapter(session=None):
    from github2gitea.adapters.gitea import GiteaAdapter
    adapter = GiteaAdapter(config={"url": "http://gitea.test", "token": "tok"})
    if session is not None:
        adapter._session = session
    return adapter


def _mock_response(json_data, status_code=200, headers=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.ok = status_code < 400
    resp.json.return_value = json_data
    resp.headers = headers or {}
    resp.raise_for_status = MagicMock()
    resp.text = str(json_data)
    return resp


# ---------------------------------------------------------------------------
# GitHub fetch_releases
# ---------------------------------------------------------------------------

def test_github_fetch_releases_single_page():
    """fetch_releases returns list from a single page response."""
    releases = [{"tag_name": "v1.0", "name": "v1.0", "body": "first", "draft": False, "prerelease": False, "assets": []}]
    session = MagicMock()
    session.get.return_value = _mock_response(releases)
    adapter = _make_github_adapter(session)

    result = adapter.fetch_releases("owner", "myrepo")

    assert result == releases
    session.get.assert_called_once_with("https://api.github.com/repos/owner/myrepo/releases")


def test_github_fetch_releases_pagination():
    """fetch_releases follows Link header to fetch all pages."""
    page1 = [{"tag_name": "v1.0", "assets": []}]
    page2 = [{"tag_name": "v2.0", "assets": []}]

    resp1 = _mock_response(page1, headers={"Link": '<https://api.github.com/repos/owner/myrepo/releases?page=2>; rel="next"'})
    resp2 = _mock_response(page2, headers={})

    session = MagicMock()
    session.get.side_effect = [resp1, resp2]
    adapter = _make_github_adapter(session, api_delay=0.0)

    result = adapter.fetch_releases("owner", "myrepo")

    assert len(result) == 2
    assert result[0]["tag_name"] == "v1.0"
    assert result[1]["tag_name"] == "v2.0"
    assert session.get.call_count == 2


# ---------------------------------------------------------------------------
# Gitea mirror_releases
# ---------------------------------------------------------------------------

def test_gitea_mirror_releases_creates_release():
    """mirror_releases POSTs a new release when tag is not already present."""
    existing_resp = _mock_response([])  # no existing releases
    create_resp = _mock_response({"id": 42, "tag_name": "v1.0"}, status_code=201)

    session = MagicMock()
    session.get.return_value = existing_resp
    session.post.return_value = create_resp

    adapter = _make_gitea_adapter(session)
    releases = [{"tag_name": "v1.0", "name": "Release 1", "body": "Notes", "draft": False, "prerelease": False, "assets": []}]

    adapter.mirror_releases("myrepo", "myorg", releases)

    session.post.assert_called_once()
    call_kwargs = session.post.call_args
    assert "v1.0" in str(call_kwargs)


def test_gitea_mirror_releases_skips_existing_tag():
    """mirror_releases skips a release if the tag already exists in Gitea."""
    existing_resp = _mock_response([{"tag_name": "v1.0", "id": 1}])
    empty_resp = _mock_response([])  # pagination terminator

    session = MagicMock()
    session.get.side_effect = [existing_resp, empty_resp]

    adapter = _make_gitea_adapter(session)
    releases = [{"tag_name": "v1.0", "name": "Release 1", "body": "", "draft": False, "prerelease": False, "assets": []}]

    adapter.mirror_releases("myrepo", "myorg", releases)

    # POST should NOT be called since tag already exists
    session.post.assert_not_called()


def test_gitea_mirror_releases_uploads_asset():
    """mirror_releases uploads assets for a newly created release."""
    existing_resp = _mock_response([])  # empty → pagination breaks immediately
    create_resp = _mock_response({"id": 99, "tag_name": "v1.0"}, status_code=201)
    upload_resp = _mock_response({"id": 1}, status_code=201)

    asset_download_resp = MagicMock()
    asset_download_resp.ok = True
    asset_download_resp.content = b"binary data"

    session = MagicMock()
    session.get.return_value = existing_resp  # always returns [] so pagination terminates
    session.post.side_effect = [create_resp, upload_resp]

    adapter = _make_gitea_adapter(session)

    releases = [{
        "tag_name": "v1.0",
        "name": "v1.0",
        "body": "",
        "draft": False,
        "prerelease": False,
        "assets": [{"name": "binary.zip", "browser_download_url": "https://cdn.example.com/binary.zip"}],
    }]

    with patch("requests.get", return_value=asset_download_resp):
        adapter.mirror_releases("myrepo", "myorg", releases)

    assert session.post.call_count == 2
    upload_call = session.post.call_args_list[1]
    assert "assets" in upload_call[0][0]
    assert upload_call[1]["params"] == {"name": "binary.zip"}
