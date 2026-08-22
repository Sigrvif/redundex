from PySide6 import QtWidgets

from redundex.gui.main_window import MainWindow


def test_scan_sync_and_move_flow(qtbot, make_tree, tmp_path, tmp_path_factory, monkeypatch):
    root = make_tree({"a/one.bin": b"same", "b/one.bin": b"same"})
    win = MainWindow()
    qtbot.addWidget(win)
    win.folder_edit.setText(str(root))
    win.scan_sync()
    assert win.model.rowCount() == 1
    assert "1 group" in win.status.text() or win.model.rowCount() == 1

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
