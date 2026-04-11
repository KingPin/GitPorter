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
        ignore_names: list[str] | None = None,
        enable_lfs: bool = False,
        cleanup_action: str | None = None,
    ):
        self._source = source
        self._dest = dest
        self._dry_run = dry_run
        self._filter_kwargs = dict(name_pattern=name_pattern, language=language, topic=topic, ignore_names=ignore_names)
        self._dest_org = dest_org
        self._enable_lfs = enable_lfs
        self._cleanup_action = cleanup_action

    def run(
        self,
        mode: str,
        user: str | None = None,
        org: str | None = None,
        repo_url: str | None = None,
    ) -> list[MigrationResult]:
        # Phase 1: Fetch
        logger.info("Fetching repos from source...")
        if mode == "repo":
            if not repo_url:
                raise ValueError("--repo is required when --mode repo is used")
            repos = [self._source.fetch_one_repo(repo_url)]
        else:
            repos = self._source.list_repos(mode=mode, user=user, org=org)
        logger.info("Fetched %d repos.", len(repos))
        all_source_repos = repos  # save pre-filter list for cleanup phase

        # Phase 2: Filter
        repos = apply_filters(repos, **self._filter_kwargs)
        logger.info("%d repos after filtering.", len(repos))

        # Phase 3: Resume check — skip repos that already exist in destination
        # dest_org should always be set for cross-platform migrations
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

        dest_kwargs = self._dest.prepare_destination(self._dest_org) if self._dest_org else {}
        if self._enable_lfs:
            dest_kwargs["enable_lfs"] = True

        results += run_parallel(
            lambda repo: self._dest.create_mirror(repo, dest_org=self._dest_org, **dest_kwargs),
            to_migrate,
        )

        # Phase 5: Cleanup orphaned dest repos
        if self._cleanup_action and self._dest_org and not self._dry_run:
            source_names = {r.name for r in all_source_repos}
            dest_names = self._dest.list_dest_repos(self._dest_org)
            orphans = [n for n in dest_names if n not in source_names]
            logger.info("Cleanup: %d orphaned repos in dest.", len(orphans))
            for name in orphans:
                if self._cleanup_action == "archive":
                    self._dest.archive_repo(name, self._dest_org)
                    logger.info("Archived orphan: %s", name)
                elif self._cleanup_action == "delete":
                    self._dest.delete_repo(name, self._dest_org)
                    logger.info("Deleted orphan: %s", name)

        return results
