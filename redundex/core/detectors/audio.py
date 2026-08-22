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
    index = {}
    for path, subs in fps.items():
        for key in _band_keys(subs):
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
