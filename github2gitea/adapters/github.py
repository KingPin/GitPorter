import logging
import os
import shutil
import subprocess
import tempfile
import time
import requests
from .base import BaseAdapter, Repo, MigrationResult
from ..core.http import parse_next_link, http_get_with_backoff

logger = logging.getLogger(__name__)
GITHUB_API = "https://api.github.com"


class GitHubAdapter(BaseAdapter):
    platform_name = "github"

    def __init__(self, config: dict | None = None, api_delay: float = 2.0):
        if config is None:
            config = {}
        self._token = config.get("token", "")
        self._api_base = config.get("url", GITHUB_API)
        self._session = requests.Session()
        if self._token:
            self._session.headers["Authorization"] = f"Bearer {self._token}"
        self._session.headers["Accept"] = "application/vnd.github+json"
        self._api_delay = api_delay

    def list_repos(self, mode: str, user: str | None = None, org: str | None = None) -> list[Repo]:
        """Return all repos for the given mode. Handles pagination internally."""
        if mode == "org":
            return self._paginate(f"{self._api_base}/orgs/{org}/repos")
        elif mode == "user":
            if "Authorization" in self._session.headers:
                # Authenticated: always use the /user/repos endpoint so that
                # destination org does not accidentally change which repos are fetched.
                return self._paginate(f"{self._api_base}/user/repos", params={"affiliation": "owner"})
            else:
                # Unauthenticated: fall back to the public endpoint (public repos only).
                if not user:
                    raise ValueError("--user is required for unauthenticated user-mode listing")
                return self._paginate(f"{self._api_base}/users/{user}/repos")
        elif mode == "star":
            return self._paginate(f"{self._api_base}/users/{user}/starred")
        elif mode == "repo":
            raise ValueError("Use fetch_one_repo() for single-repo mode")
        else:
            raise ValueError(f"Unknown mode: {mode}")

    def fetch_one_repo(self, repo_url: str) -> Repo:
        """Fetch a single repo by its GitHub URL."""
        path = repo_url.replace("https://github.com/", "").removesuffix(".git")
        r = http_get_with_backoff(self._session, f"{self._api_base}/repos/{path}")
        return self._normalize(r.json())

    def repo_exists(self, repo_name: str, owner: str) -> bool:
        """Return True if repo exists on GitHub."""
        r = self._session.get(f"{self._api_base}/repos/{owner}/{repo_name}")
        return r.status_code == 200

    def create_mirror(self, repo: Repo, dest_org: str | None = None, **kwargs) -> MigrationResult:
        """Mirror repo to GitHub by cloning and push --mirror."""
        tmp_dir = tempfile.mkdtemp()
        tmp_path = os.path.join(tmp_dir, f"{repo.name}.git")
        try:
            # Determine owner for the push destination
            owner = dest_org if dest_org else repo.owner

            # Create destination repo via API
            if dest_org:
                url = f"{self._api_base}/orgs/{dest_org}/repos"
            else:
                url = f"{self._api_base}/user/repos"

            payload = {
                "name": repo.name,
                "description": repo.description,
                "private": repo.private,
            }
            resp = self._session.post(url, json=payload)
            if resp.status_code != 201:
                if resp.status_code == 422:
                    try:
                        error_body = resp.json()
                    except ValueError:
                        error_body = {}
                    message = str(error_body.get("message", "")).lower()
                    errors = error_body.get("errors", [])
                    already_exists = any(
                        isinstance(error, dict)
                        and error.get("resource") == "Repository"
                        and error.get("field") == "name"
                        and "already exists" in str(error.get("message", "")).lower()
                        for error in errors
                    ) or "already exists" in message
                    if not already_exists:
                        resp.raise_for_status()
                else:
                    resp.raise_for_status()

            # Clone mirror
            enable_lfs = kwargs.get("enable_lfs", False)
            clone_cmd = (
                ["git", "lfs", "clone", "--mirror", repo.clone_url, tmp_path]
                if enable_lfs
                else ["git", "clone", "--mirror", repo.clone_url, tmp_path]
            )
            clone_result = subprocess.run(
                clone_cmd,
                check=False,
                capture_output=True,
            )
            if clone_result.returncode != 0:
                raise RuntimeError(clone_result.stderr.decode().strip())

            # Push mirror
            if self._token:
                push_url = f"https://{self._token}@github.com/{owner}/{repo.name}.git"
            else:
                push_url = f"https://github.com/{owner}/{repo.name}.git"

            push_result = subprocess.run(
                ["git", "-C", tmp_path, "push", "--mirror", push_url],
                check=False,
                capture_output=True,
            )
            if push_result.returncode != 0:
                raise RuntimeError(push_result.stderr.decode().strip())

            return MigrationResult(repo.name, "MIGRATED")

        except Exception as exc:
            return MigrationResult(repo.name, "FAILED", str(exc))
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def fetch_releases(self, owner: str, repo_name: str) -> list[dict]:
        """Fetch all releases for a repo from GitHub, handling pagination."""
        url = f"{self._api_base}/repos/{owner}/{repo_name}/releases"
        releases = []
        while url:
            resp = self._session.get(url)
            resp.raise_for_status()
            releases.extend(resp.json())
            url = parse_next_link(resp.headers.get("Link", ""))
            if url:
                time.sleep(self._api_delay)
        return releases

    def disable_workflows(self, repo_name: str, owner: str) -> None:
        """Disable GitHub Actions on the repo."""
        resp = self._session.put(
            f"{self._api_base}/repos/{owner}/{repo_name}/actions/permissions",
            json={"enabled": False},
        )
        resp.raise_for_status()
        logger.debug("Disabled Actions for %s/%s", owner, repo_name)

    def prepare_destination(self, dest_org: str, visibility: str = "public") -> dict:
        """Ensure the GitHub org exists (it must already; GitHub doesn't allow API org creation).
        Returns empty dict — GitHub repos are created inside create_mirror directly."""
        resp = self._session.get(f"{self._api_base}/orgs/{dest_org}")
        if resp.status_code == 404:
            raise SystemExit(
                f"GitHub org '{dest_org}' does not exist. "
                "GitHub organizations cannot be created via API — create it manually first."
            )
        resp.raise_for_status()
        return {}

    def delete_org(self, org: str, force: bool = False, dry_run: bool = False) -> None:
        """Delete all repos in a GitHub org, then delete the org itself."""
        url: str | None = f"{self._api_base}/orgs/{org}/repos"
        repo_names: list[str] = []
        while url:
            resp = self._session.get(url, params={"per_page": 100})
            if resp.status_code == 404:
                raise SystemExit(f"GitHub org '{org}' not found.")
            resp.raise_for_status()
            repo_names.extend(r["name"] for r in resp.json())
            url = parse_next_link(resp.headers.get("Link", ""))

        if dry_run:
            logger.info("[DRY RUN] Would delete %d repos and org '%s'", len(repo_names), org)
            for name in repo_names:
                logger.info("[DRY RUN] Would delete: %s/%s", org, name)
            return

        if not force:
            confirm = input(f"Type '{org}' to confirm deletion: ").strip()
            if confirm != org:
                raise SystemExit(f"Aborted: '{confirm}' != '{org}'")

        for name in repo_names:
            resp = self._session.delete(f"{self._api_base}/repos/{org}/{name}")
            if resp.status_code not in (204, 404):
                logger.warning("Failed to delete %s/%s: HTTP %s", org, name, resp.status_code)
            time.sleep(0.3)

        resp = self._session.delete(f"{self._api_base}/orgs/{org}")
        if resp.status_code not in (204, 404):
            resp.raise_for_status()

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
