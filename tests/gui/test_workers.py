from redundex.core.types import ScanConfig
from redundex.gui.workers import ScanWorker


def test_worker_emits_progress_and_result(qtbot, make_tree, tmp_path):
    root = make_tree({"a.bin": b"x", "b.bin": b"x"})
    cfg = ScanConfig(
        cache_path=str(tmp_path / "c.sqlite"),
        image=False,
        video=False,
        audio=False,
        docs=False,
    )
    worker = ScanWorker(str(root), cfg)
    with qtbot.waitSignal(worker.finished_scan, timeout=60000) as blocker:
        worker.start()
    result = blocker.args[0]
    assert len(result.groups) == 1
    assert result.stats["exact"]["matches"] == 1


def test_worker_cancel(qtbot, make_tree, tmp_path):
    root = make_tree({"a.bin": b"x"})
    worker = ScanWorker(str(root), ScanConfig(cache_path=str(tmp_path / "c.sqlite")))
    worker.cancel()
    with qtbot.waitSignal(worker.finished_scan, timeout=60000) as blocker:
        worker.start()
    assert blocker.args[0].cancelled is True
