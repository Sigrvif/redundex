import json

from redundex.core.cli import main


def test_scan_json_stats(make_tree, tmp_path, capsys):
    root = make_tree({"a.bin": b"same", "b.bin": "same".encode()})
    main(["scan", str(root), "--cache", str(tmp_path / "c.sqlite"), "--json"])
    out = capsys.readouterr()
    data = json.loads(out.out.splitlines()[-1])
    assert data["stats"]["exact"]["matches"] == 1


def test_scan_json_groups(make_tree, tmp_path, capsys):
    root = make_tree({"a.bin": b"x", "b.bin": b"x"})
    main([
        "scan", str(root),
        "--cache", str(tmp_path / "c.sqlite"),
        "--no-image", "--no-video", "--no-audio", "--no-docs",
        "--json",
    ])
    lines = capsys.readouterr().out.splitlines()
    data = json.loads(lines[-1])
    assert len(data["groups"]) == 1
    assert data["groups"][0]["redundancy"] == 1


def test_scan_missing_folder_errors(tmp_path, capsys):
    import pytest

    with pytest.raises(SystemExit) as exc:
        main(["scan", str(tmp_path / "nope"), "--json"])
    assert exc.value.code == 2


def test_scan_no_exact_flag(make_tree, tmp_path, capsys):
    root = make_tree({"a.bin": b"x", "b.bin": b"x"})
    main([
        "scan", str(root),
        "--cache", str(tmp_path / "c.sqlite"),
        "--no-exact", "--json",
    ])
    data = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert "exact" not in data["stats"]
    assert data["groups"] == []


def test_move_and_undo_commands(make_tree, tmp_path, capsys):
    root = make_tree({"a/one.txt": b"1", "two.txt": b"2"})
    coll = tmp_path / "coll"
    rc = main(["move", str(coll), str(root / "a/one.txt"), str(root / "two.txt")])
    assert rc == 0
    assert (coll / "a/one.txt").exists() and (coll / "two.txt").exists()
    rc = main(["undo", str(coll)])
    assert rc == 0
    assert (root / "a/one.txt").exists() and (root / "two.txt").exists()
    out = capsys.readouterr().out
    assert "restored" in out
