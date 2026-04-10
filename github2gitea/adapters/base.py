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
    def list_repos(self, mode: str, user: str = None, org: str = None) -> list[Repo]:
        """Fetch repos — handles pagination internally via Link header."""

    @abstractmethod
    def create_mirror(self, repo: Repo, dest_org: str = None) -> MigrationResult:
        """Create a mirror of repo in this adapter's platform."""

    @abstractmethod
    def repo_exists(self, repo_name: str, owner: str) -> bool:
        """Check if repo already exists — used for resume-on-failure."""

    @abstractmethod
    def delete_org(self, org: str, force: bool = False, dry_run: bool = False) -> None:
        """Delete org and all its repos."""
