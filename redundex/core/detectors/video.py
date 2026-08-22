import json
import subprocess

import numpy

from ..types import Match, MatchReason
from .imagehash import hamming, hash_gray_frame

FRAME_W, FRAME_H = 160, 90


class ProbeError(Exception):
    pass


def probe(path):
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json",
         "-show_format", "-show_streams", path],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise ProbeError(proc.stderr.strip()[:200] or "ffprobe failed")
    data = json.loads(proc.stdout)
    try:
        duration = float(data.get("format", {}).get("duration", 0.0))
    except (TypeError, ValueError):
        duration = 0.0
    v = next(
        (s for s in data.get("streams", []) if s.get("codec_type") == "video"), None
    )
    if v is None:
        raise ProbeError("no video stream")
    return {
        "duration": duration,
        "width": int(v.get("width", 0)),
        "height": int(v.get("height", 0)),
        "has_audio": any(
            s.get("codec_type") == "audio" for s in data.get("streams", [])
        ),
    }


def sample_frames(path, duration, interval=5.0, max_frames=200):
    if duration <= 0:
        count = 1
    else:
        interval = max(interval, duration / max_frames)
        count = min(max_frames, int(duration / interval) + 1)
    proc = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", path,
         "-vf", f"fps=1/{interval},scale={FRAME_W}:{FRAME_H}",
         "-frames:v", str(count), "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        capture_output=True,
    )
    if proc.returncode != 0:
        raise ProbeError("frame extraction failed")
    frame_size = FRAME_W * FRAME_H
    buf = numpy.frombuffer(proc.stdout, dtype=numpy.uint8)
    hashes = [
        hash_gray_frame(buf[i * frame_size:(i + 1) * frame_size].reshape(FRAME_H, FRAME_W))
        for i in range(len(buf) // frame_size)
    ]
    return hashes, interval


def video_job(path, interval=5.0, max_frames=200):
    info = probe(path)
    hashes, _interval = sample_frames(
        path, info["duration"], interval=interval, max_frames=max_frames
    )
    return path, info["duration"], hashes, info["width"], info["height"]


def frames_agree(a, b, frame_threshold=6):
    return hamming(a, b) <= frame_threshold


def aligned_similarity(h1, h2, frame_threshold=6):
    if not h1 or not h2:
        return 0.0
    dense, sparse = (h1, h2) if len(h1) >= len(h2) else (h2, h1)
    hits = 0
    for j, h in enumerate(dense):
        t = j / (len(dense) - 1) if len(dense) > 1 else 0.0
        idx = round(t * (len(sparse) - 1))
        if frames_agree(h, sparse[idx], frame_threshold):
            hits += 1
    return hits / len(dense)


def best_window(short, long, frame_threshold=6):
    n, m = len(short), len(long)
    if n == 0 or m < n:
        return 0.0, -1
    best_sim, best_off = 0.0, -1
    for off in range(m - n + 1):
        hits = sum(
            1
            for a, b in zip(short, long[off : off + n])
            if frames_agree(a, b, frame_threshold)
        )
        sim = hits / n
        if sim > best_sim:
            best_sim, best_off = sim, off
    return best_sim, best_off


def coarse_signature(hashes):
    n = len(hashes)
    if n == 0:
        return []
    return [hashes[round(k * (n - 1) / 15)] for k in range(16)]


def _bands(h):
    return ((h >> 48) & 0xFFFF, (h >> 32) & 0xFFFF, (h >> 16) & 0xFFFF, h & 0xFFFF)


def coarse_candidates(signatures):
    index = {}
    for path, hashes in signatures.items():
        for h in hashes:
            for band_no, value in enumerate(_bands(h)):
                index.setdefault((band_no, value), set()).add(path)
    counts = {}
    for members in index.values():
        ordered = sorted(members)
        for i in range(len(ordered)):
            for j in range(i + 1, len(ordered)):
                pair = (ordered[i], ordered[j])
                counts[pair] = counts.get(pair, 0) + 1
    return {pair for pair, c in counts.items() if c >= 2}


def _frame_band_set(hashes):
    keys = set()
    for h in hashes:
        for band_no, value in enumerate(_bands(h)):
            keys.add((band_no, value))
    return keys


def containment_candidates(videos, min_hits=8, max_bucket=200):
    index = {}
    for path, hashes in videos.items():
        for key in _frame_band_set(hashes):
            index.setdefault(key, []).append(path)
    counts = {}
    for members in index.values():
        if len(members) > max_bucket:
            continue
        ordered = sorted(members)
        for i in range(len(ordered)):
            for j in range(i + 1, len(ordered)):
                pair = (ordered[i], ordered[j])
                counts[pair] = counts.get(pair, 0) + 1
    return {pair for pair, c in counts.items() if c >= min_hits}


def _format_timecode(seconds):
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def match_videos(fps, video_similarity=0.90, containment_similarity=0.85,
                 frame_threshold=6):
    sigs = {p: coarse_signature(v["hashes"]) for p, v in fps.items()}
    pairs = coarse_candidates(sigs) | containment_candidates(
        {p: v["hashes"] for p, v in fps.items()}
    )
    matches = []
    for a, b in sorted(pairs):
        va, vb = fps[a], fps[b]
        sim = aligned_similarity(va["hashes"], vb["hashes"], frame_threshold)
        if sim >= video_similarity:
            matches.append(
                Match(
                    a=a, b=b, reason=MatchReason.PERCEPTUAL, score=sim,
                    detail=f"sequence similarity {sim:.2f}",
                )
            )
            continue
        short_p, long_p = (a, b) if va["duration"] <= vb["duration"] else (b, a)
        short, long_v = fps[short_p], fps[long_p]
        if not short["hashes"] or len(long_v["hashes"]) < len(short["hashes"]):
            continue
        wsim, offset = best_window(
            short["hashes"], long_v["hashes"], frame_threshold
        )
        if wsim >= containment_similarity:
            step = long_v["duration"] / max(len(long_v["hashes"]), 1)
            at = offset * step
            matches.append(
                Match(
                    a=short_p, b=long_p, reason=MatchReason.CONTAINED_IN,
                    score=wsim,
                    detail=f"at {_format_timecode(at)}",
                )
            )
    return matches
