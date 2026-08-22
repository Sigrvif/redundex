import multiprocessing as mp

from PySide6 import QtCore

from ..core.scan import Scan


class ScanWorker(QtCore.QThread):
    progress = QtCore.Signal(str, int, int)
    finished_scan = QtCore.Signal(object)
    failed = QtCore.Signal(str)

    def __init__(self, root, config, parent=None):
        super().__init__(parent)
        self.root = root
        self.config = config
        self._cancel = mp.Event()

    def cancel(self):
        self._cancel.set()

    def run(self):
        try:
            scan = Scan(
                self.root,
                self.config,
                progress_cb=self._emit,
                cancel_event=self._cancel,
            )
            self.finished_scan.emit(scan.run())
        except Exception as exc:
            self.failed.emit(str(exc))

    def _emit(self, stage, done, total):
        self.progress.emit(stage, done, total)
