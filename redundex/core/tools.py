import os
import shutil
import sys


def _candidate_dirs():
    dirs = []
    env = os.environ.get("REDUNDEX_TOOLS")
    if env:
        dirs.append(env)
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        dirs.append(os.path.join(exe_dir, "tools"))
        dirs.append(os.path.join(exe_dir, "_internal", "tools"))
        dirs.append(os.path.join(os.path.dirname(exe_dir), "tools"))
    here = os.path.abspath(__file__)
    root = os.path.dirname(os.path.dirname(os.path.dirname(here)))
    dirs.append(os.path.join(root, "tools"))
    return dirs


def which(name):
    exe = f"{name}.exe" if os.name == "nt" else name
    for d in _candidate_dirs():
        p = os.path.join(d, exe)
        if os.path.isfile(p):
            return p
    return shutil.which(name)
