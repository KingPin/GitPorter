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
