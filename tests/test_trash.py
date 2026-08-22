import json
import os

from redundex.core.trash import latest_manifest, move_batch, undo_last


def test_move_preserves_relative_subpaths(make_tree, tmp_path):
    root = make_tree({"a/one.txt": b"1", "two.txt": b"2"})
    coll = tmp_path / "coll"
    manifest, moved, failed = move_batch(
        [str(root / "a/one.txt"), str(root / "two.txt")], str(coll), root=str(root)
    )
    assert failed == []
    assert (coll / "a/one.txt").read_bytes() == b"1"
    assert (coll / "two.txt").read_bytes() == b"2"
    assert not (root / "a/one.txt").exists()
    data = json.loads(open(manifest).read())
    assert len(data["moves"]) == 2
    assert moved[0]["dst"] == str(coll / "a/one.txt")


def test_move_collision_safe_rename(make_tree, tmp_path):
    root = make_tree({"a/x.txt": b"1", "b/x.txt": b"2"})
    coll = tmp_path / "coll"
    (coll / "a").mkdir(parents=True)
    (coll / "a/x.txt").write_bytes(b"existing")
    _manifest, _moved, failed = move_batch(
        [str(root / "a/x.txt"), str(root / "b/x.txt")], str(coll), root=str(root)
    )
    assert failed == []
    assert (coll / "a/x.txt").read_bytes() == b"existing"
    assert (coll / "a/x (2).txt").read_bytes() == b"1"


def test_move_failure_recorded(make_tree, tmp_path):
    root = make_tree({"a/good.txt": b"1"})
    coll = tmp_path / "coll"
    manifest, moved, failed = move_batch(
        [str(root / "a/good.txt"), str(root / "missing.txt")], str(coll), root=str(root)
    )
    assert len(failed) == 1 and "missing.txt" in failed[0]["path"]
    assert len(moved) == 1
    data = json.loads(open(manifest).read())
    assert len(data["moves"]) == 1


def test_manifest_sequence_numbers(make_tree, tmp_path):
    root = make_tree({"one.txt": b"1", "two.txt": b"2"})
    coll = tmp_path / "coll"
    m1, _, _ = move_batch([str(root / "one.txt")], str(coll))
    m2, _, _ = move_batch([str(root / "two.txt")], str(coll))
    assert m1 != m2
    assert latest_manifest(str(coll)) == m2


def test_move_nothing_writes_no_manifest(make_tree, tmp_path):
    root = make_tree({"one.txt": b"1"})
    coll = tmp_path / "coll"
    manifest, moved, failed = move_batch([], str(coll))
    assert manifest is None and moved == [] and failed == []
    assert latest_manifest(str(coll)) is None


def test_undo_restores_and_removes_manifest(make_tree, tmp_path):
    root = make_tree({"a/one.txt": b"1", "two.txt": b"2"})
    coll = tmp_path / "coll"
    move_batch(
        [str(root / "a/one.txt"), str(root / "two.txt")], str(coll), root=str(root)
    )
    outcome = undo_last(str(coll))
    assert outcome["restored"] == 2 and outcome["remaining"] == 0
    assert (root / "a/one.txt").read_bytes() == b"1"
    assert (root / "two.txt").read_bytes() == b"2"
    assert latest_manifest(str(coll)) is None


def test_undo_reoccupied_path_goes_to_restored(make_tree, tmp_path):
    root = make_tree({"one.txt": b"moved"})
    coll = tmp_path / "coll"
    move_batch([str(root / "one.txt")], str(coll))
    (root / "one.txt").write_bytes(b"reoccupied")
    outcome = undo_last(str(coll))
    assert outcome["restored"] == 1
    assert (root / "one.txt").read_bytes() == b"reoccupied"
    assert (coll / "restored/one.txt").read_bytes() == b"moved"


def test_restore_collision_uses_restored_n(make_tree, tmp_path):
    root = make_tree({"one.txt": b"moved"})
    coll = tmp_path / "coll"
    move_batch([str(root / "one.txt")], str(coll))
    (root / "one.txt").write_bytes(b"reoccupied")
    (coll / "restored").mkdir()
    (coll / "restored/one.txt").write_bytes(b"blocker")
    outcome = undo_last(str(coll))
    assert outcome["restored"] == 1
    assert (coll / "restored/one.txt").read_bytes() == b"blocker"
    assert (coll / "restored/one (restored-1).txt").read_bytes() == b"moved"
    assert (root / "one.txt").read_bytes() == b"reoccupied"


def test_move_rejects_source_outside_root(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "x.txt").write_bytes(b"1")
    coll = tmp_path / "coll"
    _m, moved, failed = move_batch(
        [str(outside / "x.txt")], str(coll), root=str(tmp_path / "root")
    )
    assert moved == []
    assert len(failed) == 1
    assert "outside root" in failed[0]["error"]
    assert (outside / "x.txt").exists()
    assert list(coll.rglob("*.txt")) == []


def test_undo_skips_missing_destination(make_tree, tmp_path):
    root = make_tree({"one.txt": b"1", "two.txt": b"2"})
    coll = tmp_path / "coll"
    manifest, _, _ = move_batch(
        [str(root / "one.txt"), str(root / "two.txt")], str(coll), root=str(root)
    )
    os.remove(coll / "two.txt")
    outcome = undo_last(str(coll))
    assert outcome["restored"] == 1
    assert (root / "one.txt").read_bytes() == b"1"
    assert latest_manifest(str(coll)) is None
