import json
import subprocess

import numpy

from .imagehash import hash_gray_frame

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
