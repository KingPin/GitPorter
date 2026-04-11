# git-migrator

A Python tool for mirroring Git repositories between platforms. Currently supports GitHub as a source and Gitea as a destination, with GitLab and Bitbucket stubs ready to implement.

Runs entirely inside Docker — no local Python installation required.

---

## Features

- **Mirror modes** — mirror a whole org, a user's repos, starred repos, or a single repo
- **Dry run** — see exactly what would be migrated without touching anything
- **Repo filtering** — filter by name glob, language, or topic before migrating
- **Resume on failure** — re-run the same command; repos already in Gitea are skipped automatically
- **Parallel migrations** — auto-scales worker threads based on repo count
- **Rate limit handling** — exponential backoff on GitHub 403/429 responses
- **Delete orgs** — safely delete a Gitea org and all its repos, with interactive confirmation or `--force` for CI/CD

---

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) with the Compose plugin (`docker compose`)
- A **Gitea** instance with an access token
- A **GitHub** personal access token (for private repos or to avoid rate limits)

---

## Quick Start

### 1. Clone the repo

```bash
git clone git@github.com:KingPin/git-migrator.git
cd git-migrator
```

### 2. Build the Docker image

```bash
docker compose build
```

### 3. Set environment variables

```bash
export GITEA_URL=http://your-gitea-instance:3000   # no trailing slash
export ACCESS_TOKEN=your_gitea_access_token
export GITHUB_TOKEN=your_github_personal_access_token
```

You can also put these in a `.env` file in the project root (it is gitignored):

```bash
GITEA_URL=http://your-gitea-instance:3000
ACCESS_TOKEN=your_gitea_access_token
GITHUB_TOKEN=your_github_personal_access_token
```

### 4. Run a migration

```bash
# Mirror all repos of a GitHub user to your personal Gitea account
docker compose run --rm app migrate --source github --dest gitea --mode user -u myusername
```

---

## Environment Variables

| Variable       | Required            | Description                              |
|----------------|---------------------|------------------------------------------|
| `GITEA_URL`    | Always              | Base URL of your Gitea instance. No trailing slash. |
| `ACCESS_TOKEN` | Always              | Gitea personal access token.             |
| `GITHUB_TOKEN` | Recommended         | GitHub PAT. Required for private repos; strongly recommended to avoid rate limits. |

---

## Commands

### `migrate` — mirror repos

```
docker compose run --rm app migrate --source <source> --dest <dest> --mode <mode> [options]
```

#### Required flags

| Flag | Values | Description |
|------|--------|-------------|
| `--source` | `github` | Source platform |
| `--dest` | `gitea` | Destination platform |
| `--mode` | `org`, `user`, `star`, `repo` | What to mirror |

#### Mode-specific flags

| Mode | Required flags | Description |
|------|---------------|-------------|
| `org` | `--org`, `--visibility` | Mirror all repos in a GitHub org to a Gitea org |
| `user` | `--user` | Mirror all repos owned by a GitHub user |
| `user` + `--org` | `--user`, `--org`, `--visibility` | Mirror a user's repos into a Gitea org |
| `star` | `--user`, `--org` | Mirror all starred repos of a user into a Gitea org |
| `repo` | `--repo`, `--user` | Mirror a single repo by URL |

#### All flags

| Flag | Default | Description |
|------|---------|-------------|
| `--org`, `-o` | — | Gitea organization name (created automatically if it doesn't exist) |
| `--user`, `-u` | — | GitHub username |
| `--visibility` | `public` | Visibility for the Gitea org: `public` or `private` |
| `--repo`, `-r` | — | Full GitHub URL for single-repo mode, e.g. `https://github.com/owner/repo` |
| `--filter-name` | — | Glob pattern to match repo names, e.g. `*-service` |
| `--filter-language` | — | Filter by primary language, e.g. `python` (case-insensitive) |
| `--filter-topic` | — | Filter by topic tag, e.g. `ml` |
| `--dry-run` | off | Show what would be migrated without doing it |
| `--verbose`, `-v` | off | Enable debug logging |

---

## Examples

### Mirror a GitHub organization

Creates the org in Gitea if it doesn't exist, then mirrors all its repos.

```bash
docker compose run --rm app migrate \
  --source github --dest gitea \
  --mode org --org my-company --visibility private
```

### Mirror your own repos to your Gitea account

```bash
docker compose run --rm app migrate \
  --source github --dest gitea \
  --mode user --user myusername
```

### Mirror a user's repos into a Gitea org

Useful for archiving someone else's public repos.

```bash
docker compose run --rm app migrate \
  --source github --dest gitea \
  --mode user --user octocat --org octocat-archive --visibility public
```

### Mirror starred repos

Mirrors everything a user has starred into a Gitea org.

```bash
docker compose run --rm app migrate \
  --source github --dest gitea \
  --mode star --user myusername --org my-stars
```

### Mirror a single repo

```bash
docker compose run --rm app migrate \
  --source github --dest gitea \
  --mode repo --repo https://github.com/owner/repo --user myusername
```

### Filter before migrating

Only migrate Python repos with the `ml` topic whose names end in `-service`:

```bash
docker compose run --rm app migrate \
  --source github --dest gitea \
  --mode org --org my-company \
  --filter-language python \
  --filter-topic ml \
  --filter-name "*-service"
```

Multiple filters are ANDed — a repo must match all specified filters.

### Dry run first

Always a good idea before a large migration:

```bash
docker compose run --rm app migrate \
  --source github --dest gitea \
  --mode org --org my-company \
  --dry-run
```

Dry run runs the full fetch, filter, and resume-check phases — it shows exactly how many repos would be migrated, how many already exist, and how many would be skipped by filters. Nothing is written to Gitea.

---

## Resuming a Failed Migration

If a migration is interrupted, just re-run the exact same command. The tool checks Gitea before migrating each repo — any repo that already exists is skipped with status `SKIPPED (already exists in destination)`. Only repos that didn't make it will be attempted again.

---

## `delete` — remove a Gitea org

> **Destructive.** Deletes all repos in the org and then the org itself.

```
docker compose run --rm app delete --dest gitea --org <org> [--dry-run] [--force]
```

| Flag | Description |
|------|-------------|
| `--org`, `-o` | The Gitea organization to delete |
| `--dry-run` | List what would be deleted without deleting anything |
| `--force` | Skip the confirmation prompt (for CI/CD use only) |

### Preview what would be deleted

```bash
docker compose run --rm app delete --dest gitea --org my-org --dry-run
```

### Interactive delete (prompts for confirmation)

```bash
docker compose run --rm app delete --dest gitea --org my-org
```

You must type the exact org name to confirm.

### Force delete (no prompt)

```bash
docker compose run --rm app delete --dest gitea --org my-org --force
```

---

## Migration Summary Output

After each run the tool prints a summary table:

```
           Migration Summary
┌──────────┬───────┐
│ Status   │ Count │
├──────────┼───────┤
│ Migrated │  47   │
│ Skipped  │   3   │
│ Failed   │   1   │
└──────────┴───────┘

Failed repos:
  • some-repo — HTTP 422: Ensure 'github.com' is in ALLOWED_DOMAINS in app.ini [migrations]
```

The process exits with code `1` if any repos failed, making it safe to use in scripts.

---

## Troubleshooting

### HTTP 422 — Validation Failed

Gitea blocks migrations from domains not on its allowlist.

**Fix:** Add `github.com` to your Gitea `app.ini`:

```ini
[migrations]
ALLOWED_DOMAINS = github.com
```

Then restart Gitea.

### HTTP 403 / 429 — Rate Limited

The tool automatically retries with exponential backoff (up to 5 attempts, starting at a 10-second delay). If you hit persistent rate limits, set a `GITHUB_TOKEN` — authenticated requests have a much higher rate limit (5,000 req/hour vs 60).

### Private repos not migrating

Make sure `GITHUB_TOKEN` is set. Private repos require authentication for both fetching the repo list and cloning.

---

## Development

### Run tests

```bash
docker compose run --rm test
```

### Run a specific test file

```bash
docker compose run --rm --entrypoint python test -m pytest tests/adapters/test_github.py -v
```

### Project structure

```
github2gitea/
├── adapters/
│   ├── base.py          # Repo, MigrationResult dataclasses + BaseAdapter ABC
│   ├── github.py        # GitHub adapter
│   ├── gitea.py         # Gitea adapter (source + destination + delete_org)
│   ├── gitlab.py        # GitLab stub (not yet implemented)
│   └── bitbucket.py     # Bitbucket stub (not yet implemented)
└── core/
    ├── http.py          # Link header pagination + exponential backoff
    ├── filters.py       # Repo filtering (name glob, language, topic)
    ├── parallel.py      # Auto-scaling ThreadPoolExecutor
    └── migrator.py      # Pipeline orchestrator
main.py                  # CLI entry point
```

### Adding a new source (e.g. GitLab)

1. Open `github2gitea/adapters/gitlab.py` — the stub is already there
2. Implement all four methods from `BaseAdapter` (`list_repos`, `create_mirror`, `repo_exists`, `delete_org`)
3. Add `"gitlab": lambda: GitLabAdapter(...)` to `source_map` in `main.py`
4. The `--source gitlab` flag will then work automatically

---

## Roadmap

- [ ] GitLab source adapter
- [ ] Bitbucket source adapter
- [ ] Gitea → GitHub (bidirectional)
- [ ] Config file (YAML/TOML) for reusable migration profiles
- [ ] Mirror sync — trigger re-sync of already-mirrored repos
