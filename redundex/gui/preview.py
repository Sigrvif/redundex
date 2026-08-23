import subprocess

from PySide6 import QtCore, QtGui, QtWidgets

from ..core import tools
from ..core.launch import open_path
from ..core.tools import subprocess_flags
from ..core.types import FileKind


class ThumbStripWorker(QtCore.QThread):
    thumbs_ready = QtCore.Signal(list)

    def __init__(self, path, duration=0.0, count=6, parent=None):
        super().__init__(parent)
        self.path = path
        self.duration = duration
        self.count = count

    def run(self):
        images = []
        ffmpeg = tools.which("ffmpeg")
        if ffmpeg is None:
            self.thumbs_ready.emit(images)
            return
        if self.duration > 0:
            times = [self.duration * (i + 0.5) / self.count for i in range(self.count)]
            for t in times:
                pix = self._grab_at(t)
                if pix is not None:
                    images.append(pix)
        else:
            raw = subprocess.run(
                [ffmpeg, "-v", "error", "-i", self.path,
                 "-vf", "fps=1/5,scale=160:90", "-frames:v", str(self.count),
                 "-f", "image2pipe", "-vcodec", "png", "-"],
                capture_output=True,
                creationflags=subprocess_flags(),
            )
            if raw.returncode == 0:
                images = _split_png_stream(raw.stdout)
        self.thumbs_ready.emit(images)

    def _grab_at(self, t):
        ffmpeg = tools.which("ffmpeg")
        if ffmpeg is None:
            return None
        proc = subprocess.run(
            [ffmpeg, "-v", "error", "-ss", f"{t:.2f}", "-i", self.path,
             "-frames:v", "1", "-s", "160x90", "-f", "image2pipe",
             "-vcodec", "png", "-"],
            capture_output=True,
            creationflags=subprocess_flags(),
        )
        img = QtGui.QImage.fromData(proc.stdout)
        return img if not img.isNull() else None


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


class PreviewPane(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._label = QtWidgets.QLabel("No preview")
        self._label.setAlignment(QtCore.Qt.AlignCenter)
        self._open_btn = QtWidgets.QPushButton("Open in default player")
        self._open_btn.clicked.connect(self._open_current)
        self._note = QtWidgets.QLabel("")
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch(1)
        btn_row.addWidget(self._open_btn)
        btn_row.addStretch(1)
        self._strip_host = QtWidgets.QWidget()
        self._strip = QtWidgets.QHBoxLayout(self._strip_host)
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self._label, 1)
        layout.addLayout(btn_row)
        layout.addWidget(self._note)
        layout.addWidget(self._strip_host)
        self._worker = None
        self._thumb_workers = []
        self._current = None

    def set_file(self, entry, meta=None):
        meta = meta or {}
        self._current = entry.path
        self._note.setText("")
        self._clear_strip()
        self._label.setPixmap(QtGui.QPixmap())
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
        if entry.kind is FileKind.VIDEO and tools.which("ffmpeg") is not None:
            self._thumb_workers = [
                w for w in self._thumb_workers if w.isRunning()
            ]
            self._worker = ThumbStripWorker(entry.path, meta.get("duration", 0.0))
            self._worker.thumbs_ready.connect(self._show_thumbs)
            self._worker.start()
            self._thumb_workers.append(self._worker)

    def _open_current(self):
        if self._current is None:
            return
        if not open_path(self._current):
            self._note.setText("No system handler found for this file")

    def _show_thumbs(self, images):
        if self.sender() is not self._worker:
            return
        self._display_thumbs(images)

    def _display_thumbs(self, images):
        if not images:
            return
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
        for img in images:
            btn = QtWidgets.QToolButton()
            btn.setIcon(QtGui.QIcon(QtGui.QPixmap.fromImage(img)))
            btn.setIconSize(QtCore.QSize(160, 90))
            btn.setAutoRaise(True)
            btn.setToolTip(self._current or "")
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
