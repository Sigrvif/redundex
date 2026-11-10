import os

import blake3
import numpy

from ..types import Match, MatchReason
from .bktree import BKTree
from .imagehash import hamming, phash_gray

_TXT_EXTS = {".txt", ".md"}


def normalize_text(text):
    return "".join(c for c in text.lower() if c.isalnum())


def doc_job(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        import pypdfium2 as pdfium

        doc = pdfium.PdfDocument(path)
        try:
            norm = normalize_text("".join(
                page.get_textpage().get_text_range() for page in doc
            ))
            if norm:
                return path, blake3.blake3(norm.encode("utf-8", "replace")).hexdigest(), None
            pil = doc[0].render(scale=4, grayscale=True).to_pil().resize((32, 32))
            gray = numpy.asarray(pil, dtype=numpy.uint8)
            return path, None, phash_gray(gray.astype(numpy.float64))
        finally:
            doc.close()
    if ext in _TXT_EXTS:
        with open(path, encoding="utf-8", errors="replace") as f:
            norm = normalize_text(f.read())
        if norm:
            return path, blake3.blake3(norm.encode("utf-8", "replace")).hexdigest(), None
        return path, None, None
    return path, None, None


def match_docs(fps, phash_threshold=8):
    by_text = {}
    phash_items = []
    for path, (text_hash, page1) in fps.items():
        if text_hash:
            by_text.setdefault(text_hash, []).append(path)
        if page1 is not None:
            phash_items.append((page1, path))
    matches = []
    for group in by_text.values():
        if len(group) > 1:
            for other in group[1:]:
                matches.append(
                    Match(a=group[0], b=other, reason=MatchReason.SAME_TEXT,
                          score=1.0, detail="identical normalized text")
                )
    if len(phash_items) > 1:
        tree = BKTree(distance=lambda x, y: hamming(x[0], y[0]))
        for item in phash_items:
            tree.add(item)
        seen = set()
        for item in phash_items:
            for _d, other in tree.query(item, phash_threshold):
                if other[1] == item[1]:
                    continue
                pair = tuple(sorted((item[1], other[1])))
                if pair in seen:
                    continue
                seen.add(pair)
                matches.append(
                    Match(a=pair[0], b=pair[1], reason=MatchReason.PERCEPTUAL,
                          score=1.0 - _d / 64.0,
                          detail=f"page-1 hamming distance {_d}/64")
                )
    return matches
