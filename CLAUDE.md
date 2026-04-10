# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

A Python tool for mirroring repos between Git platforms using a plugin/adapter pattern. Each platform (GitHub, Gitea, GitLab, Bitbucket) is a self-contained adapter. A pipeline orchestrator runs fetch → filter → resume-check → migrate → summary.

## Project Structure

```
github2gitea/
├── adapters/
│   ├── base.py          # Repo, MigrationResult dataclasses + BaseAdapter ABC
│   ├── github.py        # GitHub adapter (source)
│   ├── gitea.py         # Gitea adapter (source + destination + delete_org)
│   ├── gitlab.py        # GitLab stub (not yet implemented)
│   └── bitbucket.py     # Bitbucket stub (not yet implemented)
└── core/
    ├── http.py          # Link header parsing + exponential backoff
    ├── filters.py       # Repo filtering (name glob, language, topic)
    ├── parallel.py      # Auto-scaling ThreadPoolExecutor
    └── migrator.py      # Migration pipeline orchestrator
main.py                  # CLI entry point
```

## Environment Variables

| Variable        | Required by         |
|-----------------|---------------------|
| `GITEA_URL`     | All commands        |
| `ACCESS_TOKEN`  | All commands        |
| `GITHUB_TOKEN`  | GitHub source only  |

No trailing slash in `GITEA_URL`.

## Running with Docker Compose

All commands run inside Docker — do not install Python packages on the local system.

```bash
# Build the image (required after code changes)
docker compose build

# Run tests
docker compose run --rm test

# Migrate
docker compose run --rm app migrate --source github --dest gitea --mode org -o <org> -v public
docker compose run --rm app migrate --source github --dest gitea --mode user -u <user>
docker compose run --rm app migrate --source github --dest gitea --mode user -u <user> -o <org>
docker compose run --rm app migrate --source github --dest gitea --mode star -u <user> -o <org>
docker compose run --rm app migrate --source github --dest gitea --mode repo -r <url> -u <user>

# Filtering
docker compose run --rm app migrate ... --filter-language python --filter-topic ml --filter-name "*-service"

# Dry run (shows what would happen without doing it)
docker compose run --rm app migrate ... --dry-run

# Delete a Gitea org and all its repos
docker compose run --rm app delete --dest gitea -o <org> --dry-run   # preview
docker compose run --rm app delete --dest gitea -o <org>              # interactive confirm
docker compose run --rm app delete --dest gitea -o <org> --force      # no prompt (CI/CD)
```

## Key Behaviors

- **Resume on failure**: re-run the same command — repos already in Gitea (HTTP 409) are skipped automatically
- **Parallel migrations**: auto-scales workers based on repo count (<5=sequential, 5-20=3 workers, >20=up to 10)
- **Rate limiting**: exponential backoff on GitHub 403/429 responses
- **Gitea 422 error**: means `github.com` is not in `ALLOWED_DOMAINS` in Gitea's `app.ini [migrations]` section
- **Dry run**: phases 1-3 (fetch/filter/resume-check) run fully — output shows exactly what would be migrated

## Adding a New Adapter

1. Create `github2gitea/adapters/<platform>.py`
2. Implement all methods from `BaseAdapter` in `adapters/base.py`
3. Add it to `source_map` / `dest_map` in `main.py`
4. Add `--source` / `--dest` to the `choices=` in `build_parser()`
