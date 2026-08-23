import subprocess

from PySide6 import QtCore, QtGui, QtWidgets

from ..core import tools
from ..core.launch import open_path
from ..core.tools import subprocess_flags
from ..core.types import FileKind

FRAME_W = 160


class ThumbStripWorker(QtCore.QThread):
    thumbs_ready = QtCore.Signal(list)

    def __init__(self, path, duration=0.0, count=6, parent=None):
        super().__init__(parent)
        self.path = path
        self.duration = duration
        self.count = count
        self._stop = False
        self._proc = None

    def cancel(self):
        self._stop = True
        proc = self._proc
        if proc is not None:
            try:
                proc.kill()
            except OSError:
                pass

    def run(self):
        images = []
        ffmpeg = tools.which("ffmpeg")
        if ffmpeg is None or self._stop:
            self.thumbs_ready.emit(images)
            return
        if self.duration > 0:
            times = [self.duration * (i + 0.5) / self.count for i in range(self.count)]
            for t in times:
                if self._stop:
                    break
                img = self._grab_at(ffmpeg, t)
                if img is not None:
                    images.append(img)
        else:
            images = self._stream(ffmpeg)
        self.thumbs_ready.emit(images)

    def _grab_at(self, ffmpeg, t):
        try:
            proc = subprocess.Popen(
                [ffmpeg, "-v", "error", "-ss", f"{t:.2f}", "-i", self.path,
                 "-frames:v", "1", "-s", "160x90", "-f", "image2pipe",
                 "-vcodec", "png", "-"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                creationflags=subprocess_flags(),
            )
        except OSError:
            return None
        self._proc = proc
        try:
            out, _ = proc.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            return None
        finally:
            self._proc = None
        img = QtGui.QImage.fromData(out)
        return img if not img.isNull() else None

    def _stream(self, ffmpeg):
        try:
            proc = subprocess.Popen(
                [ffmpeg, "-v", "error", "-i", self.path,
                 "-vf", "fps=1/5,scale=160:90", "-frames:v", str(self.count),
                 "-f", "image2pipe", "-vcodec", "png", "-"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                creationflags=subprocess_flags(),
            )
        except OSError:
            return []
        self._proc = proc
        try:
            out, _ = proc.communicate(timeout=60)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            return []
        finally:
            self._proc = None
        return _split_png_stream(out)


def _split_png_stream(data):
    images = []
    start = 0
    png_end = b"IEND"
    while True:
        i = data.find(b"\x89PNG", start)
        if i < 0:
            break
        j = data.find(png_end, i)
        if j < 0:
            break
        end = j + len(png_end) + 4
        img = QtGui.QImage.fromData(data[i:end])
        if not img.isNull():
            images.append(img)
        start = end
    return images


def encode_strip(images):
    if not images:
        return None
    height = images[0].height()
    strip = QtGui.QImage(len(images) * FRAME_W, height, QtGui.QImage.Format_RGB32)
    painter = QtGui.QPainter(strip)
    x = 0
    for img in images:
        painter.drawImage(x, 0, img.convertToFormat(QtGui.QImage.Format_RGB32))
        x += FRAME_W
    painter.end()
    buf = QtCore.QBuffer()
    buf.open(QtCore.QIODevice.WriteOnly)
    strip.save(buf, "JPG", 70)
    return bytes(buf.data())


def decode_strip(data):
    img = QtGui.QImage.fromData(data)
    if img.isNull() or img.width() < FRAME_W:
        return []
    n = img.width() // FRAME_W
    return [
        img.copy(i * FRAME_W, 0, FRAME_W, img.height()).convertToFormat(
            QtGui.QImage.Format_RGB32
        )
        for i in range(n)
    ]


class PreviewPane(QtWidgets.QWidget):
    def __init__(self, parent=None, thumb_source=None, thumb_store=None):
        super().__init__(parent)
        self._thumb_source = thumb_source
        self._thumb_store = thumb_store
        self._cache = {}
        self._worker = None
        self._current_entry = None
        self._current_meta = {}

        self._label = QtWidgets.QLabel("No preview")
        self._label.setAlignment(QtCore.Qt.AlignCenter)
        self._open_btn = QtWidgets.QPushButton("Open in default player")
        self._open_btn.clicked.connect(self._open_current)
        self._load_btn = QtWidgets.QPushButton("Load filmstrip")
        self._load_btn.clicked.connect(self._load_filmstrip)
        self._note = QtWidgets.QLabel("")
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch(1)
        btn_row.addWidget(self._load_btn)
        btn_row.addWidget(self._open_btn)
        btn_row.addStretch(1)
        self._strip_host = QtWidgets.QWidget()
        self._strip = QtWidgets.QHBoxLayout(self._strip_host)
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self._label, 1)
        layout.addLayout(btn_row)
        layout.addWidget(self._note)
        layout.addWidget(self._strip_host)
        self._load_btn.hide()

    def set_file(self, entry, meta=None):
        self._current_entry = entry
        self._current_meta = meta or {}
        self._note.setText("")
        self._clear_strip()
        self._label.setPixmap(QtGui.QPixmap())
        self._load_btn.hide()
        if entry.kind is FileKind.IMAGE:
            pix = QtGui.QPixmap(entry.path)
            if not pix.isNull():
                target = self._label.size()
                if target.width() < 2 or target.height() < 2:
                    target = QtCore.QSize(400, 300)
                self._label.setPixmap(
                    pix.scaled(
                        target,
                        QtCore.Qt.KeepAspectRatio,
                        QtCore.Qt.SmoothTransformation,
                    )
                )
                return
        self._label.setText(entry.path)
        if entry.kind is FileKind.VIDEO:
            imgs = self._cache.get(entry.path)
            if imgs is None and self._thumb_source is not None:
                data = self._thumb_source(entry.path)
                if data is not None:
                    imgs = decode_strip(data)
                    if imgs:
                        self._cache[entry.path] = imgs
            if imgs:
                self._display_thumbs(imgs)
            elif tools.which("ffmpeg") is not None:
                self._load_btn.show()

    def _load_filmstrip(self):
        entry = self._current_entry
        if entry is None or entry.kind is not FileKind.VIDEO:
            return
        self._load_btn.hide()
        imgs = self._cache.get(entry.path)
        if imgs:
            self._display_thumbs(imgs)
            return
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(3000)
        self._note.setText("Loading filmstrip...")
        worker = ThumbStripWorker(
            entry.path, self._current_meta.get("duration", 0.0)
        )
        worker.thumbs_ready.connect(
            lambda images, p=entry.path: self._on_thumbs(p, images)
        )
        self._worker = worker
        worker.start()

    def _on_thumbs(self, path, images):
        self._note.setText("")
        if not images:
            return
        self._cache[path] = images
        if self._thumb_store is not None:
            data = encode_strip(images)
            if data is not None:
                self._thumb_store(path, data)
        if self._current_entry is not None and self._current_entry.path == path:
            self._display_thumbs(images)

    def _open_current(self):
        if self._current_entry is None:
            return
        if not open_path(self._current_entry.path):
            self._note.setText("No system handler found for this file")

    def _display_thumbs(self, images):
        if not images:
            return
        self._load_btn.hide()
        middle = QtGui.QPixmap.fromImage(images[len(images) // 2])
        target = self._label.size()
        if target.width() < 2 or target.height() < 2:
            target = QtCore.QSize(400, 300)
        self._label.setPixmap(
            middle.scaled(
                target,
                QtCore.Qt.KeepAspectRatio,
                QtCore.Qt.SmoothTransformation,
            )
        )
        path = self._current_entry.path if self._current_entry else ""
        for img in images:
            btn = QtWidgets.QToolButton()
            btn.setIcon(QtGui.QIcon(QtGui.QPixmap.fromImage(img)))
            btn.setIconSize(QtCore.QSize(FRAME_W, 90))
            btn.setAutoRaise(True)
            btn.setToolTip(path)
            btn.clicked.connect(self._open_current)
            self._strip.addWidget(btn)

    def _clear_strip(self):
        while self._strip.count():
            item = self._strip.takeAt(0)
            if item.widget():
                item.widget().deleteLater()


class CompareDialog(QtWidgets.QDialog):
    def __init__(self, entries, meta, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Compare")
        layout = QtWidgets.QHBoxLayout(self)
        for entry in entries[:2]:
            label = QtWidgets.QLabel()
            if entry.kind is FileKind.IMAGE:
                pix = QtGui.QPixmap(entry.path)
                if not pix.isNull():
                    label.setPixmap(
                        pix.scaled(
                            400, 400, QtCore.Qt.KeepAspectRatio,
                            QtCore.Qt.SmoothTransformation,
                        )
                    )
            if label.pixmap().isNull():
                label.setText(entry.path)
            layout.addWidget(label)
