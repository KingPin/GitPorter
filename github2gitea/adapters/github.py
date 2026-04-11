import logging
import time
import requests
from .base import BaseAdapter, Repo, MigrationResult
from ..core.http import parse_next_link, http_get_with_backoff

logger = logging.getLogger(__name__)
GITHUB_API = "https://api.github.com"


class GitHubAdapter(BaseAdapter):
    def __init__(self, token: str | None = None, api_delay: float = 2.0):
        self._session = requests.Session()
        if token:
            self._session.headers["Authorization"] = f"Bearer {token}"
        self._session.headers["Accept"] = "application/vnd.github+json"
        self._api_delay = api_delay

    def list_repos(self, mode: str, user: str | None = None, org: str | None = None) -> list[Repo]:
        """Return all repos for the given mode. Handles pagination internally."""
        if mode == "org":
            return self._paginate(f"{GITHUB_API}/orgs/{org}/repos")
        elif mode == "user":
            if "Authorization" in self._session.headers:
                # Authenticated: always use the /user/repos endpoint so that
                # destination org does not accidentally change which repos are fetched.
                return self._paginate(f"{GITHUB_API}/user/repos", params={"affiliation": "owner"})
            else:
                # Unauthenticated: fall back to the public endpoint (public repos only).
                if not user:
                    raise ValueError("--user is required for unauthenticated user-mode listing")
                return self._paginate(f"{GITHUB_API}/users/{user}/repos")
        elif mode == "star":
            return self._paginate(f"{GITHUB_API}/users/{user}/starred")
        elif mode == "repo":
            raise ValueError("Use fetch_one_repo() for single-repo mode")
        else:
            raise ValueError(f"Unknown mode: {mode}")

    def fetch_one_repo(self, repo_url: str) -> Repo:
        """Fetch a single repo by its GitHub URL."""
        path = repo_url.replace("https://github.com/", "").removesuffix(".git")
        r = http_get_with_backoff(self._session, f"{GITHUB_API}/repos/{path}")
        return self._normalize(r.json())

    def repo_exists(self, repo_name: str, owner: str) -> bool:
        """Return True if repo exists on GitHub."""
        r = self._session.get(f"{GITHUB_API}/repos/{owner}/{repo_name}")
        return r.status_code == 200

    def create_mirror(self, repo: Repo, dest_org: str | None = None,
                      uid: int | None = None, auth_username: str | None = None,
                      auth_token: str | None = None, **kwargs) -> MigrationResult:
        raise NotImplementedError("GitHub as mirror destination is not yet supported")

    def delete_org(self, org: str, force: bool = False, dry_run: bool = False) -> None:
        raise NotImplementedError("GitHub org deletion is not supported")

    def _paginate(self, url: str, params: dict | None = None) -> list[Repo]:
        repos = []
        params = {**(params or {}), "per_page": 100}
        first_page = True
        while url:
            if not first_page:
                time.sleep(self._api_delay)
            response = http_get_with_backoff(self._session, url, params=params)
            data = response.json()
            if not data:
                break
            repos.extend(self._normalize(r) for r in data)
            url = parse_next_link(response.headers.get("Link"))
            params = {}  # next URL already encodes params
            first_page = False
        return repos

    def _normalize(self, data: dict) -> Repo:
        return Repo(
            name=data["name"],
            clone_url=data["clone_url"],
            description=(data.get("description") or "")[:255],
            private=data.get("visibility") == "private" or data.get("private", False),
            owner=data["owner"]["login"],
            topics=data.get("topics", []),
            language=data.get("language") or "",
            source_type="github",
        )
