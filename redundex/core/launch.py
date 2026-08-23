import os
import shutil
import subprocess
import sys

from .tools import subprocess_flags


def open_path(path):
    try:
        if os.name == "nt":
            startfile = getattr(os, "startfile", None)
            if startfile is None:
                return False
            startfile(path)
            return True
        helper = "open" if sys.platform == "darwin" else "xdg-open"
        exe = shutil.which(helper)
        if exe is None:
            return False
        subprocess.run(
            [exe, path], check=True, creationflags=subprocess_flags()
        )
        return True
    except Exception:
        return False
