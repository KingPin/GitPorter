import pytest

from gitporter.adapters import get_adapter, VALID_PLATFORMS
from gitporter.adapters.github    import GitHubAdapter
from gitporter.adapters.gitea     import GiteaAdapter
from gitporter.adapters.gitlab    import GitLabAdapter
from gitporter.adapters.bitbucket import BitbucketAdapter
from gitporter.adapters.forgejo   import ForgejoAdapter


def test_unknown_platform_raises_value_error():
    with pytest.raises(ValueError, match="Unknown platform"):
        get_adapter("nonexistent", {})


def test_unknown_platform_message_lists_choices():
    with pytest.raises(ValueError, match="Choices:"):
        get_adapter("nonexistent", {})


def test_get_adapter_github():
    adapter = get_adapter("github", {"url": "https://api.github.com", "token": ""})
    assert isinstance(adapter, GitHubAdapter)


def test_get_adapter_gitea():
    adapter = get_adapter("gitea", {"url": "https://gitea.example.com", "token": ""})
    assert isinstance(adapter, GiteaAdapter)


def test_get_adapter_gitlab():
    adapter = get_adapter("gitlab", {"url": "https://gitlab.com", "token": ""})
    assert isinstance(adapter, GitLabAdapter)


def test_get_adapter_bitbucket():
    adapter = get_adapter(
        "bitbucket",
        {"workspace": "ws", "username": "u", "app_password": "p"},
    )
    assert isinstance(adapter, BitbucketAdapter)


def test_get_adapter_forgejo():
    adapter = get_adapter("forgejo", {"url": "https://forgejo.example.com", "token": ""})
    assert isinstance(adapter, ForgejoAdapter)


def test_valid_platforms_contains_all_five():
    assert set(VALID_PLATFORMS) == {"github", "gitea", "gitlab", "bitbucket", "forgejo"}
