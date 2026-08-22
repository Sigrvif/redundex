import importlib.util
import shutil


def check_capabilities():
    return {
        "video": bool(shutil.which("ffmpeg") and shutil.which("ffprobe")),
        "audio": bool(shutil.which("fpcalc")),
        "pdf": importlib.util.find_spec("pymupdf") is not None,
    }


def which_missing():
    return {k for k, v in check_capabilities().items() if not v}
