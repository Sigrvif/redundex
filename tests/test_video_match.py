import pytest

from redundex.core.detectors.video import (
    aligned_similarity,
    best_window,
    coarse_signature,
    frames_agree,
)


def _h(n):
    return 0b0000000000000000000000000000000000000000000000000000000000000000 | (n % 4)


def test_frames_agree_threshold():
    a = 0
    assert frames_agree(a, 0b111111, 6)
    assert not frames_agree(a, 0b1111111, 6)


def test_aligned_similarity_identical():
    seq = [_h(i) for i in range(10)]
    assert aligned_similarity(seq, seq, 6) == 1.0


def test_aligned_similarity_resamples_grids():
    dense = [_h(i) for i in range(21)]
    sparse = [_h(i) for i in range(0, 21, 5)]
    assert aligned_similarity(dense, sparse, 6) == 1.0


def test_aligned_similarity_partial_noise():
    a = [_h(0)] * 10
    b = [_h(0)] * 8 + [_h(3)] * 2
    assert aligned_similarity(a, b, 1) == pytest.approx(0.8)


def test_best_window_finds_offset():
    core = [0x0000] * 5
    intro = [0x00FF] * 3
    outro = [0xFF00] * 4
    long_seq = intro + core + outro
    sim, offset = best_window(core, long_seq, 6)
    assert sim == 1.0
    assert offset == 3


def test_best_window_no_fit():
    a = [0x0000] * 4
    b = [0xFFFF] * 9
    sim, offset = best_window(a, b, 6)
    assert sim < 0.5


def test_coarse_signature_positions():
    def f(t):
        return 0x1000 ^ t

    dense = [f(t) for t in range(31)]
    sparse = [f(t) for t in range(0, 31, 2)]
    assert len(coarse_signature(dense)) == 16
    assert coarse_signature(dense) == coarse_signature(sparse)
