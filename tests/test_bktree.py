import random

from redundex.core.detectors.bktree import BKTree


def _pop(a, b):
    return (a ^ b).bit_count()


def test_query_matches_brute_force():
    rng = random.Random(42)
    items = [rng.getrandbits(64) for _ in range(300)]
    tree = BKTree(distance=_pop)
    for it in items:
        tree.add(it)
    for target in items[:50]:
        radius = 6
        got = {item for _d, item in tree.query(target, radius)}
        expected = {it for it in items if _pop(target, it) <= radius}
        assert got == expected


def test_duplicate_add_is_noop():
    tree = BKTree(distance=_pop)
    tree.add(123)
    tree.add(123)
    assert tree.query(123, 0) == [(0, 123)]


def test_empty_tree_query():
    assert BKTree(distance=_pop).query(1, 5) == []
