import multiprocessing as mp
import zipfile

from redundex.core.scan import Scan
from redundex.core.types import ScanConfig


def _cfg(cache):
    return ScanConfig(
        cache_path=cache, image=False, video=False, audio=False, docs=False
    )


def test_scan_finds_exact_group_and_uses_cache(make_tree, tmp_path_factory):
    root = make_tree({"x/one.bin": b"data", "two.bin": b"data", "three.bin": b"zz"})
    cache = str(tmp_path_factory.mktemp("cache") / "c.sqlite")
    result = Scan(root, _cfg(cache)).run()
    assert len(result.groups) == 1
    g = result.groups[0]
    assert g.redundancy == 4
    assert not result.cancelled
    assert result.stats["exact"]["hashed"] == 2
    assert result.stats["exact"]["matches"] == 1

    result2 = Scan(root, _cfg(cache)).run()
    assert len(result2.groups) == 1
    assert result2.stats["exact"]["hashed"] == 0
    assert result2.stats["exact"]["matches"] == 1


def test_scan_matches_repacked_archives(make_tree, tmp_path_factory):
    root = make_tree({})
    members = {"m1.txt": b"aaa", "m2.txt": b"bbb"}
    with zipfile.ZipFile(root / "stored.zip", "w", zipfile.ZIP_STORED) as z:
        for n, d in members.items():
            z.writestr(n, d)
    with zipfile.ZipFile(root / "deflated.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for n, d in members.items():
            z.writestr(n, d)
    cache = str(tmp_path_factory.mktemp("cache") / "c.sqlite")
    result = Scan(root, _cfg(cache)).run()
    assert len(result.groups) == 1
    assert result.groups[0].redundancy > 0
    assert result.stats["exact"]["matches"] == 1


def test_scan_reports_stage_progress(make_tree, tmp_path_factory):
    root = make_tree({"a.bin": b"q", "b.bin": b"q"})
    cache = str(tmp_path_factory.mktemp("c") / "c.sqlite")
    events = []
    scan = Scan(root, _cfg(cache), progress_cb=lambda s, d, t: events.append((s, d, t)))
    scan.run()
    stages = [e[0] for e in events]
    assert "walk" in stages and "exact" in stages and "group" in stages


def test_scan_cancelled_before_start(make_tree, tmp_path_factory):
    root = make_tree({"a.bin": b"q", "b.bin": b"q"})
    cache = str(tmp_path_factory.mktemp("c") / "c.sqlite")
    ev = mp.Event()
    ev.set()
    result = Scan(root, _cfg(cache), cancel_event=ev).run()
    assert result.cancelled is True
    assert result.groups == []
