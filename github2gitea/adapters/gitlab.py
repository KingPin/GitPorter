from .base import BaseAdapter, Repo, MigrationResult


class GitLabAdapter(BaseAdapter):
    """GitLab source adapter — not yet implemented.

    To implement: see BaseAdapter in adapters/base.py for the required interface.
    GitLab API docs: https://docs.gitlab.com/ee/api/projects.html
    """

    def list_repos(self, mode: str, user: str | None = None, org: str | None = None) -> list[Repo]:
        raise NotImplementedError("GitLab adapter is not yet implemented.")

    def create_mirror(self, repo: Repo, dest_org: str | None = None) -> MigrationResult:
        raise NotImplementedError

    def repo_exists(self, repo_name: str, owner: str) -> bool:
        raise NotImplementedError

    def delete_org(self, org: str, force: bool = False, dry_run: bool = False) -> None:
        raise NotImplementedError
