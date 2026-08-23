import os
import sqlite3
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS files(
    path TEXT PRIMARY KEY, size INTEGER, mtime_ns INTEGER, kind TEXT);
CREATE TABLE IF NOT EXISTS fp_exact(
    path TEXT PRIMARY KEY, file_hash TEXT, listing_hash TEXT);
CREATE TABLE IF NOT EXISTS fp_image(
    path TEXT PRIMARY KEY, phash INTEGER, dhash INTEGER, width INTEGER, height INTEGER);
CREATE TABLE IF NOT EXISTS fp_video(
    path TEXT PRIMARY KEY, duration REAL, frame_hashes BLOB, coarse BLOB,
    width INTEGER, height INTEGER, audio_fp BLOB);
CREATE TABLE IF NOT EXISTS fp_audio(
    path TEXT PRIMARY KEY, raw BLOB, duration REAL);
CREATE TABLE IF NOT EXISTS fp_doc(
    path TEXT PRIMARY KEY, text_hash TEXT, page1_phash INTEGER);
CREATE TABLE IF NOT EXISTS thumbs(
    path TEXT PRIMARY KEY, filmstrip BLOB);
"""

_TABLES = frozenset(
    {"files", "fp_exact", "fp_image", "fp_video", "fp_audio", "fp_doc", "thumbs"}
)


class CacheLockedError(RuntimeError):
    pass


class HashStore:
    def __init__(self, root: str, cache_path: str | None = None):
        p = Path(cache_path) if cache_path else Path(root) / ".redundex.cache.sqlite"
        self.path = p
        self.lock_path = p.with_name(p.name + ".lock")
        self._acquire_lock()
        try:
            self.db = sqlite3.connect(str(p))
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.executescript(SCHEMA)
            self.db.commit()
        except Exception:
            try:
                self.lock_path.unlink()
            except FileNotFoundError:
                pass
            raise

    def _acquire_lock(self, stale_after=24 * 3600):
        for _ in range(2):
            try:
                fd = os.open(
                    str(self.lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY
                )
            except FileExistsError:
                try:
                    age = time.time() - os.path.getmtime(str(self.lock_path))
                except OSError:
                    age = 0
                if age > stale_after:
                    try:
                        self.lock_path.unlink()
                    except FileNotFoundError:
                        pass
                    continue
                raise CacheLockedError(
                    f"cache is locked by another instance: {self.lock_path}"
                )
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return

    def _table(self, table):
        if table not in _TABLES:
            raise ValueError(f"unknown table: {table}")
        return table

    def _columns(self, table):
        return {r[1] for r in self.db.execute(f"PRAGMA table_info({table})")}

    def save_files(self, entries):
        rows = [
            (e.path, e.size, e.mtime_ns, e.kind.value) for e in entries.values()
        ]
        self.db.executemany(
            "INSERT OR REPLACE INTO files(path, size, mtime_ns, kind) VALUES(?,?,?,?)",
            rows,
        )
        self.db.commit()

    def load(self, table, entries):
        table = self._table(table)
        fresh = {}
        cur = self.db.execute(
            f"SELECT f.size AS _size, f.mtime_ns AS _mtime, t.* "
            f"FROM {table} t JOIN files f ON f.path = t.path"
        )
        cols = [d[0] for d in cur.description]
        for row in cur.fetchall():
            d = dict(zip(cols, row))
            e = entries.get(d["path"])
            if e is None:
                continue
            if e.size == d["_size"] and e.mtime_ns == d["_mtime"]:
                d.pop("_size"), d.pop("_mtime")
                fresh[d["path"]] = d
        return fresh

    def put(self, table, rows):
        table = self._table(table)
        if not rows:
            return
        cols = list(rows[0].keys())
        unknown = [c for c in cols if c not in self._columns(table)]
        if unknown:
            raise ValueError(f"unknown columns for {table}: {','.join(unknown)}")
        sql = (
            f"INSERT OR REPLACE INTO {table}({','.join(cols)}) "
            f"VALUES({','.join('?' * len(cols))})"
        )
        self.db.executemany(sql, [tuple(r[c] for c in cols) for r in rows])
        self.db.commit()

    def prune(self, alive):
        all_paths = [r[0] for r in self.db.execute("SELECT path FROM files")]
        vanished = [p for p in all_paths if p not in alive]
        for i in range(0, len(vanished), 500):
            chunk = vanished[i : i + 500]
            marks = ",".join("?" * len(chunk))
            self.db.execute(f"DELETE FROM files WHERE path IN ({marks})", chunk)
            for table in ("fp_exact", "fp_image", "fp_video", "fp_audio",
                          "fp_doc", "thumbs"):
                self.db.execute(f"DELETE FROM {self._table(table)} WHERE path IN ({marks})", chunk)
        self.db.commit()

    def get_thumb(self, path, size, mtime_ns):
        row = self.db.execute(
            "SELECT f.size, f.mtime_ns, t.filmstrip FROM thumbs t "
            "JOIN files f ON f.path = t.path WHERE t.path = ?",
            (path,),
        ).fetchone()
        if row is None or row[0] != size or row[1] != mtime_ns:
            return None
        return row[2]

    def put_thumb(self, path, filmstrip):
        self.db.execute(
            "INSERT OR REPLACE INTO thumbs(path, filmstrip) VALUES(?,?)",
            (path, filmstrip),
        )
        self.db.commit()

    def close(self):
        try:
            self.db.commit()
            self.db.close()
        finally:
            try:
                self.lock_path.unlink()
            except FileNotFoundError:
                pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
