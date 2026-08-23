from redundex.core import launch


def test_open_path_windows_startfile(monkeypatch):
    calls = []
    monkeypatch.setattr(launch.os, "name", "nt")
    monkeypatch.setattr(launch.os, "startfile", calls.append, raising=False)
    assert launch.open_path("C:\\v\\a.mp4") is True
    assert calls == ["C:\\v\\a.mp4"]


def test_open_path_posix_xdg_open(monkeypatch):
    class Rec:
        def __init__(self):
            self.calls = []

        def __call__(self, cmd, **kwargs):
            self.calls.append((cmd, kwargs))
            return None

    rec = Rec()
    monkeypatch.setattr(launch.os, "name", "posix")
    monkeypatch.setattr(launch.shutil, "which", lambda n: "/usr/bin/xdg-open")
    monkeypatch.setattr(launch.subprocess, "run", rec)
    assert launch.open_path("/tmp/v.mp4") is True
    assert rec.calls[0][0] == ["/usr/bin/xdg-open", "/tmp/v.mp4"]
    assert "creationflags" in rec.calls[0][1]


def test_open_path_mac_open(monkeypatch):
    class Rec:
        def __init__(self):
            self.calls = []

        def __call__(self, cmd, **kwargs):
            self.calls.append(cmd)
            return None

    rec = Rec()
    monkeypatch.setattr(launch.os, "name", "posix")
    monkeypatch.setattr(launch.sys, "platform", "darwin")
    monkeypatch.setattr(launch.shutil, "which", lambda n: "/usr/bin/open")
    monkeypatch.setattr(launch.subprocess, "run", rec)
    assert launch.open_path("/tmp/v.mp4") is True
    assert rec.calls[0] == ["/usr/bin/open", "/tmp/v.mp4"]


def test_open_path_no_helper(monkeypatch):
    monkeypatch.setattr(launch.os, "name", "posix")
    monkeypatch.setattr(launch.sys, "platform", "linux")
    monkeypatch.setattr(launch.shutil, "which", lambda n: None)
    assert launch.open_path("/tmp/v.mp4") is False


def test_open_path_failure_returns_false(monkeypatch):
    def boom(cmd, **kwargs):
        raise RuntimeError("nope")

    monkeypatch.setattr(launch.os, "name", "posix")
    monkeypatch.setattr(launch.shutil, "which", lambda n: "/usr/bin/xdg-open")
    monkeypatch.setattr(launch.subprocess, "run", boom)
    assert launch.open_path("/tmp/v.mp4") is False
