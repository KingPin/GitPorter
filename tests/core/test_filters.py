import pytest
from github2gitea.core.filters import apply_filters
from github2gitea.adapters.base import Repo

def make_repo(**kwargs):
    defaults = dict(name="repo", clone_url="", description="", private=False,
                    owner="user", topics=[], language="", source_type="github")
    return Repo(**{**defaults, **kwargs})

def test_filter_by_name_glob():
    repos = [make_repo(name="foo-service"), make_repo(name="bar-service"), make_repo(name="infra")]
    result = apply_filters(repos, name_pattern="*-service")
    assert [r.name for r in result] == ["foo-service", "bar-service"]

def test_filter_by_language_case_insensitive():
    repos = [make_repo(language="Python"), make_repo(language="Go"), make_repo(language="Python")]
    result = apply_filters(repos, language="python")
    assert len(result) == 2

def test_filter_by_topic():
    repos = [make_repo(topics=["ml", "python"]), make_repo(topics=["web"]), make_repo(topics=["ml"])]
    result = apply_filters(repos, topic="ml")
    assert len(result) == 2

def test_multiple_filters_are_anded():
    repos = [
        make_repo(name="ml-service", language="Python", topics=["ml"]),
        make_repo(name="ml-service", language="Go", topics=["ml"]),
    ]
    result = apply_filters(repos, name_pattern="ml-*", language="python")
    assert len(result) == 1

def test_no_filters_returns_all():
    repos = [make_repo(), make_repo(name="other")]
    assert apply_filters(repos) == repos
