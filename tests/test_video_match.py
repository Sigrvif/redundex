import shutil
import subprocess

import pytest

from redundex.core.detectors.video import (
    aligned_similarity,
    best_window,
    coarse_signature,
    frames_agree,
    match_videos,
    video_job,
)
from redundex.core.types import MatchReason


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


ffmpeg = pytest.mark.skipif(
    not (shutil.which("ffmpeg") and shutil.which("ffprobe")),
    reason="ffmpeg/ffprobe not installed",
)


def _make(path, duration=20, size="320x240", src="testsrc", extra=()):
    cmd = ["ffmpeg", "-v", "error", "-f", "lavfi",
           "-i", f"{src}=size={size}:rate=10"]
    cmd.extend(extra)
    cmd.extend(["-t", str(duration), "-pix_fmt", "yuv420p", str(path)])
    subprocess.run(cmd, check=True)
    return str(path)


def _fp(path, interval=5.0):
    p, duration, hashes, w, h = video_job(path, interval=interval)
    return p, {"duration": duration, "hashes": hashes, "width": w, "height": h}


@ffmpeg
def test_same_content_different_resolution(tmp_path):
    big = _make(tmp_path / "big.mp4", duration=40, size="640x480")
    small = _make(tmp_path / "small.mp4", duration=40, size="320x240")
    fps = dict([_fp(big), _fp(small)])
    matches = match_videos(fps, video_similarity=0.90, containment_similarity=0.85)
    assert len(matches) == 1
    assert matches[0].reason is MatchReason.PERCEPTUAL


@ffmpeg
def test_clip_contained_with_offset(tmp_path):
    full = _make(tmp_path / "full.mp4", duration=40, size="320x240", src="mandelbrot")
    clip = str(tmp_path / "clip.mp4")
    subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", "5", "-t", "10", "-i", full,
         "-pix_fmt", "yuv420p", clip],
        check=True,
    )
    fps = dict([_fp(full), _fp(clip)])
    matches = match_videos(fps, video_similarity=0.90, containment_similarity=0.85)
    assert len(matches) == 1
    m = matches[0]
    assert m.reason is MatchReason.CONTAINED_IN
    assert m.a == clip and m.b == full
    assert "at " in m.detail


@ffmpeg
def test_unrelated_videos_do_not_match(tmp_path):
    a = _make(tmp_path / "a.mp4", duration=30, src="testsrc")
    b = _make(tmp_path / "b.mp4", duration=30, src="testsrc2")
    fps = dict([_fp(a), _fp(b)])
    assert match_videos(fps, video_similarity=0.90, containment_similarity=0.85) == []
