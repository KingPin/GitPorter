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
    @abstractmethod
    def list_repos(self, mode: str, user: str | None = None, org: str | None = None) -> list[Repo]:
        """Return all repos matching the given mode, handling pagination internally."""

    @abstractmethod
    def create_mirror(
        self,
        repo: Repo,
        dest_org: str | None = None,
        uid: int | None = None,
        auth_username: str | None = None,
        auth_token: str | None = None,
        **kwargs,
    ) -> MigrationResult:
        """Create a mirror of repo in this adapter's platform.

        Args:
            repo: Repository metadata for the source repository.
            dest_org: Destination organisation/user to create the mirror under.
            uid: Optional numeric user/org ID used by some adapters (e.g. Gitea).
            auth_username: Optional username for authenticated cloning of private repos.
            auth_token: Optional token for authenticated cloning of private repos.
            **kwargs: Forward-compatible adapter-specific options.
        """

    @abstractmethod
    def repo_exists(self, repo_name: str, owner: str) -> bool:
        """Check if repo already exists — used for resume-on-failure."""

    @abstractmethod
    def delete_org(self, org: str, force: bool = False, dry_run: bool = False) -> None:
        """Delete org and all its repos.

        Args:
            org: Name of the organisation to delete.
            force: Skip confirmation prompts when True.
            dry_run: List what would be deleted without making any changes when True.
        """
