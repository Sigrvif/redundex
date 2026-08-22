import os
import stat

from .classify import classify
from .types import FileEntry

_CACHE_PREFIX = ".redundex.cache.sqlite"


def _normalize(path: str) -> str:
    if os.name == "nt" and len(path) > 240 and not path.startswith("\\\\?\\"):
        return "\\\\?\\" + os.path.abspath(path)
    return path


def walk_folder(root: str, follow_symlinks: bool = False):
    entries = []
    problems = []
    root = os.path.abspath(root)
    for dirpath, dirnames, filenames in os.walk(root, followlinks=follow_symlinks):
        if not follow_symlinks:
            dirnames[:] = [
                d for d in dirnames if not os.path.islink(os.path.join(dirpath, d))
            ]
        for name in filenames:
            p = os.path.join(dirpath, name)
            if name.startswith(_CACHE_PREFIX):
                continue
            if not follow_symlinks and os.path.islink(p):
                continue
            try:
                st = os.stat(p, follow_symlinks=follow_symlinks)
                if not stat.S_ISREG(st.st_mode):
                    continue
                entries.append(
                    FileEntry(
                        path=_normalize(p),
                        size=st.st_size,
                        mtime_ns=st.st_mtime_ns,
                        kind=classify(p),
                    )
                )
            except OSError as exc:
                problems.append({"path": p, "error": str(exc)})
    return entries, problems
