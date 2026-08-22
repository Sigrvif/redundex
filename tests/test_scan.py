import multiprocessing as mp
import shutil
import subprocess
import zipfile

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
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page(width=300, height=200)
    page.insert_text((20, 40), "Redundant document content")
    doc.save(str(tmp_path / "a.pdf"))
    doc.close()
    doc = pymupdf.open()
    page = doc.new_page(width=500, height=400)
    page.insert_text((80, 90), "Redundant   DOCUMENT\ncontent")
    doc.save(str(tmp_path / "b.pdf"))
    doc.close()
    (tmp_path / "c.txt").write_text("redundantdocumentcontent")
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
         "-c:a", "libvorbis", str(tmp_path / "t.ogg")],
        check=True,
    )
    cache = str(tmp_path_factory.mktemp("cache") / "c.sqlite")
    cfg = ScanConfig(cache_path=cache, image=False, video=False, docs=False)
    result = Scan(str(tmp_path), cfg).run()
    assert len(result.groups) == 1
    assert result.stats["audio"]["matches"] == 1
    result2 = Scan(str(tmp_path), cfg).run()
    assert result2.stats["audio"]["hashed"] == 0
