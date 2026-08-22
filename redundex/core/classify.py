import os

from .types import FileKind

_IMAGE = {"jpg", "jpeg", "png", "gif", "bmp", "webp", "tif", "tiff", "heic", "avif"}
_VIDEO = {"mp4", "mkv", "avi", "mov", "webm", "wmv", "m4v", "mpg", "mpeg", "ts", "flv"}
_AUDIO = {"mp3", "flac", "ogg", "oga", "wav", "m4a", "aac", "wma", "opus"}
_DOC = {"pdf", "txt", "md"}
_ARCHIVE = {"zip", "7z", "tar", "gz", "bz2", "xz"}

_SETS = (
    (_IMAGE, FileKind.IMAGE),
    (_VIDEO, FileKind.VIDEO),
    (_AUDIO, FileKind.AUDIO),
    (_DOC, FileKind.DOC),
    (_ARCHIVE, FileKind.ARCHIVE),
)


def classify(path: str) -> FileKind:
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    for exts, kind in _SETS:
        if ext in exts:
            return kind
    return FileKind.OTHER
