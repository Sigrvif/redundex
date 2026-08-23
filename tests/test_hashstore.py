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


def test_init_failure_releases_lock(make_tree, tmp_path):
    import sqlite3

    root = make_tree({"a.jpg": b"x"})
    cache = tmp_path / "corrupt.sqlite"
    cache.write_bytes(b"this is not a sqlite database" * 10)
    with pytest.raises(sqlite3.DatabaseError):
        HashStore(root, cache_path=str(cache))
    assert not (tmp_path / "corrupt.sqlite.lock").exists()


def test_put_rejects_unknown_columns(make_tree, tmp_path):
    root = make_tree({"a.jpg": b"x"})
    entries = _first_entry(root)
    store = HashStore(root, cache_path=str(tmp_path / "c.sqlite"))
    with pytest.raises(ValueError):
        store.put("fp_exact", [{"path": "x", "file_hash": "h", "bogus": 1}])
    store.close()


def test_default_cache_location(make_tree):
    root = make_tree({"a.jpg": b"x"})
    store = HashStore(root)
    assert store.path.name == ".redundex.cache.sqlite"
    assert store.path.parent == root.resolve()
    store.close()


def test_thumb_roundtrip_and_staleness(make_tree, tmp_path):
    import os as _os

    root = make_tree({"v.mp4": b"x" * 10})
    entries = _first_entry(root)
    path = str(root / "v.mp4")
    store = HashStore(root, cache_path=str(tmp_path / "c.sqlite"))
    store.save_files(entries)
    assert store.get_thumb(path, 10, entries[path].mtime_ns) is None
    store.put_thumb(path, b"jpegbytes")
    assert store.get_thumb(path, 10, entries[path].mtime_ns) == b"jpegbytes"
    entries[path] = entries[path].__class__(
        path=path, size=10, mtime_ns=entries[path].mtime_ns + 5,
        kind=entries[path].kind,
    )
    assert store.get_thumb(path, 10, entries[path].mtime_ns) is None
    store.close()


def test_thumb_pruned_with_file(make_tree, tmp_path):
    root = make_tree({"a.mp4": b"1", "b.mp4": b"2"})
    entries = _first_entry(root)
    store = HashStore(root, cache_path=str(tmp_path / "c.sqlite"))
    store.save_files(entries)
    for p in entries:
        store.put_thumb(p, b"j")
    store.prune({str(root / "a.mp4")})
    rows = store.db.execute("SELECT COUNT(*) FROM thumbs").fetchone()[0]
    assert rows == 1
    store.close()
