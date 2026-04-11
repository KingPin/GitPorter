# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

A Python tool for mirroring repos between Git platforms using a plugin/adapter pattern. Each platform (GitHub, Gitea, GitLab, Bitbucket, Forgejo) is a self-contained adapter. A pipeline orchestrator runs fetch → filter → resume-check → migrate → summary.

## Project Structure

```
gitporter/
├── config.py            # Credential loading + validation per platform
├── adapters/
│   ├── __init__.py      # Adapter registry (_REGISTRY) — register new adapters here
│   ├── base.py          # Repo, MigrationResult dataclasses + BaseAdapter ABC
│   ├── github.py        # GitHub adapter (source + destination)
│   ├── gitea.py         # Gitea adapter (source + destination + delete_org)
│   ├── gitlab.py        # GitLab adapter (source + destination)
│   ├── bitbucket.py     # Bitbucket adapter (source + destination + delete_org)
│   └── forgejo.py       # Forgejo adapter (destination + delete_org, inherits Gitea)
└── core/
    ├── http.py          # Link header parsing + exponential backoff
    ├── filters.py       # Repo filtering (name glob, language, topic, ignore list)
    ├── parallel.py      # Auto-scaling ThreadPoolExecutor
    └── migrator.py      # Migration pipeline orchestrator
main.py                  # CLI entry point
```

## Environment Variables

| Variable                | Required by                                      |
|-------------------------|--------------------------------------------------|
| `GITEA_URL`             | Gitea destination                                |
| `GITEA_TOKEN`           | Gitea destination (or `ACCESS_TOKEN` fallback)   |
| `ACCESS_TOKEN`          | Legacy fallback for `GITEA_TOKEN`                |
| `GITHUB_TOKEN`          | GitHub source/destination                        |
| `GITLAB_URL`            | GitLab source/destination                        |
| `GITLAB_TOKEN`          | GitLab source/destination                        |
| `BITBUCKET_WORKSPACE`   | Bitbucket source/destination                     |
| `BITBUCKET_USERNAME`    | Bitbucket source/destination                     |
| `BITBUCKET_APP_PASSWORD`| Bitbucket source/destination                     |
| `FORGEJO_URL`           | Forgejo destination                              |
| `FORGEJO_TOKEN`         | Forgejo destination                              |

No trailing slash in URL variables (`GITEA_URL`, `GITLAB_URL`, `FORGEJO_URL`).

## Running with Docker Compose

All commands run inside Docker — do not install Python packages on the local system.

```bash
# Build the image (required after code changes)
docker compose build

# Run tests
docker compose run --rm test

# Migrate
docker compose run --rm app migrate --source github --dest gitea --mode org -o <org> --visibility public
docker compose run --rm app migrate --source github --dest gitea --mode user -u <user>
docker compose run --rm app migrate --source github --dest gitea --mode user -u <user> -o <org>
docker compose run --rm app migrate --source github --dest gitea --mode star -u <user> -o <org>
docker compose run --rm app migrate --source github --dest gitea --mode repo -r <url> -u <user>

# Cross-platform examples (any source → any dest)
docker compose run --rm app migrate --source gitlab --dest gitea --mode org -o mygroup
docker compose run --rm app migrate --source bitbucket --dest gitea --mode org -o myworkspace
docker compose run --rm app migrate --source gitea --dest forgejo --mode org -o myorg
docker compose run --rm app migrate --source github --dest bitbucket --mode org -o myworkspace
docker compose run --rm app migrate --source gitlab --dest github --mode org -o myorg

# Filtering
docker compose run --rm app migrate ... --filter-language python --filter-topic ml --filter-name "*-service"

# Ignore specific repos by name (comma-separated)
docker compose run --rm app migrate ... --ignore-repos "repo1,repo2"

# Dry run (shows what would happen without doing it)
docker compose run --rm app migrate ... --dry-run

# LFS support (mirror repos with LFS files)
docker compose run --rm app migrate ... --lfs

# Cleanup orphaned repos after migration
docker compose run --rm app migrate ... --cleanup-action archive   # archive orphans
docker compose run --rm app migrate ... --cleanup-action delete    # delete orphans

# Mirror releases from source to destination
docker compose run --rm app migrate ... --include-releases

# Delete org/repos on any platform
docker compose run --rm app delete --dest gitea -o <org> --dry-run   # preview
docker compose run --rm app delete --dest gitea -o <org>              # interactive confirm
docker compose run --rm app delete --dest gitea -o <org> --force      # no prompt (CI/CD)
docker compose run --rm app delete --dest forgejo -o <org>
docker compose run --rm app delete --dest github -o <org>             # deletes all repos + org
docker compose run --rm app delete --dest gitlab -o <group>
docker compose run --rm app delete --dest bitbucket -o <workspace>    # deletes all repos (workspace itself not deleted)
```

## Key Behaviors

- **Resume on failure**: re-run the same command — repos already at the destination (HTTP 409) are skipped automatically; works for cross-platform migrations too
- **Repo ignore list**: use `--ignore-repos repo1,repo2` to skip specific repos by name during migration
- **Git LFS**: use `--lfs` to mirror repos that contain LFS-tracked files
- **Orphan cleanup**: `--cleanup-action archive|delete` removes repos from the destination that no longer exist in the source
- **Release mirroring**: `--include-releases` copies releases and their assets to the destination
- **Parallel migrations**: auto-scales workers based on repo count (<5=sequential, 5-20=3 workers, >20=up to 10)
- **Rate limiting**: exponential backoff on GitHub 403/429 responses
- **GitHub org as destination**: the org must already exist — GitHub does not allow API-based org creation
- **Bitbucket delete**: `delete --dest bitbucket` removes all repos in the workspace but cannot delete the workspace itself (Bitbucket API limitation)
- **422 error on Gitea/Forgejo**: means the source domain is not in `ALLOWED_DOMAINS` in the `app.ini [migrations]` section
- **Dry run**: phases 1-3 (fetch/filter/resume-check) run fully — output shows exactly what would be migrated

## Adding a New Adapter

1. Create `gitporter/adapters/<platform>.py`
2. Subclass `BaseAdapter` from `adapters/base.py`
3. Set `platform_name = "<platform>"` class attribute
4. Implement: `list_repos`, `create_mirror`, `repo_exists`
5. Override `prepare_destination` if the destination needs pre-setup (e.g., Gitea/Forgejo needs org UID)
6. Override `fetch_one_repo` if single-repo fetch is supported
7. Add credentials to `gitporter/config.py` — add to `_REQUIRED` dict and return a normalized dict
8. Register in `adapters/__init__.py` — add to `_REGISTRY`
9. Add `--source`/`--dest` to `choices=` in `build_parser()` in `main.py`
