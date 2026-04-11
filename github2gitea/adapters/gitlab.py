import logging
import os
import shutil
import subprocess
import tempfile
import urllib.parse

import requests

from .base import BaseAdapter, MigrationResult, Repo

logger = logging.getLogger(__name__)


class GitLabAdapter(BaseAdapter):
    """GitLab source and destination adapter."""

    platform_name = "gitlab"

    def __init__(self, config: dict):
        self._url = config["url"].rstrip("/")
        self._token = config["token"]
        self._session = requests.Session()
        self._session.headers["PRIVATE-TOKEN"] = self._token

    # ------------------------------------------------------------------
    # Source: list repos
    # ------------------------------------------------------------------

    def list_repos(self, mode: str, user: str | None = None, org: str | None = None) -> list[Repo]:
        if mode == "org":
            base = f"{self._url}/api/v4/groups/{org}/projects?include_subgroups=true&per_page=100"
        elif mode == "user":
            base = f"{self._url}/api/v4/users/{user}/projects?per_page=100"
        elif mode == "star":
            base = f"{self._url}/api/v4/users/{user}/starred_projects?per_page=100"
        else:
            raise ValueError(f"Unknown mode: {mode}")

        all_projects: list[dict] = []
        url: str | None = base
        while url:
            resp = self._session.get(url)
            resp.raise_for_status()
            all_projects.extend(resp.json())
            next_page = resp.headers.get("X-Next-Page", "")
            if next_page:
                # Append page param — preserve existing query string
                separator = "&" if "?" in base else "?"
                url = f"{base}{separator}page={next_page}"
            else:
                url = None

        return [self._normalize(p) for p in all_projects]

    # ------------------------------------------------------------------
    # Source: single repo
    # ------------------------------------------------------------------

    def fetch_one_repo(self, repo_url: str) -> Repo:
        parsed = urllib.parse.urlparse(repo_url)
        # e.g. /group/repo  or  /group/sub/repo
        path = parsed.path.lstrip("/").removesuffix(".git")
        encoded = urllib.parse.quote(path, safe="")
        resp = self._session.get(f"{self._url}/api/v4/projects/{encoded}")
        resp.raise_for_status()
        return self._normalize(resp.json())

    # ------------------------------------------------------------------
    # Destination: repo existence check
    # ------------------------------------------------------------------

    def repo_exists(self, repo_name: str, owner: str) -> bool:
        encoded = urllib.parse.quote(f"{owner}/{repo_name}", safe="")
        resp = self._session.get(f"{self._url}/api/v4/projects/{encoded}")
        return resp.status_code == 200

    # ------------------------------------------------------------------
    # Destination: create mirror
    # ------------------------------------------------------------------

    def create_mirror(self, repo: Repo, dest_org: str | None = None, **kwargs) -> MigrationResult:
        namespace_id = kwargs.get("namespace_id")
        tmp_dir = tempfile.mkdtemp()
        tmp_path = os.path.join(tmp_dir, f"{repo.name}.git")
        try:
            payload: dict = {
                "name": repo.name,
                "visibility": "private" if repo.private else "public",
            }
            if namespace_id is not None:
                payload["namespace_id"] = namespace_id

            resp = self._session.post(f"{self._url}/api/v4/projects", json=payload)
            if resp.status_code == 409:
                return MigrationResult(repo.name, "SKIPPED", "already exists")
            resp.raise_for_status()

            # Clone mirror from source
            clone_result = subprocess.run(
                ["git", "clone", "--mirror", repo.clone_url, tmp_path],
                check=False,
                capture_output=True,
            )
            if clone_result.returncode != 0:
                raise RuntimeError(clone_result.stderr.decode().strip())

            # Build push URL with token embedded
            parsed = urllib.parse.urlparse(self._url)
            host = parsed.netloc
            owner = dest_org if dest_org else repo.owner
            push_url = f"{parsed.scheme}://oauth2:{self._token}@{host}/{owner}/{repo.name}.git"

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

    # ------------------------------------------------------------------
    # Destination: prepare namespace
    # ------------------------------------------------------------------

    def prepare_destination(self, dest_org: str, visibility: str = "public") -> dict:
        resp = self._session.get(f"{self._url}/api/v4/groups/{dest_org}")
        resp.raise_for_status()
        return {"namespace_id": resp.json()["id"]}

    # ------------------------------------------------------------------
    # Destination: disable CI/CD pipelines
    # ------------------------------------------------------------------

    def disable_workflows(self, repo_name: str, owner: str) -> None:
        """Disable GitLab CI/CD pipelines on the project."""
        encoded = urllib.parse.quote(f"{owner}/{repo_name}", safe="")
        resp = self._session.put(
            f"{self._url}/api/v4/projects/{encoded}",
            json={"builds_access_level": "disabled"},
        )
        resp.raise_for_status()
        logger.debug("Disabled CI/CD for %s/%s", owner, repo_name)

    # ------------------------------------------------------------------
    # Destination: delete org / group
    # ------------------------------------------------------------------

    def delete_org(self, org: str, **kwargs) -> None:
        resp = self._session.delete(f"{self._url}/api/v4/groups/{org}")
        resp.raise_for_status()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _normalize(self, proj: dict) -> Repo:
        return Repo(
            name=proj["path"],
            clone_url=proj["http_url_to_repo"],
            private=proj["visibility"] == "private",
            owner=proj["namespace"]["path"],
            description=proj.get("description", "") or "",
            language=proj.get("language", "") or "",
            topics=proj.get("topics", []) or [],
            source_type="gitlab",
        )
