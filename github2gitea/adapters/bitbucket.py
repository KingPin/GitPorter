from .base import BaseAdapter, Repo, MigrationResult


class BitbucketAdapter(BaseAdapter):
    """Bitbucket source adapter — not yet implemented.

    To implement: see BaseAdapter in adapters/base.py for the required interface.
    Bitbucket API docs: https://developer.atlassian.com/cloud/bitbucket/rest/
    """

    def list_repos(self, mode: str, user: str | None = None, org: str | None = None) -> list[Repo]:
        raise NotImplementedError("Bitbucket adapter is not yet implemented.")

    def create_mirror(self, repo: Repo, dest_org: str | None = None,
                      uid: int | None = None, auth_username: str | None = None,
                      auth_token: str | None = None, **kwargs) -> MigrationResult:
        raise NotImplementedError

    def repo_exists(self, repo_name: str, owner: str) -> bool:
        raise NotImplementedError

    def delete_org(self, org: str, force: bool = False, dry_run: bool = False) -> None:
        raise NotImplementedError
