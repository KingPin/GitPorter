# git-migrator

Mirror Git repositories between platforms — any source to any destination.

Runs entirely inside Docker. No local Python installation required.

---

## Supported Platforms

| Platform | Source | Destination |
|----------|--------|-------------|
| GitHub | ✅ | ✅ |
| GitLab | ✅ | ✅ |
| Bitbucket Cloud | ✅ | ✅ |
| Gitea | ✅ | ✅ |
| Forgejo | — | ✅ |

Any supported source can be paired with any supported destination.

---

## Features

- **Any-to-any mirroring** — GitHub → Gitea, GitLab → GitHub, Bitbucket → Forgejo, and so on
- **Four mirror modes** — whole org, user repos, starred repos, or a single repo by URL
- **Filtering** — include only repos matching a name glob, language, or topic tag
- **Ignore list** — skip specific repos by name
- **Git LFS** — mirror repos that contain LFS-tracked files
- **Release mirroring** — copy releases and their assets to the destination
- **Dry run** — see exactly what would happen without writing anything
- **Resume on failure** — re-run the same command; repos that already exist are skipped
- **Orphan cleanup** — archive or delete destination repos that no longer exist in the source
- **Disable CI/CD** — turn off GitHub Actions, GitLab pipelines, or Bitbucket Pipelines after migration
- **Parallel migrations** — auto-scales threads (1 thread for <5 repos, up to 10 for large orgs)
- **Rate limit handling** — exponential backoff on 403/429 responses
- **Safe deletes** — interactive confirmation or `--force` for CI/CD pipelines

---

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) with the Compose plugin

Tokens and credentials for the platforms you use (see [Environment Variables](#environment-variables)).

---

## Quick Start

```bash
git clone https://github.com/KingPin/git-migrator.git
cd git-migrator
docker compose build
```

Create a `.env` file in the project root (it is gitignored):

```bash
# Minimum for GitHub → Gitea
GITHUB_TOKEN=ghp_yourtoken
GITEA_URL=http://your-gitea:3000
GITEA_TOKEN=your_gitea_token
```

Run your first migration:

```bash
docker compose run --rm app migrate \
  --source github --dest gitea \
  --mode org --org my-company
```

---

## Environment Variables

Set only the variables for the platforms you are using. All variables are read from the environment or a `.env` file.

| Variable | Required by | Description |
|----------|-------------|-------------|
| `GITHUB_TOKEN` | GitHub source/dest | Personal access token. Required for private repos; strongly recommended to avoid rate limits. |
| `GITEA_URL` | Gitea source/dest | Base URL, no trailing slash. e.g. `http://gitea:3000` |
| `GITEA_TOKEN` | Gitea source/dest | Gitea personal access token (or use `ACCESS_TOKEN` as fallback) |
| `ACCESS_TOKEN` | Gitea (legacy) | Fallback alias for `GITEA_TOKEN` |
| `GITLAB_URL` | GitLab source/dest | Base URL, no trailing slash. e.g. `https://gitlab.com` |
| `GITLAB_TOKEN` | GitLab source/dest | GitLab personal access token |
| `BITBUCKET_WORKSPACE` | Bitbucket source/dest | Your Bitbucket workspace slug |
| `BITBUCKET_USERNAME` | Bitbucket source/dest | Your Bitbucket username |
| `BITBUCKET_APP_PASSWORD` | Bitbucket source/dest | App password with repo read/write permissions |
| `FORGEJO_URL` | Forgejo dest | Base URL, no trailing slash |
| `FORGEJO_TOKEN` | Forgejo dest | Forgejo access token |

---

## Commands

### `migrate` — mirror repos

```
docker compose run --rm app migrate \
  --source <source> --dest <dest> --mode <mode> [options]
```

**Mirror modes**

| Mode | Required flags | What it mirrors |
|------|----------------|-----------------|
| `org` | `--org` | All repos in an org or group |
| `user` | `--user` | All repos owned by a user |
| `user` + `--org` | `--user`, `--org` | A user's repos, placed into a destination org |
| `star` | `--user`, `--org` | All repos starred by a user |
| `repo` | `--repo`, `--user` | A single repo by URL |

**All flags**

| Flag | Default | Description |
|------|---------|-------------|
| `--source` | required | Source platform: `github`, `gitea`, `gitlab`, `bitbucket`, `forgejo` |
| `--dest` | required | Destination platform: same choices |
| `--mode` | required | `org`, `user`, `star`, `repo` |
| `--org`, `-o` | — | Org or group name at the destination (created if it doesn't exist on Gitea/Forgejo) |
| `--user`, `-u` | — | Source username |
| `--visibility` | `public` | Visibility for the created org: `public` or `private` |
| `--repo`, `-r` | — | Full repo URL for `--mode repo` |
| `--filter-name` | — | Glob pattern matched against repo name, e.g. `*-service` |
| `--filter-language` | — | Primary language filter, e.g. `python` (case-insensitive) |
| `--filter-topic` | — | Topic tag filter, e.g. `ml` |
| `--ignore-repos` | — | Comma-separated repo names to skip, e.g. `repo1,repo2` |
| `--lfs` | off | Mirror repos that use Git LFS |
| `--include-releases` | off | Copy releases and their assets to the destination |
| `--cleanup-action` | — | `archive` or `delete` orphaned destination repos that no longer exist in the source |
| `--disable-workflows` | off | Disable CI/CD (Actions / Pipelines) on each repo after migration |
| `--dry-run` | off | Fetch, filter, and check what would be migrated — write nothing |
| `--verbose`, `-v` | off | Enable debug logging |

---

### `delete` — remove an org and all its repos

> **Destructive.** Permanently deletes repos. Use `--dry-run` first.

```
docker compose run --rm app delete --dest <dest> --org <org> [--dry-run] [--force]
```

Supported destinations: `github`, `gitea`, `gitlab`, `bitbucket`, `forgejo`

> **Bitbucket note:** The Bitbucket API cannot delete workspaces. `delete` removes all repos in the workspace but leaves the workspace itself.
> **GitHub note:** Deletes all repos, then attempts to delete the org itself.

---

## Examples

### GitHub → Gitea

**Mirror a whole organisation (creates the Gitea org automatically):**

```bash
docker compose run --rm app migrate \
  --source github --dest gitea \
  --mode org --org acme-corp --visibility private
```

**Mirror your own repos to a personal Gitea account:**

```bash
docker compose run --rm app migrate \
  --source github --dest gitea \
  --mode user --user alice
```

**Mirror a user's public repos into a Gitea org (archive/backup use case):**

```bash
docker compose run --rm app migrate \
  --source github --dest gitea \
  --mode user --user torvalds --org torvalds-mirror --visibility public
```

**Mirror all your starred repos:**

```bash
docker compose run --rm app migrate \
  --source github --dest gitea \
  --mode star --user alice --org alice-stars
```

**Mirror a single repo:**

```bash
docker compose run --rm app migrate \
  --source github --dest gitea \
  --mode repo --repo https://github.com/acme/widget --user alice
```

---

### GitLab → Gitea

```bash
export GITLAB_URL=https://gitlab.com
export GITLAB_TOKEN=glpat-xxxx
export GITEA_URL=http://gitea:3000
export GITEA_TOKEN=xxxx

docker compose run --rm app migrate \
  --source gitlab --dest gitea \
  --mode org --org my-gitlab-group
```

---

### GitHub → Forgejo

```bash
export GITHUB_TOKEN=ghp_xxxx
export FORGEJO_URL=https://forgejo.example.com
export FORGEJO_TOKEN=xxxx

docker compose run --rm app migrate \
  --source github --dest forgejo \
  --mode org --org my-company
```

---

### Bitbucket → Gitea

```bash
export BITBUCKET_WORKSPACE=acme
export BITBUCKET_USERNAME=alice
export BITBUCKET_APP_PASSWORD=xxxx
export GITEA_URL=http://gitea:3000
export GITEA_TOKEN=xxxx

docker compose run --rm app migrate \
  --source bitbucket --dest gitea \
  --mode org --org acme
```

---

### Gitea → GitHub (self-hosted to cloud)

> The destination GitHub org must already exist — GitHub does not allow API-based org creation.

```bash
docker compose run --rm app migrate \
  --source gitea --dest github \
  --mode org --org my-company
```

---

### Filtering

Only migrate Python repos tagged `ml` whose names end in `-model`:

```bash
docker compose run --rm app migrate \
  --source github --dest gitea \
  --mode org --org acme \
  --filter-language python \
  --filter-topic ml \
  --filter-name "*-model"
```

Filters are ANDed — a repo must match all specified filters to be included.

Skip specific repos by name:

```bash
docker compose run --rm app migrate \
  --source github --dest gitea \
  --mode org --org acme \
  --ignore-repos "scratch,wip-project,old-monolith"
```

---

### Git LFS

For orgs that have repos using Git LFS:

```bash
docker compose run --rm app migrate \
  --source github --dest gitea \
  --mode org --org acme \
  --lfs
```

---

### Mirror Releases

Copy releases and their uploaded assets alongside the code:

```bash
docker compose run --rm app migrate \
  --source github --dest gitea \
  --mode org --org acme \
  --include-releases
```

---

### Disable CI/CD After Migration

Prevent workflows from triggering on the destination immediately after import:

```bash
docker compose run --rm app migrate \
  --source github --dest gitea \
  --mode org --org acme \
  --disable-workflows
```

---

### Orphan Cleanup

After migrating, remove repos from the destination that no longer exist in the source:

```bash
# Preview what would be removed
docker compose run --rm app migrate \
  --source github --dest gitea \
  --mode org --org acme \
  --cleanup-action archive --dry-run

# Archive them (sets repos as archived, does not delete)
docker compose run --rm app migrate \
  --source github --dest gitea \
  --mode org --org acme \
  --cleanup-action archive

# Delete them permanently
docker compose run --rm app migrate \
  --source github --dest gitea \
  --mode org --org acme \
  --cleanup-action delete
```

---

### Dry Run

Always a good idea before a large migration. Phases 1–3 (fetch, filter, resume-check) run in full — the output shows exactly what would be migrated, what already exists, and what would be skipped by filters. Nothing is written.

```bash
docker compose run --rm app migrate \
  --source github --dest gitea \
  --mode org --org acme \
  --dry-run
```

---

### Resuming After a Failure

Re-run the exact same command. The tool checks the destination before each migration — repos that already exist are skipped with `SKIPPED`. Only repos that did not make it will be retried.

---

### Deleting an Org

```bash
# Preview
docker compose run --rm app delete --dest gitea --org acme --dry-run

# Interactive (prompts you to type the org name to confirm)
docker compose run --rm app delete --dest gitea --org acme

# Non-interactive (for CI/CD)
docker compose run --rm app delete --dest gitea --org acme --force
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

The process exits with code `1` if any repos failed, making it scriptable.

---

## Troubleshooting

### HTTP 422 — Validation Failed (Gitea / Forgejo)

Gitea and Forgejo block migrations from domains not on their allowlist.

**Fix:** Add the source domain to your `app.ini`:

```ini
[migrations]
ALLOWED_DOMAINS = github.com,gitlab.com,bitbucket.org
```

Restart Gitea/Forgejo after editing `app.ini`.

### HTTP 403 / 429 — Rate Limited

The tool retries automatically with exponential backoff (up to 5 attempts, 10-second initial delay). For persistent rate limits on GitHub, ensure `GITHUB_TOKEN` is set — authenticated requests get 5,000 req/hour vs 60 unauthenticated.

### Private repos not appearing

Ensure the token for the source platform has read access to private repos. For GitHub, `GITHUB_TOKEN` must have the `repo` scope. For GitLab, the token needs `read_repository`. For Bitbucket, the app password needs **Repositories: Read**.

### GitHub org does not exist (422 / SystemExit)

GitHub organisations cannot be created via API. Create the destination org manually in GitHub first, then run the migration.

### Gitea / Forgejo org created with wrong visibility

Pass `--visibility private` (or `public`) explicitly. The default is `public`.

---

## Project Structure

```
github2gitea/
├── adapters/
│   ├── __init__.py      # Adapter registry
│   ├── base.py          # Repo, MigrationResult dataclasses + BaseAdapter ABC
│   ├── github.py        # GitHub adapter (source + destination)
│   ├── gitea.py         # Gitea adapter (source + destination)
│   ├── gitlab.py        # GitLab adapter (source + destination)
│   ├── bitbucket.py     # Bitbucket adapter (source + destination)
│   └── forgejo.py       # Forgejo adapter (destination, inherits Gitea)
└── core/
    ├── http.py          # Link header pagination + exponential backoff
    ├── filters.py       # Repo filtering (name glob, language, topic, ignore list)
    ├── parallel.py      # Auto-scaling ThreadPoolExecutor
    └── migrator.py      # Migration pipeline orchestrator
main.py                  # CLI entry point
```

Want to add a new platform? See [CONTRIBUTING.md](CONTRIBUTING.md).

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Security

See [SECURITY.md](SECURITY.md) for how to report vulnerabilities.

## License

[MIT](LICENSE)
