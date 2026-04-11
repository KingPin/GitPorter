import logging
from github2gitea.adapters.base import BaseAdapter, MigrationResult
from github2gitea.core.filters import apply_filters
from github2gitea.core.parallel import run_parallel

logger = logging.getLogger(__name__)


class Migrator:
    def __init__(
        self,
        source: BaseAdapter,
        dest: BaseAdapter,
        dry_run: bool = False,
        name_pattern: str | None = None,
        language: str | None = None,
        topic: str | None = None,
        dest_org: str | None = None,
        dest_uid: int | None = None,
        auth_username: str | None = None,
        auth_token: str | None = None,
    ):
        self._source = source
        self._dest = dest
        self._dry_run = dry_run
        self._filter_kwargs = dict(name_pattern=name_pattern, language=language, topic=topic)
        self._dest_org = dest_org
        self._dest_uid = dest_uid
        self._auth_username = auth_username
        self._auth_token = auth_token

    def run(
        self,
        mode: str,
        user: str | None = None,
        org: str | None = None,
        repo_url: str | None = None,
    ) -> list[MigrationResult]:
        # Phase 1: Fetch
        logger.info("Fetching repos from source...")
        if mode == "repo" and hasattr(self._source, "fetch_one_repo"):
            if not repo_url:
                raise ValueError("--repo is required when --mode repo is used")
            repos = [self._source.fetch_one_repo(repo_url)]
        else:
            repos = self._source.list_repos(mode=mode, user=user, org=org)
        logger.info("Fetched %d repos.", len(repos))

        # Phase 2: Filter
        repos = apply_filters(repos, **self._filter_kwargs)
        logger.info("%d repos after filtering.", len(repos))

        # Phase 3: Resume check — skip repos that already exist in destination
        owner = self._dest_org or user or org
        to_migrate: list = []
        results: list[MigrationResult] = []
        for repo in repos:
            if self._dest.repo_exists(repo.name, owner):
                results.append(MigrationResult(repo.name, "SKIPPED",
                                               "already exists in destination"))
            else:
                to_migrate.append(repo)
        logger.info("%d to migrate, %d already exist.", len(to_migrate), len(results))

        # Phase 4: Migrate (or dry run)
        if self._dry_run:
            results += [MigrationResult(r.name, "SKIPPED", "dry run") for r in to_migrate]
            return results

        migrate_kwargs = dict(
            dest_org=self._dest_org,
            uid=self._dest_uid,
            auth_username=self._auth_username,
            auth_token=self._auth_token,
        )
        results += run_parallel(
            lambda repo: self._dest.create_mirror(repo, **migrate_kwargs),
            to_migrate,
        )
        return results
