import os

import pytest

from redundex.core.types import FileKind
from redundex.core.walk import walk_folder


def test_walk_collects_entries_with_kinds(make_tree):
    root = make_tree({"a/b.jpg": b"x", "c.txt": b"y", "d.mkv": b"zz"})
    entries, problems = walk_folder(root)
    assert problems == []
    by_name = {os.path.basename(e.path): e for e in entries}
    assert by_name["b.jpg"].kind is FileKind.IMAGE
    assert by_name["c.txt"].kind is FileKind.DOC
    assert by_name["d.mkv"].kind is FileKind.VIDEO
    assert by_name["b.jpg"].size == 1
    assert by_name["d.mkv"].mtime_ns > 0
    assert os.path.isabs(by_name["b.jpg"].path)


def test_walk_skips_cache_artifacts(make_tree):
    root = make_tree(
        {
            "real.jpg": b"data",
            ".redundex.cache.sqlite": b"x",
            ".redundex.cache.sqlite-wal": b"x",
            ".redundex.cache.sqlite-shm": b"x",
            ".redundex.cache.sqlite.lock": b"1",
        }
    )
    entries, _ = walk_folder(root)
    assert {os.path.basename(e.path) for e in entries} == {"real.jpg"}


@pytest.mark.skipif(os.name == "nt", reason="symlinks need Developer Mode on Windows")
def test_walk_skips_symlinks_by_default(make_tree, tmp_path_factory):
    root = make_tree({"real.jpg": b"data"})
    outside = tmp_path_factory.mktemp("outside")
    (outside / "inner.png").write_bytes(b"p")
    os.symlink(outside, root / "linked_dir")
    os.symlink(root / "real.jpg", root / "linked_file.jpg")
    entries, _ = walk_folder(root)
    assert {os.path.basename(e.path) for e in entries} == {"real.jpg"}


@pytest.mark.skipif(os.name == "nt", reason="symlinks need Developer Mode on Windows")
def test_walk_follows_symlinks_when_enabled(make_tree, tmp_path_factory):
    root = make_tree({"real.jpg": b"data"})
    outside = tmp_path_factory.mktemp("outside")
    (outside / "inner.png").write_bytes(b"p")
    os.symlink(outside, root / "linked_dir")
    os.symlink(root / "real.jpg", root / "linked_file.jpg")
    entries, _ = walk_folder(root, follow_symlinks=True)
    assert {os.path.basename(e.path) for e in entries} == {
        "real.jpg",
        "linked_file.jpg",
        "inner.png",
    }
