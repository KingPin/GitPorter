from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, TypeVar

T = TypeVar("T")
R = TypeVar("R")


def worker_count(repo_count: int) -> int:
    """Auto-scale worker count based on number of repos.

    < 5 repos  → 1 worker (sequential)
    5-20 repos → 3 workers
    > 20 repos → min(repo_count // 5, 10), capped at 10
    """
    if repo_count < 5:
        return 1
    if repo_count <= 20:
        return 3
    return min(repo_count // 5, 10)


def run_parallel(fn: Callable[[T], R], items: list[T]) -> list[R]:
    """Run fn over items using an auto-scaled thread pool. Order of results is not guaranteed."""
    n = worker_count(len(items))
    if n == 1:
        return [fn(item) for item in items]
    with ThreadPoolExecutor(max_workers=n) as executor:
        futures = {executor.submit(fn, item): item for item in items}
        return [f.result() for f in as_completed(futures)]
