import os

from PySide6 import QtCore, QtWidgets

from ..core import capabilities as caps
from ..core.hashstore import HashStore
from ..core.launch import open_path
from ..core.scan import Scan
from ..core.trash import move_batch, undo_last
from ..core.types import ScanConfig, format_size
from .results_model import ResultsModel
from .workers import ScanWorker


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Redundex")
        self._root = ""
        self._worker = None

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)

        row1 = QtWidgets.QHBoxLayout()
        self.folder_edit = QtWidgets.QLineEdit()
        browse = QtWidgets.QPushButton("Browse...")
        self.scan_btn = QtWidgets.QPushButton("Scan")
        self.cancel_btn = QtWidgets.QPushButton("Cancel")
        self.cancel_btn.setEnabled(False)
        row1.addWidget(self.folder_edit, 1)
        row1.addWidget(browse)
        row1.addWidget(self.scan_btn)
        row1.addWidget(self.cancel_btn)
        layout.addLayout(row1)

        row2 = QtWidgets.QHBoxLayout()
        self.exact_check = QtWidgets.QCheckBox("Exact")
        self.image_check = QtWidgets.QCheckBox("Images")
        self.video_check = QtWidgets.QCheckBox("Videos")
        self.audio_check = QtWidgets.QCheckBox("Audio")
        self.docs_check = QtWidgets.QCheckBox("Documents")
        self.image_thresh = QtWidgets.QSpinBox()
        self.image_thresh.setRange(0, 32)
        self.image_thresh.setValue(8)
        row2.addWidget(self.exact_check)
        row2.addWidget(self.image_check)
        row2.addWidget(QtWidgets.QLabel("img threshold"))
        row2.addWidget(self.image_thresh)
        row2.addWidget(self.video_check)
        row2.addWidget(self.audio_check)
        row2.addWidget(self.docs_check)
        row2.addStretch(1)
        layout.addLayout(row2)
        for cb in (self.exact_check, self.image_check, self.video_check,
                   self.audio_check, self.docs_check):
            cb.setChecked(True)

        self.progress = QtWidgets.QProgressBar()
        self.stage_label = QtWidgets.QLabel("")
        self.min_redundancy = QtWidgets.QSpinBox()
        self.min_redundancy.setRange(0, 1000000)
        self.min_redundancy.setSuffix(" MB min")
        self.min_redundancy.valueChanged.connect(self._refilter)
        self.batch_limit = QtWidgets.QSpinBox()
        self.batch_limit.setRange(0, 1000000)
        self.batch_limit.setSpecialValueText("no limit")
        self.batch_limit.setPrefix("max new: ")
        filter_row = QtWidgets.QHBoxLayout()
        filter_row.addWidget(self.progress, 1)
        filter_row.addWidget(self.min_redundancy)
        filter_row.addWidget(self.batch_limit)
        layout.addLayout(filter_row)
        layout.addWidget(self.stage_label)

        self.model = ResultsModel()
        self.tree = QtWidgets.QTreeView()
        self.tree.setModel(self.model)
        self.tree.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        layout.addWidget(self.tree, 1)

        row3 = QtWidgets.QHBoxLayout()
        move_btn = QtWidgets.QPushButton("Move marked...")
        undo_btn = QtWidgets.QPushButton("Undo last move")
        compare_btn = QtWidgets.QPushButton("Compare selected")
        problems_btn = QtWidgets.QPushButton("Problems...")
        row3.addWidget(move_btn)
        row3.addWidget(undo_btn)
        row3.addWidget(compare_btn)
        row3.addStretch(1)
        row3.addWidget(problems_btn)
        layout.addLayout(row3)

        self.status = QtWidgets.QLabel("Ready")
        layout.addWidget(self.status)

        browse.clicked.connect(self._browse)
        self.scan_btn.clicked.connect(self.start_scan)
        self.cancel_btn.clicked.connect(self._cancel)
        move_btn.clicked.connect(self.move_marked)
        undo_btn.clicked.connect(self.undo_last_move)
        compare_btn.clicked.connect(self._compare_selected)
        problems_btn.clicked.connect(self._show_problems)
        self.tree.customContextMenuRequested.connect(self._context_menu)
        self.tree.doubleClicked.connect(self._open_clicked)
        self.tree.selectionModel().currentChanged.connect(self._preview_current)
        self._last_result = None

        self._apply_capabilities()

    def _apply_capabilities(self):
        missing = caps.which_missing()
        caps_map = caps.check_capabilities()
        for key, cb in (("video", self.video_check), ("audio", self.audio_check)):
            cb.setEnabled(caps_map[key])
            if not caps_map[key]:
                cb.setChecked(False)
        if not caps_map["pdf"]:
            self.docs_check.setEnabled(False)
            self.docs_check.setChecked(False)
        if missing:
            self.status.setText(
                "Disabled (tools missing): " + ", ".join(sorted(missing))
            )

    def _browse(self):
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose folder")
        if d:
            self.folder_edit.setText(d)

    def _config(self):
        limit = self.batch_limit.value()
        return ScanConfig(
            exact=self.exact_check.isChecked(),
            image=self.image_check.isChecked(),
            image_threshold=self.image_thresh.value(),
            video=self.video_check.isChecked(),
            audio=self.audio_check.isChecked(),
            docs=self.docs_check.isChecked(),
            batch_limit=limit if limit > 0 else None,
        )

    def scan_sync(self):
        if self._worker is not None and self._worker.isRunning():
            return
        self._root = self.folder_edit.text().strip()
        scan = Scan(self._root, self._config())
        self._apply_result(scan.run())

    def start_scan(self):
        if self._worker is not None and self._worker.isRunning():
            return
        self._root = self.folder_edit.text().strip()
        self.scan_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self._worker = ScanWorker(self._root, self._config())
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_scan.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _cancel(self):
        if self._worker is not None:
            self._worker.cancel()

    def _on_progress(self, stage, done, total):
        self.stage_label.setText(f"{stage}: {done}/{total}")
        self.progress.setMaximum(max(total, 1))
        self.progress.setValue(done)

    def _on_finished(self, result):
        self._apply_result(result)
        self.scan_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)

    def _on_failed(self, message):
        self.status.setText(f"Scan failed: {message}")
        self.scan_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)

    def _apply_result(self, result):
        self._last_result = result
        self.model.set_result(result)
        total = sum(g.redundancy for g in result.groups)
        self.status.setText(
            f"{len(result.groups)} group(s), {format_size(total)} redundant"
        )
        if result.cancelled:
            self.status.setText(
                self.status.text() + " (paused - scan again to resume)"
            )

    def _refilter(self, mb):
        self.model.set_min_redundancy(mb * 1024 * 1024)

    def move_marked(self):
        marked = self.model.marked_paths()
        if not marked:
            QtWidgets.QMessageBox.information(self, "Move", "Nothing is marked.")
            return
        coll = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Choose collection folder"
        )
        if not coll:
            return
        answer = QtWidgets.QMessageBox.question(
            self,
            "Move",
            f"Move {len(marked)} file(s) to {coll}?",
        )
        if answer != QtWidgets.QMessageBox.Yes:
            return
        manifest, moved, failed = move_batch(marked, coll, root=self._root)
        msg = f"Moved {len(moved)}, failed {len(failed)}. Manifest: {manifest}"
        QtWidgets.QMessageBox.information(self, "Move", msg)
        if moved:
            self.start_scan()

    def undo_last_move(self):
        coll = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Choose collection folder"
        )
        if not coll:
            return
        outcome = undo_last(coll)
        QtWidgets.QMessageBox.information(
            self,
            "Undo",
            f"Restored {outcome['restored']}, remaining {outcome['remaining']}",
        )
        if outcome["restored"]:
            self.start_scan()

    def _compare_selected(self):
        rows = self.tree.selectionModel().selectedRows(0)
        if len(rows) < 2:
            return
        entries = []
        for idx in rows:
            node = idx.internalPointer()
            if node and node[0] == "member":
                entries.append(self.model.group_at_row(node[1]).members[node[2]])
        if len(entries) >= 2:
            from .preview import CompareDialog

            CompareDialog(entries, self.model._meta, self).exec()

    def _show_problems(self):
        problems = self._last_result.problems if self._last_result else []
        text = "\n".join(
            f"{p.get('path', p.get('item', '?'))}: {p['error']}" for p in problems
        ) or "No problems"
        QtWidgets.QMessageBox.information(self, "Problems", text)

    def _context_menu(self, pos):
        idx = self.tree.indexAt(pos)
        node = idx.internalPointer() if idx.isValid() else None
        if not node or node[0] != "group":
            return
        menu = QtWidgets.QMenu(self)
        for label, key in (
            ("Mark all but largest", "size"),
            ("Mark all but newest", "mtime"),
            ("Mark all but highest resolution", "resolution"),
        ):
            menu.addAction(label, lambda k=key: self.model.mark_except(node[1], k))
        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def _open_clicked(self, index):
        node = index.internalPointer() if index.isValid() else None
        if not node or node[0] != "member":
            return
        entry = self.model.group_at_row(node[1]).members[node[2]]
        open_path(entry.path)

    def _preview_current(self, current, _previous):
        node = current.internalPointer() if current.isValid() else None
        if not node or node[0] != "member":
            return
        entry = self.model.group_at_row(node[1]).members[node[2]]
        if not hasattr(self, "preview_pane"):
            from .preview import PreviewPane

            self.preview_pane = PreviewPane(
                self,
                thumb_source=self._load_thumb,
                thumb_store=self._save_thumb,
            )
            dock = QtWidgets.QDockWidget("Preview", self)
            dock.setWidget(self.preview_pane)
            self.addDockWidget(QtCore.Qt.RightDockWidgetArea, dock)
        self.preview_pane.set_file(entry, self.model._meta.get(entry.path, {}))

    def closeEvent(self, event):
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(10000)
        if hasattr(self, "preview_pane"):
            w = self.preview_pane._worker
            if w is not None and w.isRunning():
                w.cancel()
                w.wait(5000)
        super().closeEvent(event)

    def _load_thumb(self, path):
        try:
            st = os.stat(path)
            with HashStore(self._root) as store:
                return store.get_thumb(path, st.st_size, st.st_mtime_ns)
        except Exception:
            return None

    def _save_thumb(self, path, data):
        try:
            with HashStore(self._root) as store:
                store.put_thumb(path, data)
        except Exception:
            pass
