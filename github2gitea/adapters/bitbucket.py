import logging
import os
import shutil
import subprocess
import tempfile
import urllib.parse

import requests

from .base import BaseAdapter, MigrationResult, Repo

logger = logging.getLogger(__name__)


class BitbucketAdapter(BaseAdapter):
    """Bitbucket Cloud adapter (source and destination via git clone+push)."""

    platform_name = "bitbucket"

    def __init__(self, config: dict):
        self._workspace = config["workspace"]
        self._username = config["username"]
        self._app_password = config["app_password"]
        self._session = requests.Session()
        self._session.auth = (self._username, self._app_password)

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
        """Mirror repo to Bitbucket via git clone --mirror + push --mirror."""
        owner = dest_org if dest_org else self._workspace
        enable_lfs = kwargs.get("enable_lfs", False)
        tmp_dir = tempfile.mkdtemp()
        tmp_path = os.path.join(tmp_dir, f"{repo.name}.git")
        try:
            # Create destination repo via Bitbucket API
            resp = self._session.post(
                f"https://api.bitbucket.org/2.0/repositories/{owner}/{repo.name}",
                json={
                    "scm": "git",
                    "is_private": repo.private,
                    "description": repo.description,
                },
            )
            if resp.status_code == 400 and "already exists" in resp.text.lower():
                return MigrationResult(repo.name, "SKIPPED", "already exists")
            if resp.status_code not in (200, 201):
                resp.raise_for_status()

            # Clone mirror from source
            clone_cmd = (
                ["git", "lfs", "clone", "--mirror", repo.clone_url, tmp_path]
                if enable_lfs
                else ["git", "clone", "--mirror", repo.clone_url, tmp_path]
            )
            clone_result = subprocess.run(clone_cmd, check=False, capture_output=True)
            if clone_result.returncode != 0:
                raise RuntimeError(clone_result.stderr.decode().strip())

            # Build push URL with Basic auth embedded
            encoded_password = urllib.parse.quote(self._app_password, safe="")
            push_url = (
                f"https://{self._username}:{encoded_password}"
                f"@bitbucket.org/{owner}/{repo.name}.git"
            )
            push_result = subprocess.run(
                ["git", "-C", tmp_path, "push", "--mirror", push_url],
                check=False,
                capture_output=True,
            )
            if push_result.returncode != 0:
                err = push_result.stderr.decode().strip()
                err = err.replace(self._app_password, "***").replace(encoded_password, "***")
                raise RuntimeError(err)

            return MigrationResult(repo.name, "MIGRATED")
        except Exception as exc:
            return MigrationResult(repo.name, "FAILED", str(exc))
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def disable_workflows(self, repo_name: str, owner: str) -> None:
        """Disable Bitbucket Pipelines on the repo."""
        resp = self._session.put(
            f"https://api.bitbucket.org/2.0/repositories/{owner}/{repo_name}/pipelines_config",
            json={"enabled": False},
        )
        resp.raise_for_status()
        logger.debug("Disabled Pipelines for %s/%s", owner, repo_name)

    def delete_org(self, org: str, force: bool = False, dry_run: bool = False) -> None:
        """Delete all repos in a Bitbucket workspace (workspace itself cannot be deleted via API)."""
        url: str | None = f"https://api.bitbucket.org/2.0/repositories/{org}"
        repo_slugs: list[str] = []
        while url:
            resp = self._session.get(url)
            if resp.status_code == 404:
                raise SystemExit(f"Bitbucket workspace '{org}' not found.")
            resp.raise_for_status()
            data = resp.json()
            repo_slugs.extend(r["slug"] for r in data.get("values", []))
            url = data.get("next")

        if dry_run:
            logger.info("[DRY RUN] Would delete %d repos from workspace '%s'", len(repo_slugs), org)
            for slug in repo_slugs:
                logger.info("[DRY RUN] Would delete: %s/%s", org, slug)
            return

        if not force:
            confirm = input(f"Type '{org}' to confirm deletion of all repos: ").strip()
            if confirm != org:
                raise SystemExit(f"Aborted: '{confirm}' != '{org}'")

        for slug in repo_slugs:
            resp = self._session.delete(
                f"https://api.bitbucket.org/2.0/repositories/{org}/{slug}"
            )
            if resp.status_code not in (204, 404):
                logger.warning("Failed to delete %s/%s: HTTP %s", org, slug, resp.status_code)

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
