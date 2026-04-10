# Design: Python Migration Tool (github2gitea v2)

**Date:** 2026-04-10  
**Status:** Approved

## Overview

Rewrite the existing bash migration script as a Python tool using a plugin/adapter pattern. The goal is to support multi-source, multi-destination repo migrations (GitHub, GitLab, Bitbucket → Gitea, and eventually bidirectional) with dry run, filtering, parallel migrations, resume-on-failure, and rich logging.

---

## Project Structure

```
github2gitea/
├── main.py                  # CLI entry point (argparse subcommands)
├── adapters/
│   ├── base.py              # Abstract base class + shared Repo dataclass + MigrationResult
│   ├── github.py            # GitHub adapter
│   ├── gitea.py             # Gitea adapter (source + destination + delete_org)
│   ├── gitlab.py            # GitLab adapter (stub)
│   └── bitbucket.py         # Bitbucket adapter (stub)
├── core/
│   ├── migrator.py          # Orchestrates fetch → filter → resume-check → migrate → summary
│   ├── filters.py           # name/language/topic filtering logic
│   └── parallel.py          # auto-scaling ThreadPoolExecutor logic
└── requirements.txt         # requests, rich
```

The existing `delete_gitea_org.sh` is retired — delete is a first-class operation on the Gitea adapter.

---

## Adapter Interface & Shared Data Model

### `Repo` dataclass

```python
@dataclass
class Repo:
    name: str
    clone_url: str
    description: str
    private: bool
    owner: str
    topics: list[str]
    language: str
    source_type: str       # "github", "gitlab", "bitbucket", "gitea"
```

### `BaseAdapter` abstract class

```python
class BaseAdapter(ABC):
    @abstractmethod
    def list_repos(self, mode: str, user: str = None, org: str = None) -> list[Repo]:
        """Fetch repos — handles pagination internally via Link header"""

    @abstractmethod
    def create_mirror(self, repo: Repo, dest_org: str = None) -> MigrationResult:
        """Create a mirror of repo in this adapter's platform"""

    @abstractmethod
    def repo_exists(self, repo_name: str, owner: str) -> bool:
        """Check if repo already exists — used for resume-on-failure"""

    @abstractmethod
    def delete_org(self, org: str, force: bool = False, dry_run: bool = False) -> None:
        """Delete org and all its repos — Gitea only, others raise NotImplementedError"""
```

### `MigrationResult` dataclass

```python
@dataclass
class MigrationResult:
    repo_name: str
    status: Literal["MIGRATED", "SKIPPED", "FAILED"]
    reason: str = ""
```

Pagination is handled inside each adapter using the `Link: <url>; rel="next"` response header — no fragile page-number counting.

---

## Migration Pipeline

`migrator.py` runs five phases in order:

```
1. FETCH    — source_adapter.list_repos() → raw list
2. FILTER   — filters.apply(repos, name=, language=, topic=) → filtered list
3. RESUME   — dest_adapter.repo_exists() per repo → partition into skip/migrate sets
4. MIGRATE  — parallel workers call dest_adapter.create_mirror()
5. SUMMARY  — rich table: total / migrated / skipped / failed + error reasons
```

**Dry run** gates at phase 4. Phases 1–3 run fully so output shows exactly what would happen.

### Parallelism (auto-scaling)

| Repo count | Workers |
|------------|---------|
| < 5        | 1 (sequential) |
| 5–20       | 3 |
| > 20       | `min(repo_count // 5, 10)` capped at 10 |

Uses `ThreadPoolExecutor` — appropriate for HTTP I/O without async complexity.

### Error Handling

- Per-repo failures are caught, recorded in `MigrationResult`, and never abort the run
- Rate limit backoff (403/429) with exponential backoff lives inside each adapter's HTTP layer
- HTTP 422 (Allowed Domains) surfaces as a `ConfigurationError` with an actionable fix message
- HTTP 409 (repo already exists) → `SKIPPED`
- Final summary always prints even if every repo failed

---

## CLI Design

### `migrate` subcommand

```bash
python main.py migrate \
  --source github --dest gitea \
  --mode org|user|star|repo \
  --org <org> \
  --user <user> \
  --visibility public|private \
  --repo <url> \
  --filter-name "pattern" \
  --filter-language python \
  --filter-topic ml \
  --dry-run \
  --parallel auto
```

### `delete` subcommand

```bash
python main.py delete \
  --dest gitea --org <org> \
  [--dry-run] [--force]
```

Credentials remain as environment variables:

| Variable        | Used by        |
|-----------------|----------------|
| `GITHUB_TOKEN`  | GitHub adapter |
| `ACCESS_TOKEN`  | Gitea adapter  |
| `GITEA_URL`     | Gitea adapter  |
| `GITLAB_TOKEN`  | GitLab adapter |
| `BITBUCKET_*`   | Bitbucket adapter |

---

## Logging & Output

Uses `rich` for all output:

- Live progress bar during migration (repo N of M)
- Per-repo status lines: `[MIGRATED]`, `[SKIPPED]`, `[FAILED]`
- `[DRY RUN]` prefix on every line when `--dry-run` is active
- Final summary table:

```
┌──────────┬───────┐
│ Status   │ Count │
├──────────┼───────┤
│ Migrated │  47   │
│ Skipped  │   3   │
│ Failed   │   1   │
└──────────┴───────┘
Failed repos:
  • some-repo — HTTP 422: github.com not in ALLOWED_DOMAINS
```

---

## Future Upgrade Path

- **Config file (YAML/TOML):** env vars → config file is a non-breaking addition; adapters already read from a dict-like config object
- **New sources:** add a new file in `adapters/`, implement `BaseAdapter` — no changes to pipeline or CLI
- **Bidirectional (Gitea → GitHub):** GitHub adapter implements `create_mirror()` and `repo_exists()` — pipeline unchanged
- **Config-driven execution:** wrap CLI args in a config loader that reads YAML, feeds same argparse namespace

---

## Tasks

- T1: Set up project structure and `base.py`
- T2: Implement `github.py` adapter (list_repos with Link header pagination, repo_exists)
- T3: Implement `gitea.py` adapter (create_mirror, repo_exists, delete_org)
- T4: Implement `core/filters.py`
- T5: Implement `core/parallel.py`
- T6: Implement `core/migrator.py` (full pipeline)
- T7: Implement `main.py` CLI (argparse, subcommands, env var validation)
- T8: Stub `gitlab.py` and `bitbucket.py`
- T9: Retire `delete_gitea_org.sh`, update `CLAUDE.md`
