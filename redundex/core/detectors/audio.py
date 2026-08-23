import struct
import subprocess

from .. import tools
from ..types import Match, MatchReason


def best_ber(short, long):
    n, m = len(short), len(long)
    if n == 0 or m == 0:
        return 1.0, -1
    if n > m:
        short, long = long, short
        n, m = m, n
    best, best_off = 1.0, 0
    for off in range(m - n + 1):
        errors = sum((a ^ b).bit_count() for a, b in zip(short, long[off : off + n]))
        ber = errors / (32 * n)
        if ber < best:
            best, best_off = ber, off
    return best, best_off


def _band_keys(subs):
    keys = set()
    for v in subs:
        keys.add((0, (v >> 16) & 0xFFFF))
        keys.add((1, v & 0xFFFF))
    return keys


def audio_candidates(fps, min_hits=8, max_bucket=200):
    groups = {}
    for path, subs in fps.items():
        groups.setdefault(tuple(subs), []).append(path)
    pairs = set()
    index = {}
    for subs, members in groups.items():
        ordered = sorted(members)
        rep = ordered[0]
        for other in ordered[1:]:
            pairs.add((rep, other))
        for key in _band_keys(subs):
            index.setdefault(key, []).append(rep)
    counts = {}
    for members in index.values():
        if len(members) < 2 or len(members) > max_bucket:
            continue
        ordered = sorted(members)
        for i in range(len(ordered)):
            for j in range(i + 1, len(ordered)):
                pair = (ordered[i], ordered[j])
                counts[pair] = counts.get(pair, 0) + 1
    pairs.update(pair for pair, c in counts.items() if c >= min_hits)
    return pairs


class FpCalcError(Exception):
    pass


def fpcalc_raw(path, length=120):
    fpcalc = tools.which("fpcalc")
    if fpcalc is None:
        raise FpCalcError("fpcalc not installed")
    try:
        proc = subprocess.run(
            [fpcalc, "-raw", "-length", str(length), path],
            capture_output=True, text=True, timeout=120,
        )
    except subprocess.TimeoutExpired as exc:
        raise FpCalcError("fpcalc timed out") from exc
    if proc.returncode != 0:
        raise FpCalcError(proc.stderr.strip()[:200] or "fpcalc failed")
    duration = 0.0
    hexdata = None
    for line in proc.stdout.splitlines():
        if line.startswith("DURATION="):
            try:
                duration = float(line.split("=", 1)[1])
            except ValueError:
                duration = 0.0
        elif line.startswith("FINGERPRINT="):
            hexdata = line.split("=", 1)[1].strip()
    if not hexdata:
        raise FpCalcError("no fingerprint in output")
    subs = [int(part) for part in hexdata.split(",") if part]
    return subs, duration


def match_audio(fps, ber_threshold=0.30, min_duration_ratio=0.5):
    candidates = audio_candidates({p: v[0] for p, v in fps.items()})
    matches = []
    for a, b in sorted(candidates):
        (subs_a, dur_a), (subs_b, dur_b) = fps[a], fps[b]
        mx = max(dur_a, dur_b)
        if mx > 0 and min(dur_a, dur_b) / mx < min_duration_ratio:
            continue
        ber, _offset = best_ber(subs_a, subs_b)
        if ber <= ber_threshold:
            matches.append(
                Match(
                    a=a, b=b, reason=MatchReason.SAME_TRACK, score=1.0 - ber,
                    detail=f"bit error rate {ber:.3f}",
                )
            )
    return matches


def pack_subs(subs):
    return struct.pack(f"<{len(subs)}I", *subs) if subs else b""


def unpack_subs(blob):
    n = len(blob) // 4
    return list(struct.unpack(f"<{n}I", blob)) if n else []


def fpcalc_job(path):
    subs, duration = fpcalc_raw(path)
    return path, pack_subs(subs), duration
