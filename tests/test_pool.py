import multiprocessing as mp

import pytest

from redundex.core.pool import CancelledScan, run_jobs


def _double(item):
    return item * 2


def _boom(item):
    if item == 3:
        raise ValueError("bad item")
    return item + 1


def test_run_jobs_maps_function():
    results, problems = run_jobs(_double, [1, 2, 3], workers=2)
    assert sorted(results) == [2, 4, 6]
    assert problems == []


def test_run_jobs_collects_failures_as_problems():
    results, problems = run_jobs(_boom, [1, 2, 3, 4], workers=2)
    assert sorted(results) == [2, 3, 5]
    assert len(problems) == 1 and "bad item" in problems[0]["error"]
    assert problems[0]["item"] == 3


def test_run_jobs_cancel_raises():
    ev = mp.Event()
    ev.set()
    with pytest.raises(CancelledScan):
        run_jobs(_double, list(range(10)), workers=2, cancel_event=ev)


def _kill_worker(item):
    import os

    os._exit(1)


def test_run_jobs_broken_pool_single_problem():
    results, problems = run_jobs(_kill_worker, [1, 2, 3], workers=1)
    assert problems != []
    assert len(problems) == 1
    assert problems[0]["item"] is None
    assert "pool crashed" in problems[0]["error"]


def test_run_jobs_empty_items():
    assert run_jobs(_double, []) == ([], [])
