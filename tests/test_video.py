import shutil
import subprocess

import pytest

from redundex.core.detectors.video import probe, sample_frames, video_job

pytestmark = pytest.mark.skipif(
    not (shutil.which("ffmpeg") and shutil.which("ffprobe")),
    reason="ffmpeg/ffprobe not installed",
)


def _make_video(path, duration=20, size="320x240", src="testsrc"):
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi",
         "-i", f"{src}=duration={duration}:size={size}:rate=10",
         "-pix_fmt", "yuv420p", str(path)],
        check=True,
    )
    return str(path)


def test_probe_reports_metadata(tmp_path):
    p = _make_video(tmp_path / "v.mp4", duration=12)
    info = probe(p)
    assert 11.5 <= info["duration"] <= 12.5
    assert info["width"] == 320 and info["height"] == 240
    assert info["has_audio"] is False


def test_sample_frames_hashes(tmp_path):
    p = _make_video(tmp_path / "v.mp4", duration=20)
    hashes, interval = sample_frames(p, 20.0)
    assert 4 <= len(hashes) <= 6
    assert interval == 5.0
    assert all(0 <= h < 2**64 for h in hashes)


def test_sample_frames_interval_stretches_under_cap(tmp_path):
    p = _make_video(tmp_path / "v.mp4", duration=600)
    hashes, interval = sample_frames(p, 600.0, interval=5.0, max_frames=40)
    assert len(hashes) <= 40
    assert interval >= 600 / 40


def test_video_job(tmp_path):
    p = _make_video(tmp_path / "v.mp4", duration=15)
    path, duration, hashes, w, h = video_job(p)
    assert path == p and w == 320 and h == 240
    assert 3 <= len(hashes) <= 4
