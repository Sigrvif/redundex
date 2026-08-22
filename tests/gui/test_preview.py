import shutil
import subprocess

import numpy
import pytest
from PIL import Image

from redundex.core.types import FileEntry, FileKind
from redundex.gui.preview import CompareDialog, PreviewPane, ThumbStripWorker


def _png(path, size=120):
    arr = numpy.zeros((size, size), dtype=numpy.uint8)
    arr[:, : size // 2] = 200
    Image.fromarray(arr).save(path)
    return str(path)


def test_preview_shows_image(qtbot, tmp_path):
    p = _png(tmp_path / "img.png")
    pane = PreviewPane()
    qtbot.addWidget(pane)
    pane.resize(400, 300)
    pane.set_file(FileEntry(path=p, size=10, mtime_ns=1, kind=FileKind.IMAGE))
    assert not pane._label.pixmap().isNull()


def test_preview_fallback_text(qtbot, tmp_path):
    pane = PreviewPane()
    qtbot.addWidget(pane)
    pane.set_file(FileEntry(path=str(tmp_path / "gone.bin"), size=10, mtime_ns=1, kind=FileKind.OTHER))
    assert "gone.bin" in pane._label.text()


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_thumb_strip_worker(qtbot, tmp_path):
    out = tmp_path / "v.mp4"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=duration=12:size=160x120:rate=5",
         "-pix_fmt", "yuv420p", str(out)],
        check=True,
    )
    worker = ThumbStripWorker(str(out), duration=12)
    with qtbot.waitSignal(worker.thumbs_ready, timeout=60000) as blocker:
        worker.start()
    assert len(blocker.args[0]) == 6


def test_compare_dialog_smoke(qtbot, tmp_path):
    p = _png(tmp_path / "a.png")
    entries = [
        FileEntry(path=p, size=1, mtime_ns=1, kind=FileKind.IMAGE),
        FileEntry(path=p, size=1, mtime_ns=1, kind=FileKind.IMAGE),
    ]
    dlg = CompareDialog(entries, {})
    qtbot.addWidget(dlg)
