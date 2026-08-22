import os
import time

import pytest

from redundex.core.hashstore import CacheLockedError, HashStore
from redundex.core.types import FileKind
from redundex.core.walk import walk_folder


def _first_entry(root):
    entries, _ = walk_folder(root)
    return {e.path: e for e in entries}


def test_roundtrip_freshness_and_prune(make_tree, tmp_path_factory):
    root = make_tree({"a.jpg": b"12345", "b.jpg": b"678"})
    entries = _first_entry(root)
    cache = str(tmp_path_factory.mktemp("cache") / "c.sqlite")
    store = HashStore(root, cache_path=cache)
    assert store.load("fp_exact", entries) == {}
    store.save_files(entries)
    store.put(
        "fp_exact",
        [
            {"path": e.path, "file_hash": "h" + os.path.basename(e.path), "listing_hash": None}
            for e in entries.values()
        ],
    )
    fresh = store.load("fp_exact", entries)
    assert {p: fresh[p]["file_hash"] for p in entries} == {
        str(root / "a.jpg"): "ha.jpg",
        str(root / "b.jpg"): "hb.jpg",
    }

    os.utime(str(root / "a.jpg"), ns=(time.time_ns() + 10**9,) * 2)
    stale_entries = _first_entry(root)
    assert set(store.load("fp_exact", stale_entries)) == {str(root / "b.jpg")}

    (root / "b.jpg").unlink()
    store.prune({str(root / "a.jpg")})
    store.close()
    store = HashStore(root, cache_path=cache)
    assert store.load("fp_exact", stale_entries) == {}
    remaining = [r[0] for r in store.db.execute("SELECT path FROM files")]
    assert remaining == [str(root / "a.jpg")]
    store.close()


def test_lock_prevents_second_instance(make_tree, tmp_path):
    root = make_tree({"a.jpg": b"x"})
    cache = str(tmp_path / "c.sqlite")
    store = HashStore(root, cache_path=cache)
    with pytest.raises(CacheLockedError):
        HashStore(root, cache_path=cache)
    store.close()
    HashStore(root, cache_path=cache).close()


def test_stale_lock_is_taken_over(make_tree, tmp_path):
    import time as _time

    root = make_tree({"a.jpg": b"x"})
    cache = str(tmp_path / "c.sqlite")
    store = HashStore(root, cache_path=cache)
    old = _time.time() - 48 * 3600
    os.utime(store.lock_path, (old, old))
    store2 = HashStore(root, cache_path=cache)
    store2.close()
    store.close()


def test_default_cache_location(make_tree):
    root = make_tree({"a.jpg": b"x"})
    store = HashStore(root)
    assert store.path.name == ".redundex.cache.sqlite"
    assert store.path.parent == root.resolve()
    store.close()
