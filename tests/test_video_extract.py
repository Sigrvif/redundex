from types import SimpleNamespace

import numpy
import pytest

from redundex.core.detectors import video


class _Recorder:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.kwargs = []

    def __call__(self, cmd, **kwargs):
        self.calls.append(list(cmd))
        self.kwargs.append(kwargs)
        resp = self.responses.pop(0)
        return SimpleNamespace(
            returncode=resp.get("returncode", 0), stdout=resp.get("stdout", b"")
        )


def _frames(n):
    out = bytearray()
    for i in range(n):
        rng = numpy.random.default_rng(i)
        out += rng.integers(0, 256, video.FRAME_W * video.FRAME_H, dtype=numpy.uint8).tobytes()
    return bytes(out)


def test_sample_frames_decodes_keyframes_only(monkeypatch):
    rec = _Recorder([{"stdout": _frames(10)}])
    monkeypatch.setattr(video.subprocess, "run", rec)
    monkeypatch.setattr(video.tools, "which", lambda name: "/bin/ffmpeg")
    hashes, interval = video.sample_frames("v.mp4", 100.0)
    assert len(hashes) == 10
    assert len(set(hashes)) == 10
    assert interval == 5.0
    cmd = rec.calls[0]
    i = cmd.index("-i")
    assert cmd[i - 2 : i] == ["-skip_frame", "nokey"]
    assert "-threads" in cmd and cmd[cmd.index("-threads") + 1] == "1"
    assert "creationflags" in rec.kwargs[0]


def test_sample_frames_falls_back_on_sparse_keyframes(monkeypatch):
    rec = _Recorder([{"stdout": _frames(3)}, {"stdout": _frames(2)}])
    monkeypatch.setattr(video.subprocess, "run", rec)
    monkeypatch.setattr(video.tools, "which", lambda name: "/bin/ffmpeg")
    hashes, _interval = video.sample_frames("v.mp4", 100.0)
    assert len(hashes) == 2
    assert len(rec.calls) == 2
    assert "-skip_frame" in rec.calls[0]
    assert "-skip_frame" not in rec.calls[1]


def test_sample_frames_no_fallback_when_distinct(monkeypatch):
    rec = _Recorder([{"stdout": _frames(10)}])
    monkeypatch.setattr(video.subprocess, "run", rec)
    monkeypatch.setattr(video.tools, "which", lambda name: "/bin/ffmpeg")
    hashes, _interval = video.sample_frames("v.mp4", 100.0)
    assert len(hashes) == 10
    assert len(rec.calls) == 1
    assert "-skip_frame" in rec.calls[0]


def test_sample_frames_no_fallback_on_zero_duration(monkeypatch):
    rec = _Recorder([{"stdout": b""}])
    monkeypatch.setattr(video.subprocess, "run", rec)
    monkeypatch.setattr(video.tools, "which", lambda name: "/bin/ffmpeg")
    hashes, _interval = video.sample_frames("v.mp4", 0.0)
    assert hashes == []
    assert len(rec.calls) == 1


def test_sample_frames_error(monkeypatch):
    rec = _Recorder([{"returncode": 1, "stdout": b""}])
    monkeypatch.setattr(video.subprocess, "run", rec)
    monkeypatch.setattr(video.tools, "which", lambda name: "/bin/ffmpeg")
    with pytest.raises(video.ProbeError):
        video.sample_frames("v.mp4", 100.0)


def test_probe_passes_creationflags(monkeypatch):
    import json as _json

    payload = _json.dumps(
        {"format": {"duration": "10"}, "streams": [{"codec_type": "video", "width": 2, "height": 2}]}
    ).encode()
    rec = _Recorder([{"stdout": payload}])
    monkeypatch.setattr(video.subprocess, "run", rec)
    monkeypatch.setattr(video.tools, "which", lambda name: "/bin/ffprobe")
    info = video.probe("v.mp4")
    assert info["duration"] == 10.0
    assert "creationflags" in rec.kwargs[0]


def test_fpcalc_raw_passes_creationflags(monkeypatch):
    import subprocess as _subprocess
    from redundex.core.detectors import audio

    class _Rec:
        def __init__(self):
            self.kwargs = None

        def __call__(self, cmd, **kwargs):
            self.kwargs = kwargs
            return SimpleNamespace(
                returncode=0,
                stdout="DURATION=10\nFINGERPRINT=1,2,3\n",
            )

    rec = _Rec()
    monkeypatch.setattr(audio.subprocess, "run", rec)
    monkeypatch.setattr(audio.tools, "which", lambda name: "/bin/fpcalc")
    subs, duration = audio.fpcalc_raw("t.mp3")
    assert subs == [1, 2, 3] and duration == 10.0
    assert "creationflags" in rec.kwargs
