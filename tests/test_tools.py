import os
import sys

import pytest

from redundex.core import tools


def test_bundled_tools_dir_frozen(monkeypatch, tmp_path):
    bundle = tmp_path / "bundle"
    (bundle / "tools").mkdir(parents=True)
    ffmpeg = bundle / "tools" / "ffmpeg"
    ffmpeg.write_bytes(b"#!/bin/sh\n")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(bundle / "redundex"))
    assert tools.which("ffmpeg") == str(ffmpeg)


def test_bundled_tools_internal_dir_frozen(monkeypatch, tmp_path):
    bundle = tmp_path / "dist" / "redundex"
    internal = bundle / "_internal" / "tools"
    internal.mkdir(parents=True)
    fpcalc = internal / "fpcalc"
    fpcalc.write_bytes(b"#!/bin/sh\n")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(bundle / "redundex"))
    assert tools.which("fpcalc") == str(fpcalc)


def test_portable_python_parent_tools_dir(monkeypatch, tmp_path):
    root = tmp_path / "portable"
    (root / "tools").mkdir(parents=True)
    fpcalc = root / "tools" / "fpcalc"
    fpcalc.write_bytes(b"#!/bin/sh\n")
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(sys, "executable", str(root / "python" / "python.exe"))
    assert tools.which("fpcalc") == str(fpcalc)


def test_env_var_overrides(monkeypatch, tmp_path):
    custom = tmp_path / "custom-tools"
    custom.mkdir()
    tool = custom / "ffmpeg"
    tool.write_bytes(b"#!/bin/sh\n")
    monkeypatch.setenv("REDUNDEX_TOOLS", str(custom))
    assert tools.which("ffmpeg") == str(tool)


def test_windows_exe_suffix(monkeypatch, tmp_path):
    bundle = tmp_path / "bundle"
    (bundle / "tools").mkdir(parents=True)
    ffmpeg = bundle / "tools" / "ffmpeg.exe"
    ffmpeg.write_bytes(b"x")
    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(bundle / "redundex.exe"))
    assert tools.which("ffmpeg") == str(ffmpeg)


def test_falls_back_to_path(monkeypatch):
    monkeypatch.delenv("REDUNDEX_TOOLS", raising=False)
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(
        tools.shutil, "which", lambda name: f"/usr/bin/{name}"
    )
    assert tools.which("ffprobe") == "/usr/bin/ffprobe"


def test_missing_returns_none(monkeypatch):
    monkeypatch.delenv("REDUNDEX_TOOLS", raising=False)
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(tools.shutil, "which", lambda name: None)
    assert tools.which("fpcalc") is None


def test_source_tree_tools_dir(monkeypatch, tmp_path):
    src = tmp_path / "src"
    pkg = src / "redundex" / "core"
    pkg.mkdir(parents=True)
    (src / "tools").mkdir()
    ffmpeg = src / "tools" / "ffmpeg"
    ffmpeg.write_bytes(b"#!/bin/sh\n")
    monkeypatch.delenv("REDUNDEX_TOOLS", raising=False)
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(tools, "__file__", str(pkg / "tools.py"))
    monkeypatch.setattr(tools.shutil, "which", lambda name: None)
    assert tools.which("ffmpeg") == str(ffmpeg)
