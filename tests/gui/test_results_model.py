from redundex.core.types import FileEntry, FileKind, Group, Match, MatchReason, ScanResult
from redundex.gui.results_model import COLUMNS, ResultsModel


def _entry(name, size=10, mtime=1000):
    return FileEntry(path=f"/t/{name}", size=size, mtime_ns=mtime, kind=FileKind.IMAGE)


def _result():
    entries_a = [_entry("big.jpg", 100), _entry("small.jpg", 40, mtime=2000)]
    m = Match("/t/big.jpg", "/t/small.jpg", MatchReason.PERCEPTUAL, 0.9)
    g = Group(members=entries_a, matches=[m], redundancy=40)
    entries_b = [_entry("z1.bin", 5), _entry("z2.bin", 5)]
    g2 = Group(
        members=entries_b,
        matches=[Match("/t/z1.bin", "/t/z2.bin", MatchReason.EXACT, 1.0)],
        redundancy=5,
    )
    meta = {"/t/big.jpg": {"width": 800, "height": 600}, "/t/small.jpg": {"width": 400, "height": 300}}
    return ScanResult(groups=[g, g2], meta=meta)


def test_model_structure(qtbot):
    model = ResultsModel()
    model.set_result(_result())
    assert model.rowCount() == 2
    assert model.columnCount() == len(COLUMNS)
    g0 = model.index(0, 0)
    assert model.rowCount(g0) == 2
    child = model.index(1, 1, g0)
    assert child.data() == "small.jpg"
    assert model.parent(child) == g0
    assert model.index(1, 3, g0).data() == "40 B"
    assert model.index(0, 3, g0).data() == "100 B"


def test_details_and_reason_columns(qtbot):
    model = ResultsModel()
    model.set_result(_result())
    g0 = model.index(0, 0)
    assert model.index(0, 4, g0).data() == "800x600"
    assert model.index(1, 4, g0).data() == "400x300"
    assert model.index(0, 6, g0).data() == "perceptual"


def test_mark_toggle(qtbot):
    model = ResultsModel()
    model.set_result(_result())
    g0 = model.index(0, 0)
    mark_index = model.index(1, 0, g0)
    assert model.marked_paths() == []
    model.toggle_mark(mark_index)
    assert model.marked_paths() == ["/t/small.jpg"]
    model.toggle_mark(mark_index)
    assert model.marked_paths() == []


def test_mark_except_rules(qtbot):
    model = ResultsModel()
    model.set_result(_result())
    model.mark_except(0, "resolution")
    assert model.marked_paths() == ["/t/small.jpg"]
    model.mark_except(0, "mtime")
    assert model.marked_paths() == ["/t/big.jpg"]


def test_min_redundancy_filter(qtbot):
    model = ResultsModel()
    model.set_result(_result())
    model.set_min_redundancy(10)
    assert model.rowCount() == 1
    model.set_min_redundancy(0)
    assert model.rowCount() == 2
