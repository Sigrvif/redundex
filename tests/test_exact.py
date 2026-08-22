import zipfile

from redundex.core.detectors.exact import (
    blake3_file,
    hash_job,
    match_from_fingerprints,
)
from redundex.core.types import MatchReason


def _run(paths):
    fps = {}
    for p in paths:
        path, fh, listing = hash_job(p)
        fps[path] = (fh, listing)
    return fps, match_from_fingerprints(fps)


def test_blake3_file_stable(tmp_path):
    a = tmp_path / "a.bin"
    a.write_bytes(b"hello")
    assert blake3_file(str(a)) == blake3_file(str(a))
    assert len(blake3_file(str(a))) == 64


def test_identical_content_matches(make_tree):
    root = make_tree({"one.bin": b"data", "two.bin": b"data", "three.bin": b"other"})
    fps, matches = _run([str(root / p) for p in ("one.bin", "two.bin", "three.bin")])
    assert len(matches) == 1
    m = matches[0]
    assert m.reason is MatchReason.EXACT
    assert {m.a, m.b} == {str(root / "one.bin"), str(root / "two.bin")}


def test_three_way_chain(make_tree):
    root = make_tree({"a.bin": b"x", "b.bin": b"x", "c.bin": b"x"})
    _, matches = _run([str(root / p) for p in ("a.bin", "b.bin", "c.bin")])
    assert len(matches) == 2


def test_two_identical_plus_one_repacked(make_tree):
    import zipfile

    root = make_tree({})
    members = {"m.txt": b"aaa"}
    for name in ("c1.zip", "c2.zip"):
        with zipfile.ZipFile(root / name, "w", zipfile.ZIP_STORED) as z:
            z.writestr("m.txt", members["m.txt"])
    with zipfile.ZipFile(root / "repacked.zip", "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("m.txt", members["m.txt"])
    fps, matches = _run(
        [str(root / n) for n in ("c1.zip", "c2.zip", "repacked.zip")]
    )
    hash_matches = [m for m in matches if m.detail == "identical content"]
    listing_matches = [m for m in matches if m.detail == "same archive contents"]
    assert len(hash_matches) == 1
    assert len(listing_matches) == 2


def test_repacked_zip_matches_by_listing(tmp_path):
    members = {"m1.txt": b"aaa", "m2.txt": b"bbb"}
    stored = tmp_path / "stored.zip"
    deflated = tmp_path / "deflated.zip"
    with zipfile.ZipFile(stored, "w", zipfile.ZIP_STORED) as z:
        for n, d in members.items():
            z.writestr(n, d)
    with zipfile.ZipFile(deflated, "w", zipfile.ZIP_DEFLATED) as z:
        for n, d in members.items():
            z.writestr(n, d)
    fps, matches = _run([str(stored), str(deflated)])
    assert fps[str(stored)][0] != fps[str(deflated)][0]
    assert len(matches) == 1
    assert matches[0].reason is MatchReason.EXACT
    assert "archive contents" in matches[0].detail
