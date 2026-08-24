from PySide6 import QtCore, QtWidgets

from redundex.gui.main_window import MainWindow


def test_scan_sync_and_move_flow(qtbot, make_tree, tmp_path, tmp_path_factory, monkeypatch):
    root = make_tree({"a/one.bin": b"same", "b/one.bin": b"same"})
    win = MainWindow()
    qtbot.addWidget(win)
    win.folder_edit.setText(str(root))
    win.scan_sync()
    assert win.model.rowCount() == 1
    assert "1 group" in win.status.text()

    child = win.model.index(0, 0, win.model.index(0, 0))
    win.model.toggle_mark(child)
    coll = tmp_path_factory.mktemp("coll")
    monkeypatch.setattr(
        QtWidgets.QFileDialog,
        "getExistingDirectory",
        staticmethod(lambda *a, **k: str(coll)),
    )
    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "question",
        staticmethod(lambda *a, **k: QtWidgets.QMessageBox.Yes),
    )
    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "information",
        staticmethod(lambda *a, **k: QtWidgets.QMessageBox.Ok),
    )
    win.move_marked()
    moved = [p for p in [root / "a/one.bin", root / "b/one.bin"] if not p.exists()]
    assert len(moved) == 1
    assert len(list(coll.rglob("one.bin"))) == 1

    win.undo_last_move()
    assert (root / "a/one.bin").exists() and (root / "b/one.bin").exists()
    win.close()


def test_detector_toggles_reflect_capabilities(qtbot, monkeypatch):
    import redundex.core.capabilities as caps

    monkeypatch.setattr(caps, "which_missing", lambda: {"video", "audio", "pdf"})
    monkeypatch.setattr(
        caps, "check_capabilities",
        lambda: {"video": False, "audio": False, "pdf": False},
    )
    win = MainWindow()
    qtbot.addWidget(win)
    assert not win.video_check.isEnabled()
    assert not win.audio_check.isEnabled()
    assert not win.docs_check.isEnabled()
    assert win.exact_check.isEnabled()


def test_double_click_opens_file(qtbot, monkeypatch):
    import redundex.gui.main_window as mw_mod
    from redundex.core.types import FileEntry, FileKind, Group, Match, MatchReason, ScanResult

    opened = []
    monkeypatch.setattr(mw_mod, "open_path", lambda p: opened.append(p) or True)
    win = MainWindow()
    qtbot.addWidget(win)
    entry = FileEntry(path="/t/clip.mp4", size=5, mtime_ns=1, kind=FileKind.VIDEO)
    group = Group(
        members=[entry],
        matches=[],
        redundancy=0,
    )
    win.model.set_result(ScanResult(groups=[group], meta={}))
    idx = win.model.index(0, 0, win.model.index(0, 0))
    win._open_clicked(idx)
    assert opened == ["/t/clip.mp4"]
    win.close()


def _one_group_result(path="/t/clip.mp4"):
    from redundex.core.types import FileEntry, FileKind, Group, ScanResult

    entry = FileEntry(path=path, size=5, mtime_ns=1, kind=FileKind.VIDEO)
    group = Group(members=[entry], matches=[], redundancy=0)
    return ScanResult(groups=[group], meta={})


def test_groups_expanded_after_result(qtbot):
    win = MainWindow()
    qtbot.addWidget(win)
    win.model.set_result(_one_group_result())
    assert win.tree.isExpanded(win.model.index(0, 0))
    win.model.set_min_redundancy(1000)
    assert win.tree.model().rowCount() == 0
    win.model.set_min_redundancy(0)
    assert win.tree.isExpanded(win.model.index(0, 0))
    win.close()


def test_space_toggles_mark_on_current(qtbot):
    win = MainWindow()
    qtbot.addWidget(win)
    win.model.set_result(_one_group_result())
    child = win.model.index(0, 0, win.model.index(0, 0))
    win.tree.setCurrentIndex(child)
    qtbot.keyClick(win.tree, QtCore.Qt.Key_Space)
    assert win.model.marked_paths() == ["/t/clip.mp4"]
    qtbot.keyClick(win.tree, QtCore.Qt.Key_Space)
    assert win.model.marked_paths() == []
    win.close()


def test_enter_opens_current_file(qtbot, monkeypatch):
    import redundex.gui.main_window as mw_mod
    from PySide6 import QtCore as _qc

    opened = []
    monkeypatch.setattr(mw_mod, "open_path", lambda p: opened.append(p) or True)
    win = MainWindow()
    qtbot.addWidget(win)
    win.model.set_result(_one_group_result("/t/v.mp4"))
    child = win.model.index(0, 0, win.model.index(0, 0))
    win.tree.setCurrentIndex(child)
    qtbot.keyClick(win.tree, _qc.Qt.Key_Return)
    assert opened == ["/t/v.mp4"]
    opened.clear()
    group_idx = win.model.index(0, 0)
    win.tree.setCurrentIndex(group_idx)
    qtbot.keyClick(win.tree, _qc.Qt.Key_Enter)
    assert opened == []
    win.close()
