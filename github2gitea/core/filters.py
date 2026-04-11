import fnmatch
from github2gitea.adapters.base import Repo


def apply_filters(
    repos: list[Repo],
    name_pattern: str | None = None,
    language: str | None = None,
    topic: str | None = None,
    ignore_names: list[str] | None = None,
) -> list[Repo]:
    """Filter repos by name glob, language, and/or topic. All supplied filters are ANDed."""
    result = repos
    if ignore_names:
        result = [r for r in result if r.name not in ignore_names]
    if name_pattern:
        result = [r for r in result if fnmatch.fnmatch(r.name, name_pattern)]
    if language:
        lang = language.lower()
        result = [r for r in result if (r.language or "").lower() == lang]
    if topic:
        result = [r for r in result if topic in r.topics]
    return result
