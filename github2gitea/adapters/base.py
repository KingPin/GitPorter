from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class Repo:
    name: str
    clone_url: str
    description: str
    private: bool
    owner: str
    topics: list[str] = field(default_factory=list)
    language: str = ""
    source_type: str = ""


@dataclass
class MigrationResult:
    repo_name: str
    status: Literal["MIGRATED", "SKIPPED", "FAILED"]
    reason: str = ""


class BaseAdapter(ABC):
    platform_name: str = ""

    @abstractmethod
    def list_repos(self, mode: str, user: str | None = None, org: str | None = None) -> list[Repo]:
        """Return all repos matching the given mode, handling pagination internally."""

    @abstractmethod
    def create_mirror(
        self,
        repo: Repo,
        dest_org: str | None = None,
        **kwargs,
    ) -> MigrationResult:
        """Create a mirror of repo in this adapter's platform.

        Args:
            repo: Repository metadata for the source repository.
            dest_org: Destination organisation/user to create the mirror under.
            **kwargs: Forward-compatible adapter-specific options (e.g. uid, auth_username,
                      auth_token supplied by prepare_destination).
        """

    @abstractmethod
    def repo_exists(self, repo_name: str, owner: str) -> bool:
        """Check if repo already exists — used for resume-on-failure."""

    def fetch_one_repo(self, repo_url: str) -> Repo:
        """Fetch metadata for a single repo by URL.

        Raises NotImplementedError by default; adapters that support single-repo
        fetch should override this method.
        """
        raise NotImplementedError(f"{self.platform_name} does not support single-repo fetch")

    def prepare_destination(self, dest_org: str, visibility: str = "public") -> dict:
        """Return adapter-specific kwargs to pass to create_mirror.

        Default returns an empty dict. Adapters like Gitea/Forgejo override this
        to return {"uid": ..., "auth_username": ..., "auth_token": ...}.
        """
        return {}

    def list_dest_repos(self, owner: str) -> list[str]:
        """List repo names in dest org. Override in adapters that support cleanup."""
        raise NotImplementedError(f"{self.platform_name} does not support destination repo listing (required for --cleanup-action)")

    def archive_repo(self, name: str, owner: str) -> None:
        raise NotImplementedError(f"{self.platform_name} does not support repo archiving")

    def delete_repo(self, name: str, owner: str) -> None:
        raise NotImplementedError(f"{self.platform_name} does not support repo deletion")

    def fetch_releases(self, owner: str, repo_name: str) -> list[dict]:
        """Fetch releases from source. Returns [] if not supported."""
        return []

    def mirror_releases(self, repo_name: str, owner: str, releases: list[dict]) -> None:
        """Mirror releases to dest. No-op if not supported."""
        return
