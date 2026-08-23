import importlib.util

from redundex.core import tools
from redundex.core.capabilities import check_capabilities, which_missing


def test_all_present(monkeypatch):
    monkeypatch.setattr(tools, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: object())
    assert check_capabilities() == {"video": True, "audio": True, "pdf": True}
    assert which_missing() == set()


def test_all_missing(monkeypatch):
    monkeypatch.setattr(tools, "which", lambda name: None)
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
    assert check_capabilities() == {"video": False, "audio": False, "pdf": False}
    assert which_missing() == {"video", "audio", "pdf"}


def test_only_ffprobe_missing(monkeypatch):
    monkeypatch.setattr(
        tools, "which", lambda name: "/usr/bin/ffmpeg" if name == "ffmpeg" else None
    )
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: object())
    assert check_capabilities() == {"video": False, "audio": False, "pdf": True}
