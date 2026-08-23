import importlib.util

from . import tools


def check_capabilities():
    return {
        "video": bool(tools.which("ffmpeg") and tools.which("ffprobe")),
        "audio": bool(tools.which("fpcalc")),
        "pdf": importlib.util.find_spec("pymupdf") is not None,
    }


def which_missing():
    return {k for k, v in check_capabilities().items() if not v}
