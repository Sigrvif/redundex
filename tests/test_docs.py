from pathlib import Path

from redundex.core.detectors.docs import doc_job, match_docs
from redundex.core.types import MatchReason

# Static PDF fixtures (generated once from the original pymupdf helpers; see
# tests/fixtures/) keep these tests independent of any PDF-writing library.
FIXTURES = Path(__file__).parent / "fixtures"


def _txt(path, text):
    path.write_text(text)
    return str(path)


def _fp(p):
    _, text_hash, page1 = doc_job(p)
    return text_hash, page1


def test_pdf_same_text_matches():
    a = str(FIXTURES / "pdf-text-a.pdf")
    b = str(FIXTURES / "pdf-text-b.pdf")
    fps = {a: _fp(a), b: _fp(b)}
    matches = match_docs(fps)
    assert len(matches) == 1
    assert matches[0].reason is MatchReason.SAME_TEXT


def test_pdf_different_text_no_match():
    a = str(FIXTURES / "pdf-text-a.pdf")
    c = str(FIXTURES / "pdf-text-c.pdf")
    fps = {a: _fp(a), c: _fp(c)}
    assert match_docs(fps) == []


def test_txt_normalization_matches(tmp_path):
    a = _txt(tmp_path / "a.txt", "Same  text,\nwith punctuation!")
    b = _txt(tmp_path / "b.txt", "sametextwithpunctuation")
    fps = {a: _fp(a), b: _fp(b)}
    matches = match_docs(fps)
    assert len(matches) == 1
    assert matches[0].reason is MatchReason.SAME_TEXT


def test_scanned_pdf_phash_fallback():
    a = str(FIXTURES / "pdf-scan-a.pdf")
    b = str(FIXTURES / "pdf-scan-b.pdf")
    c = str(FIXTURES / "pdf-scan-c.pdf")
    fps = {a: _fp(a), b: _fp(b), c: _fp(c)}
    matches = match_docs(fps)
    assert any(m.reason is MatchReason.PERCEPTUAL and {m.a, m.b} == {a, b} for m in matches)
    assert all(c not in (m.a, m.b) for m in matches)
