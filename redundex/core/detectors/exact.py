import os
import tarfile
import zipfile

import blake3

from ..types import Match, MatchReason


def blake3_file(path: str, chunk_size: int = 1 << 20) -> str:
    h = blake3.blake3()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk_size)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def archive_listing_hash(path: str):
    ext = os.path.splitext(path)[1].lower()
    members = []
    try:
        if ext == ".zip":
            with zipfile.ZipFile(path) as z:
                for i in z.infolist():
                    members.append((i.filename, i.file_size, i.CRC))
        elif ext in (".tar", ".gz", ".bz2", ".xz"):
            with tarfile.open(path, "r:*") as t:
                for m in t.getmembers():
                    members.append((m.name, m.size, m.mtime))
        elif ext == ".7z":
            try:
                import py7zr
            except ImportError:
                return None
            with py7zr.SevenZipFile(path) as z:
                for i in z.list():
                    members.append((i.filename, i.uncompressed, i.crc32 or 0))
        else:
            return None
    except Exception:
        return None
    members.sort()
    joined = "\x00".join(f"{n}|{s}|{c}" for n, s, c in members)
    return blake3.blake3(joined.encode("utf-8", "replace")).hexdigest()


def hash_job(path):
    return path, blake3_file(path), archive_listing_hash(path)


def match_from_fingerprints(fps):
    by_file_hash = {}
    by_listing = {}
    for path, (fh, listing) in fps.items():
        by_file_hash.setdefault(fh, []).append(path)
        if listing:
            by_listing.setdefault(listing, []).append(path)
    matches = []
    for group in by_file_hash.values():
        if len(group) > 1:
            for other in group[1:]:
                matches.append(
                    Match(
                        a=group[0],
                        b=other,
                        reason=MatchReason.EXACT,
                        score=1.0,
                        detail="identical content",
                    )
                )
    exact_pairs = {(m.a, m.b) for m in matches}
    for group in by_listing.values():
        if len(group) > 1:
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    a, b = sorted((group[i], group[j]))
                    if (a, b) in exact_pairs or fps[a][0] == fps[b][0]:
                        continue
                    matches.append(
                        Match(
                            a=a,
                            b=b,
                            reason=MatchReason.EXACT,
                            score=1.0,
                            detail="same archive contents",
                        )
                    )
    return matches
