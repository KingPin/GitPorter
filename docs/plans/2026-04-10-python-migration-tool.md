# Python Migration Tool Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:executing-plans to implement this plan task-by-task.

**Goal:** Rewrite the GitHub→Gitea bash migration script as a Python tool using an adapter pattern that supports multiple sources (GitHub, GitLab, Bitbucket), multiple destinations (Gitea), dry run, repo filtering, parallel migrations, resume-on-failure, and rich terminal output.

**Architecture:** Plugin/adapter pattern — each platform implements a `BaseAdapter` interface. A pipeline orchestrator (`migrator.py`) runs fetch → filter → resume-check → migrate → summary phases. The CLI (`main.py`) routes between adapters via argparse subcommands. `delete_org` is a first-class method on the Gitea adapter — the bash delete script is retired.

**Tech Stack:** Python 3.10+, `requests`, `rich`, `pytest`

---

### Task 1: Project scaffold + base data model

**Files:**
- Create: `github2gitea/__init__.py`
- Create: `github2gitea/adapters/__init__.py`
- Create: `github2gitea/adapters/base.py`
- Create: `github2gitea/core/__init__.py`
- Create: `requirements.txt`
- Create: `tests/__init__.py`
- Create: `tests/adapters/__init__.py`
- Create: `tests/core/__init__.py`

**Step 1: Write the failing test**

```python
# tests/adapters/test_base.py
from github2gitea.adapters.base import Repo, MigrationResult, BaseAdapter
import pytest

def test_repo_dataclass_defaults():
    repo = Repo(name="my-repo", clone_url="https://github.com/user/my-repo",
                description="test", private=False, owner="user")
    assert repo.topics == []
    assert repo.language == ""
    assert repo.source_type == ""

def test_migration_result_statuses():
    r = MigrationResult(repo_name="my-repo", status="MIGRATED")
    assert r.reason == ""
    r2 = MigrationResult(repo_name="my-repo", status="FAILED", reason="HTTP 500")
    assert r2.reason == "HTTP 500"

def test_base_adapter_cannot_instantiate():
    with pytest.raises(TypeError):
        BaseAdapter()
```

**Step 2: Run to verify failure**
```
pytest tests/adapters/test_base.py -v
```
Expected: `ModuleNotFoundError`

**Step 3: Create scaffold**

Create all `__init__.py` files (empty).

`requirements.txt`:
```
requests>=2.31.0
rich>=13.0.0
pytest>=8.0.0
```

`github2gitea/adapters/base.py`:
```python
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
```

**Step 4: Run test to verify it passes**
```
pytest tests/adapters/test_base.py -v
```
Expected: 3 PASSED

**Step 5: Commit**
```bash
git add github2gitea/ tests/ requirements.txt
git commit -m "feat: add project scaffold and base adapter interface"
```

---

### Task 2: HTTP utility layer

**Files:**
- Create: `github2gitea/core/http.py`
- Create: `tests/core/test_http.py`

Shared HTTP helpers used by all adapters: Link header parsing and exponential backoff on rate limits.

**Step 1: Write the failing tests**

```python
# tests/core/test_http.py
from github2gitea.core.http import parse_next_link

def test_parse_next_link_present():
    header = '<https://api.github.com/repos?page=2>; rel="next", <https://api.github.com/repos?page=5>; rel="last"'
    assert parse_next_link(header) == "https://api.github.com/repos?page=2"

def test_parse_next_link_absent():
    header = '<https://api.github.com/repos?page=4>; rel="prev"'
    assert parse_next_link(header) is None

def test_parse_next_link_empty():
    assert parse_next_link("") is None
    assert parse_next_link(None) is None
```

**Step 2: Run to verify failure**
```
pytest tests/core/test_http.py -v
```
Expected: `ImportError`

**Step 3: Implement `github2gitea/core/http.py`**

```python
import re
import time
import logging
import requests

logger = logging.getLogger(__name__)

_LINK_RE = re.compile(r'<([^>]+)>;\s*rel="next"')


def parse_next_link(link_header: str | None) -> str | None:
    """Extract the 'next' URL from a Link response header."""
    if not link_header:
        return None
    m = _LINK_RE.search(link_header)
    return m.group(1) if m else None


def http_get_with_backoff(
    session: requests.Session,
    url: str,
    max_retries: int = 5,
    initial_delay: float = 10.0,
    **kwargs,
) -> requests.Response:
    """GET a URL with exponential backoff on 403/429 rate limits."""
    delay = initial_delay
    for attempt in range(1, max_retries + 1):
        response = session.get(url, **kwargs)
        if response.status_code == 200:
            return response
        if response.status_code in (403, 429):
            logger.warning(
                "Rate limited (HTTP %s). Sleeping %.0fs (attempt %d/%d)...",
                response.status_code, delay, attempt, max_retries,
            )
            time.sleep(delay)
            delay *= 2
        else:
            response.raise_for_status()
    raise requests.HTTPError(f"Exceeded {max_retries} retries for {url}")
```

**Step 4: Run tests**
```
pytest tests/core/test_http.py -v
```
Expected: 3 PASSED

**Step 5: Commit**
```bash
git add github2gitea/core/http.py tests/core/test_http.py
git commit -m "feat: add HTTP utility layer with Link header parsing and backoff"
```

---

### Task 3: GitHub adapter

**Files:**
- Create: `github2gitea/adapters/github.py`
- Create: `tests/adapters/test_github.py`

Implements `list_repos` for all four modes (org, user-owner, user-all, star) using Link header pagination. `create_mirror` and `delete_org` raise `NotImplementedError` (GitHub as destination is future work).

**Step 1: Write failing tests**

```python
# tests/adapters/test_github.py
from unittest.mock import MagicMock
from github2gitea.adapters.github import GitHubAdapter
import pytest

SAMPLE_REPO_JSON = {
    "name": "my-repo",
    "clone_url": "https://github.com/user/my-repo.git",
    "description": "A test repo",
    "visibility": "public",
    "private": False,
    "owner": {"login": "user"},
    "topics": ["python", "tool"],
    "language": "Python",
}

@pytest.fixture
def adapter():
    return GitHubAdapter(token="fake-token")

def test_normalize_repo(adapter):
    repo = adapter._normalize(SAMPLE_REPO_JSON)
    assert repo.name == "my-repo"
    assert repo.private is False
    assert repo.topics == ["python", "tool"]
    assert repo.language == "Python"
    assert repo.source_type == "github"

def test_create_mirror_raises(adapter):
    with pytest.raises(NotImplementedError):
        adapter.create_mirror(MagicMock())

def test_delete_org_raises(adapter):
    with pytest.raises(NotImplementedError):
        adapter.delete_org("some-org")
```

**Step 2: Run to verify failure**
```
pytest tests/adapters/test_github.py -v
```
Expected: `ImportError`

**Step 3: Implement `github2gitea/adapters/github.py`**

```python
import logging
import requests
from .base import BaseAdapter, Repo, MigrationResult
from ..core.http import parse_next_link, http_get_with_backoff

logger = logging.getLogger(__name__)
GITHUB_API = "https://api.github.com"


class GitHubAdapter(BaseAdapter):
    def __init__(self, token: str = None, api_delay: float = 2.0):
        self._session = requests.Session()
        if token:
            self._session.headers["Authorization"] = f"Bearer {token}"
        self._session.headers["Accept"] = "application/vnd.github+json"
        self._api_delay = api_delay

    def list_repos(self, mode: str, user: str = None, org: str = None) -> list[Repo]:
        if mode == "org":
            return self._paginate(f"{GITHUB_API}/orgs/{org}/repos")
        elif mode == "user":
            if org:
                return self._paginate(f"{GITHUB_API}/users/{user}/repos")
            else:
                return self._paginate(f"{GITHUB_API}/user/repos", params={"affiliation": "owner"})
        elif mode == "star":
            return self._paginate(f"{GITHUB_API}/users/{user}/starred")
        elif mode == "repo":
            raise ValueError("Use fetch_one_repo() for single-repo mode")
        else:
            raise ValueError(f"Unknown mode: {mode}")

    def fetch_one_repo(self, repo_url: str) -> Repo:
        path = repo_url.replace("https://github.com/", "").rstrip(".git")
        r = http_get_with_backoff(self._session, f"{GITHUB_API}/repos/{path}")
        return self._normalize(r.json())

    def repo_exists(self, repo_name: str, owner: str) -> bool:
        r = self._session.get(f"{GITHUB_API}/repos/{owner}/{repo_name}")
        return r.status_code == 200

    def create_mirror(self, repo: Repo, dest_org: str = None) -> MigrationResult:
        raise NotImplementedError("GitHub as mirror destination is not yet supported")

    def delete_org(self, org: str, force: bool = False, dry_run: bool = False) -> None:
        raise NotImplementedError("GitHub org deletion is not supported")

    def _paginate(self, url: str, params: dict = None) -> list[Repo]:
        repos = []
        params = {**(params or {}), "per_page": 100}
        while url:
            response = http_get_with_backoff(self._session, url, params=params)
            data = response.json()
            if not data:
                break
            repos.extend(self._normalize(r) for r in data)
            url = parse_next_link(response.headers.get("Link"))
            params = {}
        return repos

    def _normalize(self, data: dict) -> Repo:
        return Repo(
            name=data["name"],
            clone_url=data["clone_url"],
            description=(data.get("description") or "")[:255],
            private=data.get("visibility") == "private" or data.get("private", False),
            owner=data["owner"]["login"],
            topics=data.get("topics", []),
            language=data.get("language") or "",
            source_type="github",
        )
```

**Step 4: Run tests**
```
pytest tests/adapters/test_github.py -v
```
Expected: 3 PASSED

**Step 5: Commit**
```bash
git add github2gitea/adapters/github.py tests/adapters/test_github.py
git commit -m "feat: add GitHub adapter with Link header pagination"
```

---

### Task 4: Gitea adapter

**Files:**
- Create: `github2gitea/adapters/gitea.py`
- Create: `tests/adapters/test_gitea.py`

Implements `create_mirror` (with retry + 409/422 handling), `repo_exists`, `delete_org` (with dry run + force), `ensure_org`, and `get_org_uid`.

**Step 1: Write failing tests**

```python
# tests/adapters/test_gitea.py
from unittest.mock import MagicMock, patch
from github2gitea.adapters.gitea import GiteaAdapter
from github2gitea.adapters.base import Repo
import pytest

SAMPLE_REPO = Repo(
    name="my-repo", clone_url="https://github.com/user/my-repo.git",
    description="A test repo", private=False, owner="user", source_type="github",
)

@pytest.fixture
def adapter():
    return GiteaAdapter(url="http://gitea:3000", token="fake-token")

def test_repo_exists_true(adapter):
    with patch.object(adapter._session, "get") as mock_get:
        mock_get.return_value.status_code = 200
        assert adapter.repo_exists("my-repo", "user") is True

def test_repo_exists_false(adapter):
    with patch.object(adapter._session, "get") as mock_get:
        mock_get.return_value.status_code = 404
        assert adapter.repo_exists("my-repo", "user") is False

def test_create_mirror_success(adapter):
    with patch.object(adapter._session, "post") as mock_post:
        mock_post.return_value.status_code = 201
        result = adapter.create_mirror(SAMPLE_REPO)
        assert result.status == "MIGRATED"

def test_create_mirror_already_exists(adapter):
    with patch.object(adapter._session, "post") as mock_post:
        mock_post.return_value.status_code = 409
        result = adapter.create_mirror(SAMPLE_REPO)
        assert result.status == "SKIPPED"
        assert "already exists" in result.reason

def test_create_mirror_422_allowed_domains(adapter):
    with patch.object(adapter._session, "post") as mock_post:
        mock_post.return_value.status_code = 422
        result = adapter.create_mirror(SAMPLE_REPO)
        assert result.status == "FAILED"
        assert "ALLOWED_DOMAINS" in result.reason
```

**Step 2: Run to verify failure**
```
pytest tests/adapters/test_gitea.py -v
```
Expected: `ImportError`

**Step 3: Implement `github2gitea/adapters/gitea.py`**

```python
import logging
import time
import requests
from .base import BaseAdapter, Repo, MigrationResult
from ..core.http import parse_next_link

logger = logging.getLogger(__name__)


class GiteaAdapter(BaseAdapter):
    def __init__(self, url: str, token: str, api_delay: float = 1.0):
        self._url = url.rstrip("/")
        self._api_delay = api_delay
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        })

    def list_repos(self, mode: str, user: str = None, org: str = None) -> list[Repo]:
        if mode == "org":
            return self._paginate(f"{self._url}/api/v1/orgs/{org}/repos")
        elif mode == "user":
            return self._paginate(f"{self._url}/api/v1/users/{user}/repos")
        else:
            raise ValueError(f"Unsupported mode for Gitea source: {mode}")

    def repo_exists(self, repo_name: str, owner: str) -> bool:
        r = self._session.get(f"{self._url}/api/v1/repos/{owner}/{repo_name}")
        return r.status_code == 200

    def get_org_uid(self, org: str) -> int:
        r = self._session.get(f"{self._url}/api/v1/orgs/{org}")
        r.raise_for_status()
        return r.json()["id"]

    def get_user_uid(self, username: str) -> int:
        r = self._session.get(f"{self._url}/api/v1/users/{username}")
        r.raise_for_status()
        return r.json()["id"]

    def ensure_org(self, org: str, visibility: str = "public") -> None:
        """Create org if it doesn't exist. 422 = already exists, both are fine."""
        r = self._session.post(
            f"{self._url}/api/v1/orgs",
            json={"username": org, "visibility": visibility},
        )
        if r.status_code not in (201, 422):
            r.raise_for_status()

    def create_mirror(self, repo: Repo, dest_org: str = None, uid: int = None,
                      auth_username: str = None, auth_token: str = None) -> MigrationResult:
        payload = {
            "clone_addr": repo.clone_url,
            "repo_name": repo.name,
            "description": repo.description,
            "mirror": True,
            "private": repo.private,
        }
        if uid:
            payload["uid"] = uid
        if repo.private and auth_username and auth_token:
            payload["auth_username"] = auth_username
            payload["auth_password"] = auth_token

        max_attempts, delay = 3, 5.0
        for attempt in range(1, max_attempts + 1):
            r = self._session.post(f"{self._url}/api/v1/repos/migrate", json=payload)
            if r.status_code in (200, 201):
                time.sleep(self._api_delay)
                return MigrationResult(repo_name=repo.name, status="MIGRATED")
            elif r.status_code == 409:
                return MigrationResult(repo_name=repo.name, status="SKIPPED",
                                       reason="already exists in Gitea")
            elif r.status_code == 422:
                return MigrationResult(
                    repo_name=repo.name, status="FAILED",
                    reason="HTTP 422: Ensure 'github.com' is in ALLOWED_DOMAINS in app.ini [migrations]",
                )
            else:
                logger.warning("Attempt %d/%d failed (HTTP %s). Retrying in %.0fs...",
                               attempt, max_attempts, r.status_code, delay)
                time.sleep(delay)
                delay *= 2

        return MigrationResult(repo_name=repo.name, status="FAILED",
                               reason=f"Failed after {max_attempts} attempts")

    def delete_org(self, org: str, force: bool = False, dry_run: bool = False) -> None:
        repos = self._paginate_names(org)
        if dry_run:
            logger.info("[DRY RUN] Would delete %d repos and org '%s'", len(repos), org)
            for name in repos:
                logger.info("[DRY RUN] Would delete: %s/%s", org, name)
            return

        if not force:
            confirm = input(f"Type '{org}' to confirm deletion: ").strip()
            if confirm != org:
                raise SystemExit(f"Aborted: '{confirm}' != '{org}'")

        for name in repos:
            r = self._session.delete(f"{self._url}/api/v1/repos/{org}/{name}")
            if r.status_code not in (204, 200, 404):
                logger.warning("Failed to delete %s/%s: HTTP %s", org, name, r.status_code)
            time.sleep(0.5)

        r = self._session.delete(f"{self._url}/api/v1/orgs/{org}")
        if r.status_code not in (204, 200, 404):
            r.raise_for_status()

    def _paginate(self, url: str) -> list[Repo]:
        repos, params = [], {"limit": 50}
        while url:
            r = self._session.get(url, params=params)
            r.raise_for_status()
            data = r.json()
            if not data:
                break
            repos.extend(self._normalize(item) for item in data)
            url = parse_next_link(r.headers.get("Link"))
            params = {}
        return repos

    def _paginate_names(self, org: str) -> list[str]:
        names, params = [], {"limit": 50}
        url = f"{self._url}/api/v1/orgs/{org}/repos"
        while url:
            r = self._session.get(url, params=params)
            if r.status_code == 404:
                raise SystemExit(f"Organization '{org}' not found")
            r.raise_for_status()
            data = r.json()
            if not data:
                break
            names.extend(item["name"] for item in data)
            url = parse_next_link(r.headers.get("Link"))
            params = {}
        return names

    def _normalize(self, data: dict) -> Repo:
        return Repo(
            name=data["name"],
            clone_url=data.get("clone_url", ""),
            description=(data.get("description") or "")[:255],
            private=data.get("private", False),
            owner=data.get("owner", {}).get("login", ""),
            topics=data.get("topics", []),
            language=data.get("language") or "",
            source_type="gitea",
        )
```

**Step 4: Run tests**
```
pytest tests/adapters/test_gitea.py -v
```
Expected: 5 PASSED

**Step 5: Commit**
```bash
git add github2gitea/adapters/gitea.py tests/adapters/test_gitea.py
git commit -m "feat: add Gitea adapter with mirror creation, resume check, org deletion"
```

---

### Task 5: Filters

**Files:**
- Create: `github2gitea/core/filters.py`
- Create: `tests/core/test_filters.py`

**Step 1: Write failing tests**

```python
# tests/core/test_filters.py
from github2gitea.core.filters import apply_filters
from github2gitea.adapters.base import Repo

def make_repo(**kwargs):
    defaults = dict(name="repo", clone_url="", description="", private=False,
                    owner="user", topics=[], language="", source_type="github")
    return Repo(**{**defaults, **kwargs})

def test_filter_by_name_glob():
    repos = [make_repo(name="foo-service"), make_repo(name="bar-service"), make_repo(name="infra")]
    result = apply_filters(repos, name_pattern="*-service")
    assert [r.name for r in result] == ["foo-service", "bar-service"]

def test_filter_by_language_case_insensitive():
    repos = [make_repo(language="Python"), make_repo(language="Go"), make_repo(language="Python")]
    result = apply_filters(repos, language="python")
    assert len(result) == 2

def test_filter_by_topic():
    repos = [make_repo(topics=["ml", "python"]), make_repo(topics=["web"]), make_repo(topics=["ml"])]
    result = apply_filters(repos, topic="ml")
    assert len(result) == 2

def test_multiple_filters_are_anded():
    repos = [
        make_repo(name="ml-service", language="Python", topics=["ml"]),
        make_repo(name="ml-service", language="Go", topics=["ml"]),
    ]
    result = apply_filters(repos, name_pattern="ml-*", language="python")
    assert len(result) == 1

def test_no_filters_returns_all():
    repos = [make_repo(), make_repo(name="other")]
    assert apply_filters(repos) == repos
```

**Step 2: Run to verify failure**
```
pytest tests/core/test_filters.py -v
```
Expected: `ImportError`

**Step 3: Implement `github2gitea/core/filters.py`**

```python
import fnmatch
from github2gitea.adapters.base import Repo


def apply_filters(
    repos: list[Repo],
    name_pattern: str = None,
    language: str = None,
    topic: str = None,
) -> list[Repo]:
    """Filter repos by name glob, language, and/or topic. All filters are ANDed."""
    result = repos
    if name_pattern:
        result = [r for r in result if fnmatch.fnmatch(r.name, name_pattern)]
    if language:
        lang = language.lower()
        result = [r for r in result if (r.language or "").lower() == lang]
    if topic:
        result = [r for r in result if topic in r.topics]
    return result
```

**Step 4: Run tests**
```
pytest tests/core/test_filters.py -v
```
Expected: 5 PASSED

**Step 5: Commit**
```bash
git add github2gitea/core/filters.py tests/core/test_filters.py
git commit -m "feat: add repo filters (name glob, language, topic)"
```

---

### Task 6: Parallel executor

**Files:**
- Create: `github2gitea/core/parallel.py`
- Create: `tests/core/test_parallel.py`

**Step 1: Write failing tests**

```python
# tests/core/test_parallel.py
from github2gitea.core.parallel import worker_count, run_parallel

def test_worker_count_tiny():
    assert worker_count(3) == 1

def test_worker_count_medium():
    assert worker_count(10) == 3

def test_worker_count_large():
    assert worker_count(50) == 10  # capped at 10

def test_worker_count_boundaries():
    assert worker_count(4) == 1
    assert worker_count(5) == 3
    assert worker_count(20) == 3
    assert worker_count(21) > 3

def test_run_parallel_collects_results():
    results = run_parallel(lambda x: x * 2, [1, 2, 3, 4, 5])
    assert sorted(results) == [2, 4, 6, 8, 10]
```

**Step 2: Run to verify failure**
```
pytest tests/core/test_parallel.py -v
```
Expected: `ImportError`

**Step 3: Implement `github2gitea/core/parallel.py`**

```python
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, TypeVar

T = TypeVar("T")
R = TypeVar("R")


def worker_count(repo_count: int) -> int:
    """Auto-scale worker count based on number of repos."""
    if repo_count < 5:
        return 1
    if repo_count <= 20:
        return 3
    return min(repo_count // 5, 10)


def run_parallel(fn: Callable[[T], R], items: list[T]) -> list[R]:
    """Run fn over items using an auto-scaled thread pool. Order not guaranteed."""
    n = worker_count(len(items))
    if n == 1:
        return [fn(item) for item in items]
    with ThreadPoolExecutor(max_workers=n) as executor:
        futures = {executor.submit(fn, item): item for item in items}
        return [f.result() for f in as_completed(futures)]
```

**Step 4: Run tests**
```
pytest tests/core/test_parallel.py -v
```
Expected: 5 PASSED

**Step 5: Commit**
```bash
git add github2gitea/core/parallel.py tests/core/test_parallel.py
git commit -m "feat: add auto-scaling parallel executor"
```

---

### Task 7: Migration pipeline (migrator.py)

**Files:**
- Create: `github2gitea/core/migrator.py`
- Create: `tests/core/test_migrator.py`

**Step 1: Write failing tests**

```python
# tests/core/test_migrator.py
from unittest.mock import MagicMock
from github2gitea.core.migrator import Migrator
from github2gitea.adapters.base import Repo, MigrationResult

def make_repo(name, language="Python"):
    return Repo(name=name, clone_url=f"https://github.com/user/{name}.git",
                description="", private=False, owner="user",
                topics=[], language=language, source_type="github")

def make_source(*names):
    m = MagicMock()
    m.list_repos.return_value = [make_repo(n) for n in names]
    return m

def make_dest(existing=None):
    m = MagicMock()
    existing = existing or []
    m.repo_exists.side_effect = lambda name, owner: name in existing
    m.create_mirror.side_effect = lambda repo, **kw: MigrationResult(repo.name, "MIGRATED")
    return m

def test_dry_run_skips_migration():
    migrator = Migrator(make_source("a", "b"), make_dest(), dry_run=True)
    results = migrator.run(mode="user", user="user")
    assert all(r.status == "SKIPPED" for r in results)
    assert all("dry run" in r.reason for r in results)

def test_existing_repos_skipped():
    migrator = Migrator(make_source("a", "b", "c"), make_dest(existing=["a"]))
    results = migrator.run(mode="user", user="user")
    assert len([r for r in results if r.status == "SKIPPED"]) == 1
    assert len([r for r in results if r.status == "MIGRATED"]) == 2

def test_language_filter_applied():
    source = MagicMock()
    source.list_repos.return_value = [make_repo("py-repo", "Python"), make_repo("go-repo", "Go")]
    migrator = Migrator(source, make_dest(), language="go")
    results = migrator.run(mode="user", user="user")
    assert len(results) == 1
    assert results[0].repo_name == "go-repo"
```

**Step 2: Run to verify failure**
```
pytest tests/core/test_migrator.py -v
```
Expected: `ImportError`

**Step 3: Implement `github2gitea/core/migrator.py`**

```python
import logging
from github2gitea.adapters.base import BaseAdapter, Repo, MigrationResult
from github2gitea.core.filters import apply_filters
from github2gitea.core.parallel import run_parallel

logger = logging.getLogger(__name__)


class Migrator:
    def __init__(
        self,
        source: BaseAdapter,
        dest: BaseAdapter,
        dry_run: bool = False,
        name_pattern: str = None,
        language: str = None,
        topic: str = None,
        dest_org: str = None,
        dest_uid: int = None,
        auth_username: str = None,
        auth_token: str = None,
    ):
        self._source = source
        self._dest = dest
        self._dry_run = dry_run
        self._filter_kwargs = dict(name_pattern=name_pattern, language=language, topic=topic)
        self._dest_org = dest_org
        self._dest_uid = dest_uid
        self._auth_username = auth_username
        self._auth_token = auth_token

    def run(self, mode: str, user: str = None, org: str = None,
            repo_url: str = None) -> list[MigrationResult]:
        # Phase 1: Fetch
        logger.info("Fetching repos from source...")
        if mode == "repo" and hasattr(self._source, "fetch_one_repo"):
            repos = [self._source.fetch_one_repo(repo_url)]
        else:
            repos = self._source.list_repos(mode=mode, user=user, org=org)
        logger.info("Fetched %d repos.", len(repos))

        # Phase 2: Filter
        repos = apply_filters(repos, **self._filter_kwargs)
        logger.info("%d repos after filtering.", len(repos))

        # Phase 3: Resume check
        owner = self._dest_org or user or org
        to_migrate, results = [], []
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
```

**Step 4: Run tests**
```
pytest tests/core/test_migrator.py -v
```
Expected: 3 PASSED

**Step 5: Run full test suite**
```
pytest tests/ -v
```
Expected: all green

**Step 6: Commit**
```bash
git add github2gitea/core/migrator.py tests/core/test_migrator.py
git commit -m "feat: add migration pipeline (fetch/filter/resume/migrate)"
```

---

### Task 8: CLI (main.py)

**Files:**
- Create: `main.py`

No unit tests — thin glue code. Smoke-tested via `--dry-run`.

**Step 1: Implement `main.py`**

```python
#!/usr/bin/env python3
import argparse
import logging
import os
import sys

from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

from github2gitea.adapters.github import GitHubAdapter
from github2gitea.adapters.gitea import GiteaAdapter
from github2gitea.core.migrator import Migrator

console = Console()


def get_env(name: str, required: bool = True) -> str:
    val = os.environ.get(name)
    if required and not val:
        console.print(f"[red]Error:[/red] Environment variable {name} is not set.")
        sys.exit(1)
    return val or ""


def setup_logging(verbose: bool = False):
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(message)s",
        handlers=[RichHandler(rich_tracebacks=True, show_path=False)],
    )


def print_summary(results):
    migrated = sum(1 for r in results if r.status == "MIGRATED")
    skipped  = sum(1 for r in results if r.status == "SKIPPED")
    failed   = sum(1 for r in results if r.status == "FAILED")

    table = Table(title="Migration Summary")
    table.add_column("Status", style="bold")
    table.add_column("Count", justify="right")
    table.add_row("[green]Migrated[/green]", str(migrated))
    table.add_row("[yellow]Skipped[/yellow]",  str(skipped))
    table.add_row("[red]Failed[/red]",    str(failed))
    console.print(table)

    failures = [r for r in results if r.status == "FAILED"]
    if failures:
        console.print("\n[red]Failed repos:[/red]")
        for r in failures:
            console.print(f"  • {r.repo_name} — {r.reason}")


def cmd_migrate(args):
    setup_logging(args.verbose)
    gitea_url    = get_env("GITEA_URL")
    access_token = get_env("ACCESS_TOKEN")
    github_token = get_env("GITHUB_TOKEN", required=False)

    source_map = {"github": lambda: GitHubAdapter(token=github_token)}
    dest_map   = {"gitea":  lambda: GiteaAdapter(url=gitea_url, token=access_token)}

    if args.source not in source_map:
        console.print(f"[red]Unknown source:[/red] {args.source}"); sys.exit(1)
    if args.dest not in dest_map:
        console.print(f"[red]Unknown destination:[/red] {args.dest}"); sys.exit(1)

    source = source_map[args.source]()
    dest   = dest_map[args.dest]()

    dest_uid = None
    if args.org:
        dest.ensure_org(args.org, visibility=args.visibility or "public")
        dest_uid = dest.get_org_uid(args.org)

    if args.dry_run:
        console.print("[bold yellow][DRY RUN][/bold yellow] No repos will be migrated.")

    migrator = Migrator(
        source=source, dest=dest, dry_run=args.dry_run,
        name_pattern=args.filter_name, language=args.filter_language,
        topic=args.filter_topic, dest_org=args.org, dest_uid=dest_uid,
        auth_username=args.user, auth_token=github_token,
    )
    results = migrator.run(mode=args.mode, user=args.user, org=args.org, repo_url=args.repo)
    print_summary(results)
    if any(r.status == "FAILED" for r in results):
        sys.exit(1)


def cmd_delete(args):
    setup_logging(args.verbose)
    adapter = GiteaAdapter(url=get_env("GITEA_URL"), token=get_env("ACCESS_TOKEN"))
    adapter.delete_org(org=args.org, force=args.force, dry_run=args.dry_run)


def build_parser():
    parser = argparse.ArgumentParser(prog="github2gitea",
                                     description="Mirror repos between Git platforms.")
    parser.add_argument("--verbose", "-v", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    m = sub.add_parser("migrate", help="Mirror repos from source to destination")
    m.add_argument("--source",  required=True, choices=["github", "gitlab", "bitbucket"])
    m.add_argument("--dest",    required=True, choices=["gitea"])
    m.add_argument("--mode",    required=True, choices=["org", "user", "star", "repo"])
    m.add_argument("--org",  "-o")
    m.add_argument("--user", "-u")
    m.add_argument("--visibility", choices=["public", "private"], default="public")
    m.add_argument("--repo", "-r")
    m.add_argument("--filter-name")
    m.add_argument("--filter-language")
    m.add_argument("--filter-topic")
    m.add_argument("--dry-run", action="store_true")
    m.set_defaults(func=cmd_migrate)

    d = sub.add_parser("delete", help="Delete a Gitea org and all its repos")
    d.add_argument("--dest", required=True, choices=["gitea"])
    d.add_argument("--org", "-o", required=True)
    d.add_argument("--dry-run", action="store_true")
    d.add_argument("--force",   action="store_true")
    d.set_defaults(func=cmd_delete)

    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()
    args.func(args)
```

**Step 2: Smoke test**
```bash
export GITEA_URL=http://localhost:3000
export ACCESS_TOKEN=test
export GITHUB_TOKEN=test
python main.py migrate --source github --dest gitea --mode user --user octocat --dry-run
```
Expected: `[DRY RUN]` output, summary table, exit 0

**Step 3: Commit**
```bash
git add main.py
git commit -m "feat: add CLI with migrate and delete subcommands"
```

---

### Task 9: Adapter stubs (GitLab, Bitbucket)

**Files:**
- Create: `github2gitea/adapters/gitlab.py`
- Create: `github2gitea/adapters/bitbucket.py`

Each stub raises `NotImplementedError` with a message pointing to `base.py`.

**Step 1: Create `github2gitea/adapters/gitlab.py`**

```python
from .base import BaseAdapter, Repo, MigrationResult


class GitLabAdapter(BaseAdapter):
    """GitLab source adapter — not yet implemented. See adapters/base.py for the interface."""

    def list_repos(self, mode: str, user: str = None, org: str = None) -> list[Repo]:
        raise NotImplementedError("GitLab adapter is not yet implemented.")

    def create_mirror(self, repo: Repo, dest_org: str = None) -> MigrationResult:
        raise NotImplementedError

    def repo_exists(self, repo_name: str, owner: str) -> bool:
        raise NotImplementedError

    def delete_org(self, org: str, force: bool = False, dry_run: bool = False) -> None:
        raise NotImplementedError
```

**Step 2: Create `github2gitea/adapters/bitbucket.py`**

```python
from .base import BaseAdapter, Repo, MigrationResult


class BitbucketAdapter(BaseAdapter):
    """Bitbucket source adapter — not yet implemented. See adapters/base.py for the interface."""

    def list_repos(self, mode: str, user: str = None, org: str = None) -> list[Repo]:
        raise NotImplementedError("Bitbucket adapter is not yet implemented.")

    def create_mirror(self, repo: Repo, dest_org: str = None) -> MigrationResult:
        raise NotImplementedError

    def repo_exists(self, repo_name: str, owner: str) -> bool:
        raise NotImplementedError

    def delete_org(self, org: str, force: bool = False, dry_run: bool = False) -> None:
        raise NotImplementedError
```

**Step 3: Commit**
```bash
git add github2gitea/adapters/gitlab.py github2gitea/adapters/bitbucket.py
git commit -m "feat: add GitLab and Bitbucket adapter stubs"
```

---

### Task 10: Retire bash scripts and update CLAUDE.md

**Files:**
- Delete: `github-mirror-2-gitea.sh`
- Delete: `delete_gitea_org.sh`
- Modify: `CLAUDE.md`

**Step 1: Remove bash scripts**
```bash
git rm github-mirror-2-gitea.sh delete_gitea_org.sh
```

**Step 2: Rewrite CLAUDE.md**

Replace the Usage section to reflect the Python CLI. Keep env vars section. New commands:

```bash
# Install deps
pip install -r requirements.txt

# Migrate
python main.py migrate --source github --dest gitea --mode org -o myorg -v public
python main.py migrate --source github --dest gitea --mode user -u myuser
python main.py migrate --source github --dest gitea --mode user -u myuser -o myorg
python main.py migrate --source github --dest gitea --mode star -u myuser -o myorg
python main.py migrate --source github --dest gitea --mode repo -r <url> -u myuser
python main.py migrate ... --filter-language python --filter-topic ml --dry-run

# Delete org
python main.py delete --dest gitea -o myorg --dry-run
python main.py delete --dest gitea -o myorg
python main.py delete --dest gitea -o myorg --force
```

**Step 3: Run full test suite one final time**
```
pytest tests/ -v
```
Expected: all green

**Step 4: Commit**
```bash
git add CLAUDE.md
git commit -m "chore: retire bash scripts, update CLAUDE.md for Python CLI"
```
