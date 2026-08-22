from redundex.core.detectors.image import match_images
from redundex.core.types import MatchReason


def test_close_hashes_match():
    base = 0b0000000000000000000000000000000000000000000000000000000000000001
    fps = {
        "/a.png": (base, base, 100, 100),
        "/b.png": (base ^ 0b1111, base, 50, 50),
    }
    matches = match_images(fps, threshold=8)
    assert len(matches) == 1
    m = matches[0]
    assert m.reason is MatchReason.PERCEPTUAL
    assert {m.a, m.b} == {"/a.png", "/b.png"}


def test_far_hashes_no_match():
    far = 0xFFFFFFFFFFFFFFFF
    fps = {
        "/a.png": (0, 0, 100, 100),
        "/b.png": (far, far, 50, 50),
    }
    assert match_images(fps, threshold=8) == []


def test_either_tree_matches():
    base = 0
    fps = {
        "/a.png": (base, base, 100, 100),
        "/b.png": (base ^ 0b11, base ^ (2**63 + 2**62), 50, 50),
    }
    assert len(match_images(fps, threshold=8)) == 1


def test_threshold_respected():
    base = 0
    far = (1 << 10) - 1
    fps = {
        "/a.png": (base, base, 100, 100),
        "/b.png": (base ^ far, base ^ far, 50, 50),
    }
    assert match_images(fps, threshold=8) == []
    assert len(match_images(fps, threshold=10)) == 1
