from redundex.core.hashstore import HashStore
from redundex.core.scan import _StageWriter
from redundex.core.types import FileEntry, FileKind


def _entries(n):
    return {
        f"/t/f{i}": FileEntry(
            path=f"/t/f{i}", size=i, mtime_ns=i, kind=FileKind.OTHER
        )
        for i in range(n)
    }


def test_stage_writer_batches_and_flushes(tmp_path):
    entries = _entries(250)
    store = HashStore(str(tmp_path), cache_path=str(tmp_path / "c.sqlite"))
    writer = _StageWriter(
        store,
        entries,
        "fp_exact",
        lambda r: {"path": r[0], "file_hash": r[1], "listing_hash": None},
        batch=100,
    )
    for i in range(250):
        writer.add((f"/t/f{i}", f"h{i}", None))
    mid = store.db.execute("SELECT COUNT(*) FROM fp_exact").fetchone()[0]
    assert mid == 200
    writer.flush()
    total = store.db.execute("SELECT COUNT(*) FROM fp_exact").fetchone()[0]
    assert total == 250
    files = store.db.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    assert files == 250
    store.close()


def test_stage_writer_flush_is_idempotent(tmp_path):
    entries = _entries(3)
    store = HashStore(str(tmp_path), cache_path=str(tmp_path / "c.sqlite"))
    writer = _StageWriter(
        store,
        entries,
        "fp_exact",
        lambda r: {"path": r[0], "file_hash": r[1], "listing_hash": None},
        batch=100,
    )
    for i in range(3):
        writer.add((f"/t/f{i}", f"h{i}", None))
    writer.flush()
    writer.flush()
    total = store.db.execute("SELECT COUNT(*) FROM fp_exact").fetchone()[0]
    assert total == 3
    store.close()


def test_stage_writer_partial_batch_not_written_until_flush(tmp_path):
    entries = _entries(2)
    store = HashStore(str(tmp_path), cache_path=str(tmp_path / "c.sqlite"))
    writer = _StageWriter(
        store,
        entries,
        "fp_exact",
        lambda r: {"path": r[0], "file_hash": r[1], "listing_hash": None},
        batch=100,
    )
    writer.add(("/t/f0", "h0", None))
    assert store.db.execute("SELECT COUNT(*) FROM fp_exact").fetchone()[0] == 0
    store.close()
