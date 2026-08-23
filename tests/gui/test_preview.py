import shutil
import subprocess

import numpy
import pytest
from PIL import Image
from PySide6 import QtGui

from redundex.core.types import FileEntry, FileKind
from redundex.gui.preview import (
    CompareDialog,
    PreviewPane,
    ThumbStripWorker,
    decode_strip,
    encode_strip,
)


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
    worker.wait()


def test_compare_dialog_smoke(qtbot, tmp_path):
    p = _png(tmp_path / "a.png")
    entries = [
        FileEntry(path=p, size=1, mtime_ns=1, kind=FileKind.IMAGE),
        FileEntry(path=p, size=1, mtime_ns=1, kind=FileKind.IMAGE),
    ]
    dlg = CompareDialog(entries, {})
    qtbot.addWidget(dlg)


def _qimage(i=0):
    img = QtGui.QImage(160, 90, QtGui.QImage.Format_Grayscale8)
    img.fill(20 * (i + 1))
    return img


class _FakeWorker:
    instances = []

    def __init__(self, path, duration=0.0):
        self.path = path
        self.duration = duration
        self.started = False
        _FakeWorker.instances.append(self)

    def isRunning(self):
        return False

    def cancel(self):
        pass

    def wait(self, ms=None):
        return True

    def start(self):
        self.started = True

    thumbs_ready = None


def test_preview_middle_frame_and_clickable_thumbs(qtbot, tmp_path, monkeypatch):
    import redundex.gui.preview as preview_mod

    calls = []
    monkeypatch.setattr(preview_mod, "open_path", lambda p: calls.append(p) or True)
    monkeypatch.setattr(preview_mod.tools, "which", lambda name: None)
    pane = preview_mod.PreviewPane()
    qtbot.addWidget(pane)
    pane.resize(400, 300)
    entry = FileEntry(
        path=str(tmp_path / "v.mp4"), size=10, mtime_ns=1, kind=FileKind.VIDEO
    )
    pane.set_file(entry, {"duration": 12.0})
    pane._display_thumbs([_qimage(), _qimage(), _qimage()])
    assert not pane._label.pixmap().isNull()
    buttons = [
        pane._strip.itemAt(i).widget() for i in range(pane._strip.count())
    ]
    assert len(buttons) == 3
    buttons[1].click()
    assert calls == [str(tmp_path / "v.mp4")]


def test_preview_open_button_reports_missing_handler(qtbot, tmp_path, monkeypatch):
    import redundex.gui.preview as preview_mod

    monkeypatch.setattr(preview_mod, "open_path", lambda p: False)
    monkeypatch.setattr(preview_mod.tools, "which", lambda name: None)
    pane = preview_mod.PreviewPane()
    qtbot.addWidget(pane)
    pane.set_file(
        FileEntry(
            path=str(tmp_path / "v.mp4"), size=10, mtime_ns=1,
            kind=FileKind.VIDEO,
        )
    )
    pane._open_btn.click()
    assert "No system handler" in pane._note.text()


def test_set_file_never_spawns_worker(qtbot, tmp_path, monkeypatch):
    import redundex.gui.preview as preview_mod

    _FakeWorker.instances = []

    class _Signals:
        def connect(self, fn):
            pass

    def fake_init(self, path, duration=0.0):
        self.path = path
        self.thumbs_ready = _Signals()
        _FakeWorker.instances.append(self)

    monkeypatch.setattr(
        preview_mod, "ThumbStripWorker",
        lambda path, duration=0.0: fake_init(_FakeWorker, path, duration),
    )
    monkeypatch.setattr(preview_mod.tools, "which", lambda name: "/bin/ffmpeg")
    pane = preview_mod.PreviewPane()
    qtbot.addWidget(pane)
    entry = FileEntry(
        path=str(tmp_path / "v.mp4"), size=10, mtime_ns=1, kind=FileKind.VIDEO
    )
    pane.set_file(entry, {"duration": 12.0})
    pane.set_file(entry, {"duration": 12.0})
    assert _FakeWorker.instances == []
    assert pane._load_btn.isVisibleTo(pane)


def test_load_button_generates_once_and_caches(qtbot, tmp_path, monkeypatch):
    import redundex.gui.preview as preview_mod

    class _RealEmit:
        def __init__(self):
            self._fn = None

        def connect(self, fn):
            self._fn = fn

        def emit_now(self, images):
            if self._fn is not None:
                self._fn(images)

    made = []

    class _Worker:
        def __init__(self, path, duration=0.0):
            self.path = path
            self.thumbs_ready = _RealEmit()
            made.append(self)

        def isRunning(self):
            return False

        def cancel(self):
            pass

        def wait(self, ms=None):
            return True

        def start(self):
            self.thumbs_ready.emit_now([_qimage(1), _qimage(2), _qimage(3)])

    stored = {}
    monkeypatch.setattr(preview_mod, "ThumbStripWorker", _Worker)
    monkeypatch.setattr(preview_mod.tools, "which", lambda name: "/bin/ffmpeg")
    pane = preview_mod.PreviewPane(thumb_store=lambda p, d: stored.__setitem__(p, d))
    qtbot.addWidget(pane)
    entry = FileEntry(
        path=str(tmp_path / "v.mp4"), size=10, mtime_ns=1, kind=FileKind.VIDEO
    )
    pane.set_file(entry, {"duration": 12.0})
    pane._load_filmstrip()
    assert len(made) == 1
    assert not pane._label.pixmap().isNull()
    assert entry.path in pane._cache
    assert entry.path in stored

    other = FileEntry(
        path=str(tmp_path / "w.mp4"), size=10, mtime_ns=1, kind=FileKind.VIDEO
    )
    pane.set_file(other, {"duration": 9.0})
    pane.set_file(entry, {"duration": 12.0})
    assert not pane._label.pixmap().isNull()
    assert len(made) == 1


def test_persistent_source_displays_without_worker(qtbot, tmp_path, monkeypatch):
    import redundex.gui.preview as preview_mod

    strip = preview_mod.encode_strip([_qimage(1), _qimage(2)])
    made = []
    monkeypatch.setattr(
        preview_mod, "ThumbStripWorker",
        lambda path, duration=0.0: made.append(1),
    )
    monkeypatch.setattr(preview_mod.tools, "which", lambda name: "/bin/ffmpeg")
    pane = preview_mod.PreviewPane(thumb_source=lambda p: strip)
    qtbot.addWidget(pane)
    entry = FileEntry(
        path=str(tmp_path / "v.mp4"), size=10, mtime_ns=1, kind=FileKind.VIDEO
    )
    pane.set_file(entry, {})
    assert made == []
    assert not pane._label.pixmap().isNull()
    assert not pane._load_btn.isVisibleTo(pane)


def test_worker_cancel_before_start_emits_empty(qtbot, tmp_path):
    worker = ThumbStripWorker(str(tmp_path / "missing.mp4"), duration=5.0)
    with qtbot.waitSignal(worker.thumbs_ready, timeout=5000) as blocker:
        worker.cancel()
        worker.start()
    assert blocker.args[0] == []
    worker.wait()


def test_strip_codec_roundtrip():
    images = [_qimage(i) for i in range(4)]
    data = encode_strip(images)
    assert data is not None
    back = decode_strip(data)
    assert len(back) == 4
    assert all(img.width() == 160 for img in back)
