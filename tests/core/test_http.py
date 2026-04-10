from github2gitea.core.http import parse_next_link


def test_parse_next_link_present():
    header = '<https://api.github.com/repos?page=2>; rel="next", <https://api.github.com/repos?page=5>; rel="last"'
    assert parse_next_link(header) == "https://api.github.com/repos?page=2"


def test_parse_next_link_absent():
    header = '<https://api.github.com/repos?page=4>; rel="prev"'
    assert parse_next_link(header) is None


def test_parse_next_link_empty():
    assert parse_next_link("") is None
    assert parse_next_link(None) is None
