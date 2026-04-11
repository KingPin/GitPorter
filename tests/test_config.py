"""Tests for github2gitea/config.py"""
import pytest

from github2gitea.config import load_platform_config


# ---------------------------------------------------------------------------
# 1. Missing required vars → SystemExit(1) with helpful message
# ---------------------------------------------------------------------------

def test_gitea_missing_url_raises(monkeypatch):
    monkeypatch.delenv("GITEA_URL", raising=False)
    monkeypatch.delenv("GITEA_TOKEN", raising=False)
    monkeypatch.delenv("ACCESS_TOKEN", raising=False)
    with pytest.raises(SystemExit) as exc:
        load_platform_config("gitea")
    assert exc.value.code == 1


def test_gitlab_missing_vars_raises(monkeypatch):
    monkeypatch.delenv("GITLAB_URL", raising=False)
    monkeypatch.delenv("GITLAB_TOKEN", raising=False)
    with pytest.raises(SystemExit) as exc:
        load_platform_config("gitlab")
    assert exc.value.code == 1


def test_bitbucket_missing_vars_raises(monkeypatch):
    monkeypatch.delenv("BITBUCKET_WORKSPACE", raising=False)
    monkeypatch.delenv("BITBUCKET_USERNAME", raising=False)
    monkeypatch.delenv("BITBUCKET_APP_PASSWORD", raising=False)
    with pytest.raises(SystemExit) as exc:
        load_platform_config("bitbucket")
    assert exc.value.code == 1


def test_forgejo_missing_vars_raises(monkeypatch):
    monkeypatch.delenv("FORGEJO_URL", raising=False)
    monkeypatch.delenv("FORGEJO_TOKEN", raising=False)
    with pytest.raises(SystemExit) as exc:
        load_platform_config("forgejo")
    assert exc.value.code == 1


# ---------------------------------------------------------------------------
# 2. ACCESS_TOKEN fallback when GITEA_TOKEN absent
# ---------------------------------------------------------------------------

def test_gitea_access_token_fallback(monkeypatch):
    monkeypatch.setenv("GITEA_URL", "https://gitea.example.com")
    monkeypatch.delenv("GITEA_TOKEN", raising=False)
    monkeypatch.setenv("ACCESS_TOKEN", "fallback-token")
    cfg = load_platform_config("gitea")
    assert cfg["token"] == "fallback-token"


# ---------------------------------------------------------------------------
# 3. GITEA_TOKEN takes priority over ACCESS_TOKEN
# ---------------------------------------------------------------------------

def test_gitea_token_priority(monkeypatch):
    monkeypatch.setenv("GITEA_URL", "https://gitea.example.com")
    monkeypatch.setenv("GITEA_TOKEN", "primary-token")
    monkeypatch.setenv("ACCESS_TOKEN", "fallback-token")
    cfg = load_platform_config("gitea")
    assert cfg["token"] == "primary-token"


# ---------------------------------------------------------------------------
# 4. Unknown platform raises SystemExit(1)
# ---------------------------------------------------------------------------

def test_unknown_platform_raises():
    with pytest.raises(SystemExit) as exc:
        load_platform_config("notaplatform")
    assert exc.value.code == 1


# ---------------------------------------------------------------------------
# 5. All platforms return correct normalized dict keys
# ---------------------------------------------------------------------------

def test_github_normalized_keys(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "gh-token")
    cfg = load_platform_config("github")
    assert set(cfg.keys()) == {"url", "token"}
    assert cfg["url"] == "https://api.github.com"
    assert cfg["token"] == "gh-token"


def test_github_no_token_defaults_empty(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    cfg = load_platform_config("github")
    assert cfg["token"] == ""
    assert cfg["url"] == "https://api.github.com"


def test_gitea_normalized_keys(monkeypatch):
    monkeypatch.setenv("GITEA_URL", "https://gitea.example.com")
    monkeypatch.setenv("GITEA_TOKEN", "gt-token")
    monkeypatch.delenv("ACCESS_TOKEN", raising=False)
    cfg = load_platform_config("gitea")
    assert set(cfg.keys()) == {"url", "token"}
    assert cfg["url"] == "https://gitea.example.com"
    assert cfg["token"] == "gt-token"


def test_gitlab_normalized_keys(monkeypatch):
    monkeypatch.setenv("GITLAB_URL", "https://gitlab.example.com")
    monkeypatch.setenv("GITLAB_TOKEN", "gl-token")
    cfg = load_platform_config("gitlab")
    assert set(cfg.keys()) == {"url", "token"}
    assert cfg["url"] == "https://gitlab.example.com"
    assert cfg["token"] == "gl-token"


def test_bitbucket_normalized_keys(monkeypatch):
    monkeypatch.setenv("BITBUCKET_WORKSPACE", "myworkspace")
    monkeypatch.setenv("BITBUCKET_USERNAME", "myuser")
    monkeypatch.setenv("BITBUCKET_APP_PASSWORD", "mypassword")
    cfg = load_platform_config("bitbucket")
    assert set(cfg.keys()) == {"workspace", "username", "app_password"}
    assert cfg["workspace"] == "myworkspace"
    assert cfg["username"] == "myuser"
    assert cfg["app_password"] == "mypassword"


def test_forgejo_normalized_keys(monkeypatch):
    monkeypatch.setenv("FORGEJO_URL", "https://forgejo.example.com")
    monkeypatch.setenv("FORGEJO_TOKEN", "fj-token")
    cfg = load_platform_config("forgejo")
    assert set(cfg.keys()) == {"url", "token"}
    assert cfg["url"] == "https://forgejo.example.com"
    assert cfg["token"] == "fj-token"
