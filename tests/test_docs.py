import pymupdf
from PIL import Image
import numpy

from redundex.core.detectors.docs import doc_job, match_docs
from redundex.core.types import MatchReason


def _pdf(path, text="Hello redundant world", page_size=(400, 300)):
    doc = pymupdf.open()
    page = doc.new_page(width=page_size[0], height=page_size[1])
    page.insert_text((50, 50), text)
    doc.save(str(path))
    doc.close()
    return str(path)


def _scanned_pdf(path, variant=0):
    arr = numpy.zeros((200, 150), dtype=numpy.uint8)
    arr[:, :75] = 120
    if variant >= 100:
        y, x = numpy.mgrid[0:200, 0:150]
        arr = (((x + y) % 40 < 20) * 255).astype(numpy.uint8)
    else:
        arr[50:90, 30:120] = 230
        if variant:
            arr = numpy.clip(arr.astype(numpy.int16) + variant, 0, 255).astype(numpy.uint8)
    img = str(path) + ".png"
    Image.fromarray(arr).save(img)
    doc = pymupdf.open()
    page = doc.new_page(width=150, height=200)
    page.insert_image(pymupdf.Rect(0, 0, 150, 200), filename=img)
    doc.save(str(path))
    doc.close()
    return str(path)


def _txt(path, text):
    path.write_text(text)
    return str(path)


def _fp(p):
    _, text_hash, page1 = doc_job(p)
    return text_hash, page1


def test_pdf_same_text_matches(tmp_path):
    a = _pdf(tmp_path / "a.pdf", text="Hello redundant world", page_size=(400, 300))
    b = _pdf(tmp_path / "b.pdf", text="Hello  redundant\n WORLD!", page_size=(600, 400))
    fps = {a: _fp(a), b: _fp(b)}
    matches = match_docs(fps)
    assert len(matches) == 1
    assert matches[0].reason is MatchReason.SAME_TEXT


def test_pdf_different_text_no_match(tmp_path):
    a = _pdf(tmp_path / "a.pdf", text="Hello redundant world")
    b = _pdf(tmp_path / "b.pdf", text="Completely other content here")
    fps = {a: _fp(a), b: _fp(b)}
    assert match_docs(fps) == []


def test_txt_normalization_matches(tmp_path):
    a = _txt(tmp_path / "a.txt", "Same  text,\nwith punctuation!")
    b = _txt(tmp_path / "b.txt", "sametextwithpunctuation")
    fps = {a: _fp(a), b: _fp(b)}
    matches = match_docs(fps)
    assert len(matches) == 1
    assert matches[0].reason is MatchReason.SAME_TEXT


def test_scanned_pdf_phash_fallback(tmp_path):
    a = _scanned_pdf(tmp_path / "scan1.pdf")
    b = _scanned_pdf(tmp_path / "scan2.pdf", variant=2)
    c = _scanned_pdf(tmp_path / "other.pdf", variant=100)
    fps = {a: _fp(a), b: _fp(b), c: _fp(c)}
    matches = match_docs(fps)
    assert any(m.reason is MatchReason.PERCEPTUAL and {m.a, m.b} == {a, b} for m in matches)
    assert all(c not in (m.a, m.b) for m in matches)
