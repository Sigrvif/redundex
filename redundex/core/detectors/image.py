from ..types import Match, MatchReason
from .bktree import BKTree
from .imagehash import hamming


def _pair_distance(a, b):
    return hamming(a[0], b[0])


def match_images(fps, threshold=8):
    phash_tree = BKTree(distance=_pair_distance)
    dhash_tree = BKTree(distance=_pair_distance)
    entries = [(ph, dh, path) for path, (ph, dh, _w, _h) in fps.items()]
    for ph, _dh, path in entries:
        phash_tree.add((ph, path))
    for _ph, dh, path in entries:
        dhash_tree.add((dh, path))
    best = {}
    for ph, dh, path in entries:
        for d, other in phash_tree.query((ph, path), threshold):
            if other[1] != path:
                pair = tuple(sorted((path, other[1])))
                best[pair] = min(best.get(pair, 65), d)
        for d, other in dhash_tree.query((dh, path), threshold):
            if other[1] != path:
                pair = tuple(sorted((path, other[1])))
                best[pair] = min(best.get(pair, 65), d)
    matches = []
    for (a, b), d in sorted(best.items()):
        matches.append(
            Match(
                a=a,
                b=b,
                reason=MatchReason.PERCEPTUAL,
                score=1.0 - d / 64.0,
                detail=f"hamming distance {d}/64",
            )
        )
    return matches
