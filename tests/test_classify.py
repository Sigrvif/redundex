from redundex.core.classify import classify
from redundex.core.types import FileKind


def test_classify_common_extensions():
    assert classify("a/b.JPG") is FileKind.IMAGE
    assert classify("x.png") is FileKind.IMAGE
    assert classify("v.MP4") is FileKind.VIDEO
    assert classify("v.mkv") is FileKind.VIDEO
    assert classify("s.flac") is FileKind.AUDIO
    assert classify("s.mp3") is FileKind.AUDIO
    assert classify("d.pdf") is FileKind.DOC
    assert classify("d.txt") is FileKind.DOC
    assert classify("d.md") is FileKind.DOC
    assert classify("a.zip") is FileKind.ARCHIVE
    assert classify("a.7z") is FileKind.ARCHIVE
    assert classify("a.tar") is FileKind.ARCHIVE
    assert classify("a.gz") is FileKind.ARCHIVE


def test_classify_unknown_is_other():
    assert classify("noext") is FileKind.OTHER
    assert classify("weird.xyz") is FileKind.OTHER
