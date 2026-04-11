import logging

import requests

from .base import BaseAdapter, MigrationResult, Repo

logger = logging.getLogger(__name__)


class BitbucketAdapter(BaseAdapter):
    """Bitbucket Cloud source adapter (source only — no mirror creation API)."""

    platform_name = "bitbucket"

    def __init__(self, config: dict):
        self._workspace = config["workspace"]
        self._session = requests.Session()
        self._session.auth = (config["username"], config["app_password"])

    # ------------------------------------------------------------------
    # Source: list repos
    # ------------------------------------------------------------------

    def list_repos(self, mode: str, user: str | None = None, org: str | None = None) -> list[Repo]:
        if mode == "star":
            raise ValueError("Bitbucket Cloud does not support star mode")

        if mode == "user":
            workspace = self._workspace
        elif mode == "org":
            workspace = org if org else self._workspace
        else:
            raise ValueError(f"Unknown mode: {mode}")

        url: str | None = f"https://api.bitbucket.org/2.0/repositories/{workspace}"
        all_repos: list[dict] = []
        while url:
            resp = self._session.get(url)
            resp.raise_for_status()
            data = resp.json()
            all_repos.extend(data.get("values", []))
            url = data.get("next")

        return [self._normalize(r) for r in all_repos]

    # ------------------------------------------------------------------
    # Source: single repo
    # ------------------------------------------------------------------

    def fetch_one_repo(self, repo_url: str) -> Repo:
        # https://bitbucket.org/workspace/slug  →  slug
        parts = repo_url.rstrip("/").split("/")
        slug = parts[-1]
        workspace = parts[-2]
        resp = self._session.get(
            f"https://api.bitbucket.org/2.0/repositories/{workspace}/{slug}"
        )
        resp.raise_for_status()
        return self._normalize(resp.json())

    # ------------------------------------------------------------------
    # Destination (not supported): existence check only
    # ------------------------------------------------------------------

    def repo_exists(self, repo_name: str, owner: str) -> bool:
        resp = self._session.get(
            f"https://api.bitbucket.org/2.0/repositories/{owner}/{repo_name}"
        )
        return resp.status_code == 200

    def create_mirror(self, repo: Repo, dest_org: str | None = None, **kwargs) -> MigrationResult:
        raise NotImplementedError("Bitbucket Cloud does not support mirror creation")

    def delete_org(self, org: str, **kwargs) -> None:
        raise NotImplementedError("Bitbucket Cloud does not support org deletion")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _normalize(self, repo: dict) -> Repo:
        full_name = repo["full_name"]
        owner, name = full_name.split("/", 1)
        clone_url = next(
            link["href"]
            for link in repo["links"]["clone"]
            if link["name"] == "https"
        )
        return Repo(
            name=name,
            clone_url=clone_url,
            private=repo["is_private"],
            owner=owner,
            description=repo.get("description", "") or "",
            language=repo.get("language", "") or "",
            topics=[],
            source_type="bitbucket",
        )
