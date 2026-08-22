from redundex.core.detectors.video import containment_candidates, coarse_candidates


def _mix(i, salt=0):
    return ((i + 1 + salt) * 0x9E3779B97F4A7C15) % (2**64)


def test_coarse_candidates_same_content():
    base = 0x123456789ABCDEF0
    a = {
        "a.mp4": [base] * 16,
        "b.mp4": [base] * 15 + [base ^ 0xFFFF],
        "c.mp4": [_mix(i) for i in range(16)],
    }
    pairs = coarse_candidates(a)
    assert ("a.mp4", "b.mp4") in pairs
    assert all("c.mp4" not in p for p in pairs)


def test_coarse_candidates_require_two_bands():
    base = 0x0000000000000001
    a = {"a.mp4": [base] * 16, "b.mp4": [0xFFFFFFFFFFFFFFFE] * 16}
    assert coarse_candidates(a) == set()


def test_containment_candidates_shared_frames():
    clip = [_mix(i) for i in range(12)]
    container = (
        [_mix(i, 100) for i in range(20)] + clip + [_mix(i, 200) for i in range(20)]
    )
    videos = {
        "clip.mp4": clip,
        "full.mp4": container,
        "other.mp4": [_mix(i, 300) for i in range(30)],
    }
    pairs = containment_candidates(videos)
    assert ("clip.mp4", "full.mp4") in pairs
    assert all("other.mp4" not in p for p in pairs)


def test_containment_candidates_empty():
    assert containment_candidates({}) == set()


def test_coarse_candidates_identical_content_star():
    base = 0x123456789ABCDEF0
    vids = {f"v{i}.mp4": [base] * 16 for i in range(50)}
    pairs = coarse_candidates(vids)
    assert len(pairs) == 49
    assert all("v0.mp4" in p for p in pairs)


def test_containment_candidates_identical_content_star():
    clip = [_mix(i) for i in range(12)]
    vids = {f"v{i}.mp4": clip for i in range(50)}
    pairs = containment_candidates(vids)
    assert len(pairs) == 49
    assert all("v0.mp4" in p for p in pairs)
