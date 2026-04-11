import logging
import time
import requests
from .base import BaseAdapter, Repo, MigrationResult
from ..core.http import parse_next_link

logger = logging.getLogger(__name__)


class GiteaAdapter(BaseAdapter):
    platform_name = "gitea"

    def __init__(self, config: dict, api_delay: float = 1.0):
        self._url = config["url"].rstrip("/")
        self._token = config["token"]
        self._api_delay = api_delay
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        })

    def list_repos(self, mode: str, user: str | None = None, org: str | None = None) -> list[Repo]:
        """Return repos from Gitea (for use as a source adapter)."""
        if mode == "org":
            return self._paginate(f"{self._url}/api/v1/orgs/{org}/repos")
        elif mode == "user":
            return self._paginate(f"{self._url}/api/v1/users/{user}/repos")
        else:
            raise ValueError(f"Unsupported mode for Gitea source: {mode}")

    def repo_exists(self, repo_name: str, owner: str) -> bool:
        """Return True if the repo already exists in Gitea."""
        r = self._session.get(f"{self._url}/api/v1/repos/{owner}/{repo_name}")
        return r.status_code == 200

    def get_org_uid(self, org: str) -> int:
        """Return the numeric uid of a Gitea organization."""
        r = self._session.get(f"{self._url}/api/v1/orgs/{org}")
        r.raise_for_status()
        return r.json()["id"]

    def get_user_uid(self, username: str) -> int:
        """Return the numeric uid of a Gitea user."""
        r = self._session.get(f"{self._url}/api/v1/users/{username}")
        r.raise_for_status()
        return r.json()["id"]

    def ensure_org(self, org: str, visibility: str = "public") -> None:
        """Create org if it doesn't exist. HTTP 422 means it already exists — both are fine."""
        r = self._session.post(
            f"{self._url}/api/v1/orgs",
            json={"username": org, "visibility": visibility},
        )
        if r.status_code not in (201, 422):
            r.raise_for_status()

    def prepare_destination(self, dest_org: str) -> dict:
        """Ensure org exists and return migration kwargs with uid."""
        self.ensure_org(dest_org)
        uid = self.get_org_uid(dest_org)
        return {"uid": uid, "auth_username": "", "auth_token": ""}

    def create_mirror(self, repo: Repo, dest_org: str | None = None, **kwargs) -> MigrationResult:
        """Migrate repo as a mirror into Gitea. Retries on transient failures."""
        uid = kwargs.get("uid")
        auth_username = kwargs.get("auth_username", "")
        auth_token = kwargs.get("auth_token", "")

        payload: dict = {
            "clone_addr": repo.clone_url,
            "repo_name": repo.name,
            "description": repo.description,
            "mirror": True,
            "private": repo.private,
        }
        if uid is not None:
            payload["uid"] = uid
        if repo.private and auth_username and auth_token:
            payload["auth_username"] = auth_username
            payload["auth_password"] = auth_token

        max_attempts, delay = 3, 5.0
        for attempt in range(1, max_attempts + 1):
            r = self._session.post(f"{self._url}/api/v1/repos/migrate", json=payload)
            if r.status_code in (200, 201):
                time.sleep(self._api_delay)
                return MigrationResult(repo_name=repo.name, status="MIGRATED")
            elif r.status_code == 409:
                return MigrationResult(repo_name=repo.name, status="SKIPPED",
                                       reason="already exists in Gitea")
            elif r.status_code == 422:
                return MigrationResult(
                    repo_name=repo.name, status="FAILED",
                    reason="HTTP 422: Ensure 'github.com' is in ALLOWED_DOMAINS in app.ini [migrations]",
                )
            else:
                logger.warning("Attempt %d/%d failed (HTTP %s). Retrying in %.0fs...",
                               attempt, max_attempts, r.status_code, delay)
                time.sleep(delay)
                delay *= 2

        return MigrationResult(repo_name=repo.name, status="FAILED",
                               reason=f"Failed after {max_attempts} attempts")

    def delete_org(self, org: str, force: bool = False, dry_run: bool = False) -> None:
        """Delete a Gitea org and all its repos. Supports dry run and force modes."""
        repos = self._paginate_names(org)
        if dry_run:
            logger.info("[DRY RUN] Would delete %d repos and org '%s'", len(repos), org)
            for name in repos:
                logger.info("[DRY RUN] Would delete: %s/%s", org, name)
            return

        if not force:
            confirm = input(f"Type '{org}' to confirm deletion: ").strip()
            if confirm != org:
                raise SystemExit(f"Aborted: '{confirm}' != '{org}'")

        for name in repos:
            r = self._session.delete(f"{self._url}/api/v1/repos/{org}/{name}")
            if r.status_code not in (204, 200, 404):
                logger.warning("Failed to delete %s/%s: HTTP %s", org, name, r.status_code)
            time.sleep(0.5)

        r = self._session.delete(f"{self._url}/api/v1/orgs/{org}")
        if r.status_code not in (204, 200, 404):
            r.raise_for_status()

    def _paginate(self, url: str) -> list[Repo]:
        repos: list[Repo] = []
        params: dict = {"limit": 50}
        while url:
            r = self._session.get(url, params=params)
            r.raise_for_status()
            data = r.json()
            if not data:
                break
            repos.extend(self._normalize(item) for item in data)
            url = parse_next_link(r.headers.get("Link"))
            params = {}
        return repos

    def _paginate_names(self, org: str) -> list[str]:
        names: list[str] = []
        url = f"{self._url}/api/v1/orgs/{org}/repos"
        params: dict = {"limit": 50}
        while url:
            r = self._session.get(url, params=params)
            if r.status_code == 404:
                raise SystemExit(f"Organization '{org}' not found")
            r.raise_for_status()
            data = r.json()
            if not data:
                break
            names.extend(item["name"] for item in data)
            url = parse_next_link(r.headers.get("Link"))
            params = {}
        return names

    def _normalize(self, data: dict) -> Repo:
        return Repo(
            name=data["name"],
            clone_url=data.get("clone_url", ""),
            description=(data.get("description") or "")[:255],
            private=data.get("private", False),
            owner=data.get("owner", {}).get("login", ""),
            topics=data.get("topics", []),
            language=data.get("language") or "",
            source_type="gitea",
        )
