import shutil
import subprocess

import pytest

from redundex.core.detectors.audio import (
    audio_candidates,
    best_ber,
    fpcalc_raw,
    match_audio,
)
from redundex.core.types import MatchReason


def _word(i, salt=0):
    return ((i + 1 + salt) * 2654435761) % (2**32)


def test_best_ber_identical():
    seq = [_word(i) for i in range(12)]
    ber, offset = best_ber(seq, seq)
    assert ber == 0.0 and offset == 0


def test_best_ber_finds_offset():
    short = [_word(i) for i in range(10)]
    long = [_word(i, 100) for i in range(3)] + short + [_word(i, 200) for i in range(3)]
    ber, offset = best_ber(short, long)
    assert ber == 0.0
    assert offset == 3


def test_best_ber_unrelated():
    a = [_word(i) for i in range(40)]
    b = [_word(i, 999) for i in range(40)]
    ber, _ = best_ber(a, b)
    assert ber > 0.4


def test_audio_candidates_shared_segment():
    shared = [_word(i) for i in range(10)]
    a = [_word(i, 10) for i in range(5)] + shared
    b = shared + [_word(i, 20) for i in range(5)]
    other = [_word(i, 999) for i in range(15)]
    pairs = audio_candidates({"a.mp3": a, "b.mp3": b, "c.mp3": other})
    assert ("a.mp3", "b.mp3") in pairs
    assert all("c.mp3" not in p for p in pairs)


def test_audio_candidates_empty():
    assert audio_candidates({}) == set()


def test_audio_candidates_identical_content_star():
    track = [_word(i) for i in range(40)]
    fps = {f"t{i}.mp3": track for i in range(50)}
    pairs = audio_candidates(fps)
    assert len(pairs) == 49
    assert all("t0.mp3" in p for p in pairs)


tools = pytest.mark.skipif(
    not (shutil.which("fpcalc") and shutil.which("ffmpeg")),
    reason="fpcalc/ffmpeg not installed",
)


def _make_audio(path, freq=440, duration=30):
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi",
         "-i", f"sine=frequency={freq}:duration={duration}",
         str(path)],
        check=True,
    )
    return str(path)


@tools
def test_fpcalc_raw_parses(tmp_path):
    p = _make_audio(tmp_path / "s.wav")
    subs, duration = fpcalc_raw(p)
    assert 25 <= duration <= 35
    assert len(subs) > 50
    assert all(0 <= v < 2**32 for v in subs)


@tools
def test_same_track_different_format(tmp_path):
    wav = _make_audio(tmp_path / "track.wav")
    ogg = str(tmp_path / "track.ogg")
    subprocess.run(
        ["ffmpeg", "-v", "error", "-i", wav, "-c:a", "libvorbis", ogg],
        check=True,
    )
    fa = fpcalc_raw(wav)
    fb = fpcalc_raw(ogg)
    fps = {"track.wav": fa, "track.ogg": fb}
    matches = match_audio(fps, ber_threshold=0.30)
    assert len(matches) == 1
    assert matches[0].reason is MatchReason.SAME_TRACK


@tools
def test_different_tracks_do_not_match(tmp_path):
    a = _make_audio(tmp_path / "a.wav", freq=440)
    b = _make_audio(tmp_path / "b.wav", freq=2000)
    fps = {"a.wav": fpcalc_raw(a), "b.wav": fpcalc_raw(b)}
    assert match_audio(fps, ber_threshold=0.30) == []
