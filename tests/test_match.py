from redundex.core.match import build_groups
from redundex.core.types import FileEntry, FileKind, Match, MatchReason


def _entry(name, size, mtime=1000):
    return FileEntry(path=f"/t/{name}", size=size, mtime_ns=mtime, kind=FileKind.OTHER)


def test_transitive_matches_form_one_group():
    entries = {e.path: e for e in (_entry("a", 10), _entry("b", 20), _entry("c", 30))}
    matches = [
        Match("/t/a", "/t/b", MatchReason.EXACT, 1.0),
        Match("/t/b", "/t/c", MatchReason.PERCEPTUAL, 0.95),
    ]
    groups = build_groups(entries, matches, quality={})
    assert len(groups) == 1
    g = groups[0]
    assert {m.path for m in g.members} == {"/t/a", "/t/b", "/t/c"}
    assert len(g.matches) == 2
    assert g.redundancy == 60 - 30


def test_best_file_first_by_quality_then_mtime():
    entries = {e.path: e for e in (_entry("a", 10, 2000), _entry("b", 20, 1000))}
    matches = [Match("/t/a", "/t/b", MatchReason.EXACT, 1.0)]
    groups = build_groups(entries, matches, quality={"/t/a": 5.0, "/t/b": 9.0})
    assert [m.path for m in groups[0].members] == ["/t/b", "/t/a"]
    assert groups[0].redundancy == 10


def test_quality_falls_back_to_size_and_newest():
    entries = {e.path: e for e in (_entry("old", 20, 1000), _entry("new", 20, 9000))}
    matches = [Match("/t/old", "/t/new", MatchReason.EXACT, 1.0)]
    groups = build_groups(entries, matches, quality={})
    assert [m.path for m in groups[0].members] == ["/t/new", "/t/old"]


def test_partial_quality_falls_back_to_size():
    entries = {
        e.path: e
        for e in (_entry("small_new", 10, 9000), _entry("big_old", 20, 1000))
    }
    matches = [Match("/t/small_new", "/t/big_old", MatchReason.EXACT, 1.0)]
    groups = build_groups(
        entries, matches, quality={"/t/small_new": 5.0}
    )
    assert [m.path for m in groups[0].members] == ["/t/big_old", "/t/small_new"]


def test_unmatched_files_excluded():
    entries = {e.path: e for e in (_entry("a", 1), _entry("lonely", 2))}
    groups = build_groups(entries, [])
    assert groups == []
