import multiprocessing as mp
import os
import shutil
import subprocess
import zipfile
from pathlib import Path

import numpy
import pytest
from PIL import Image

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


def test_scan_recomputes_modified_file(make_tree, tmp_path_factory):
    root = make_tree({"a.bin": b"one", "b.bin": b"one"})
    cache = str(tmp_path_factory.mktemp("cache") / "c.sqlite")
    cfg = _cfg(cache)
    result = Scan(root, cfg).run()
    assert result.stats["exact"]["hashed"] == 2
    assert len(result.groups) == 1

    (root / "a.bin").write_bytes(b"two")
    os.utime(root / "a.bin")
    result2 = Scan(root, cfg).run()
    assert result2.stats["exact"]["hashed"] == 1
    assert result2.stats["exact"]["matches"] == 0
    assert result2.groups == []


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
    cache = str(tmp_path_factory.mktemp("cache") / "c.sqlite")
    ev = mp.Event()
    ev.set()
    result = Scan(root, _cfg(cache), cancel_event=ev).run()
    assert result.cancelled is True
    assert result.groups == []


def _img(path, size, variant=0):
    rng = numpy.random.default_rng(variant)
    arr = numpy.zeros((size, size), dtype=numpy.uint8)
    arr[:, : size // 2] = 70
    arr[size // 3 : size // 2, size // 4 : 3 * size // 4] = 210
    if variant:
        arr = arr.astype(numpy.int16) + rng.integers(-8, 9, (size, size))
        arr = numpy.clip(arr, 0, 255).astype(numpy.uint8)
    Image.fromarray(arr).save(path)


def _stripes(path, size):
    y, x = numpy.mgrid[0:size, 0:size]
    arr = ((x + y) % (size // 4) < size // 8).astype(numpy.uint8) * 255
    Image.fromarray(arr).save(path)


def test_scan_image_stage_groups_resizes(make_tree, tmp_path_factory):
    root = make_tree({})
    _img(root / "big.png", 256)
    _img(root / "small.png", 64)
    _stripes(root / "other.png", 128)
    cache = str(tmp_path_factory.mktemp("cache") / "c.sqlite")
    cfg = ScanConfig(cache_path=cache, video=False, audio=False, docs=False)
    result = Scan(root, cfg).run()
    assert len(result.groups) == 1
    g = result.groups[0]
    assert {m.path for m in g.members} == {
        str(root / "big.png"), str(root / "small.png")
    }
    assert g.members[0].path == str(root / "big.png")
    assert result.stats["image"]["hashed"] == 3
    assert result.stats["image"]["matches"] == 1
    assert result.meta[str(root / "big.png")] == {"width": 256, "height": 256}
    assert result.meta[str(root / "small.png")] == {"width": 64, "height": 64}

    result2 = Scan(root, cfg).run()
    assert result2.stats["image"]["hashed"] == 0
    assert len(result2.groups) == 1


def test_scan_video_stage_skips_without_tools(tmp_path, tmp_path_factory, monkeypatch):
    from redundex.core import tools

    monkeypatch.setattr(tools, "which", lambda name: None)
    (tmp_path / "fake.mp4").write_bytes(b"x")
    cache = str(tmp_path_factory.mktemp("cache") / "c.sqlite")
    cfg = ScanConfig(cache_path=cache, image=False, audio=False, docs=False)
    result = Scan(str(tmp_path), cfg).run()
    assert result.stats["video"]["skipped"] == "ffmpeg/ffprobe not installed"
    assert result.problems == []


VIDEO_SKIP = pytest.mark.skipif(
    not shutil.which("ffmpeg"), reason="ffmpeg not installed"
)


@VIDEO_SKIP
def test_scan_video_stage(tmp_path, tmp_path_factory):
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi",
         "-i", "testsrc=duration=40:size=640x480:rate=10",
         "-pix_fmt", "yuv420p", str(tmp_path / "big.mp4")],
        check=True,
    )
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi",
         "-i", "testsrc=duration=40:size=320x240:rate=10",
         "-pix_fmt", "yuv420p", str(tmp_path / "small.mp4")],
        check=True,
    )
    cache = str(tmp_path_factory.mktemp("cache") / "c.sqlite")
    cfg = ScanConfig(cache_path=cache, image=False, audio=False, docs=False)
    result = Scan(str(tmp_path), cfg).run()
    assert len(result.groups) == 1
    assert result.stats["video"]["hashed"] == 2
    assert result.stats["video"]["matches"] == 1
    meta = result.meta[str(tmp_path / "big.mp4")]
    assert meta["width"] == 640 and meta["duration"] > 39

    result2 = Scan(str(tmp_path), cfg).run()
    assert result2.stats["video"]["hashed"] == 0


def test_scan_docs_stage(tmp_path, tmp_path_factory):
    fixtures = Path(__file__).parent / "fixtures"
    shutil.copyfile(fixtures / "pdf-text-a.pdf", tmp_path / "a.pdf")
    shutil.copyfile(fixtures / "pdf-text-b.pdf", tmp_path / "b.pdf")
    (tmp_path / "c.txt").write_text("helloredundantworld")
    cache = str(tmp_path_factory.mktemp("cache") / "c.sqlite")
    cfg = ScanConfig(cache_path=cache, image=False, video=False, audio=False)
    result = Scan(str(tmp_path), cfg).run()
    assert len(result.groups) == 1
    assert len(result.groups[0].members) == 3
    assert result.stats["docs"]["matches"] == 2
    result2 = Scan(str(tmp_path), cfg).run()
    assert result2.stats["docs"]["hashed"] == 0


AUDIO_SKIP = pytest.mark.skipif(
    not (shutil.which("fpcalc") and shutil.which("ffmpeg")),
    reason="fpcalc/ffmpeg not installed",
)


@AUDIO_SKIP
def test_scan_audio_stage(tmp_path, tmp_path_factory):
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi",
         "-i", "sine=frequency=440:duration=30",
         str(tmp_path / "t.wav")],
        check=True,
    )
    subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(tmp_path / "t.wav"),
         "-c:a", "flac", str(tmp_path / "t.flac")],
        check=True,
    )
    cache = str(tmp_path_factory.mktemp("cache") / "c.sqlite")
    cfg = ScanConfig(cache_path=cache, image=False, video=False, docs=False)
    result = Scan(str(tmp_path), cfg).run()
    assert len(result.groups) == 1
    assert result.stats["audio"]["matches"] == 1
    result2 = Scan(str(tmp_path), cfg).run()
    assert result2.stats["audio"]["hashed"] == 0


def test_scan_cancel_preserves_exact_progress(make_tree, tmp_path_factory):
    root = make_tree(
        {"a.bin": b"aaa1", "b.bin": b"bbb2", "c.bin": b"ccc3", "d.bin": b"ddd4"}
    )
    cache = str(tmp_path_factory.mktemp("cache") / "c.sqlite")
    cfg = _cfg(cache)
    ev = mp.Event()

    def maybe_cancel(stage, done, total):
        if stage == "exact" and done >= 1:
            ev.set()

    result = Scan(root, cfg, progress_cb=maybe_cancel, cancel_event=ev).run()
    assert result.cancelled is True

    result2 = Scan(root, cfg).run()
    assert not result2.cancelled
    assert result2.stats["exact"]["hashed"] == 3


def test_scan_cancel_after_modify_no_stale(make_tree, tmp_path_factory):
    root = make_tree({"a.bin": b"xx", "z.bin": b"xx"})
    cache = str(tmp_path_factory.mktemp("cache") / "c.sqlite")
    cfg = _cfg(cache)
    assert len(Scan(root, cfg).run().groups) == 1

    (root / "z.bin").write_bytes(b"yy")
    os.utime(root / "z.bin")
    ev = mp.Event()

    def cancel_at_exact_start(stage, done, total):
        if stage == "exact":
            ev.set()

    result = Scan(
        root, cfg, progress_cb=cancel_at_exact_start, cancel_event=ev
    ).run()
    assert result.cancelled is True

    result2 = Scan(root, cfg).run()
    assert result2.stats["exact"]["hashed"] == 1
    assert result2.groups == []


def test_scan_batch_limit(make_tree, tmp_path_factory):
    root = make_tree(
        {"a.bin": b"one", "b.bin": b"two", "c.bin": b"one", "d.bin": b"two"}
    )
    cache = str(tmp_path_factory.mktemp("cache") / "c.sqlite")
    cfg = ScanConfig(
        cache_path=cache,
        image=False,
        video=False,
        audio=False,
        docs=False,
        batch_limit=2,
    )
    result = Scan(root, cfg).run()
    assert result.stats["exact"]["hashed"] == 2
    assert len(result.groups) == 0

    result2 = Scan(root, cfg).run()
    assert result2.stats["exact"]["hashed"] == 2
    assert result2.stats["exact"]["cached"] == 2
    assert len(result2.groups) == 2
    result3 = Scan(root, cfg).run()
    assert result3.stats["exact"]["hashed"] == 0
    assert result3.stats["exact"]["cached"] == 4
    assert len(result3.groups) == 2


@VIDEO_SKIP
def test_scan_cancel_resumes_video(tmp_path, tmp_path_factory):
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi",
         "-i", "testsrc=size=640x480:rate=10", "-t", "20",
         "-pix_fmt", "yuv420p", str(tmp_path / "big.mp4")],
        check=True,
    )
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi",
         "-i", "testsrc=size=320x240:rate=10", "-t", "20",
         "-pix_fmt", "yuv420p", str(tmp_path / "small.mp4")],
        check=True,
    )
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi",
         "-i", "testsrc2=size=320x240:rate=10", "-t", "20",
         "-pix_fmt", "yuv420p", str(tmp_path / "other.mp4")],
        check=True,
    )
    cache = str(tmp_path_factory.mktemp("cache") / "c.sqlite")
    cfg = ScanConfig(cache_path=cache, image=False, audio=False, docs=False)
    ev = mp.Event()

    def maybe_cancel(stage, done, total):
        if stage == "video" and done >= 1:
            ev.set()

    result = Scan(str(tmp_path), cfg, progress_cb=maybe_cancel, cancel_event=ev).run()
    assert result.cancelled is True

    result2 = Scan(str(tmp_path), cfg).run()
    assert not result2.cancelled
    assert result2.stats["video"]["hashed"] == 2
    assert len(result2.groups) == 1
