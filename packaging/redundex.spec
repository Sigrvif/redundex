a = Analysis(
    ["entry.py"],
    pathex=[".."],
    binaries=[],
    datas=[("tools/linux", "tools"), ("licenses", "licenses"), ("../THIRD-PARTY-NOTICES.md", "."), ("../LICENSE", ".")],
    hiddenimports=["PySide6.QtSvg"],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter"],
)
a2 = Analysis(
    ["entry-cli.py"],
    pathex=[".."],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "PySide6"],
)
pyz = PYZ(a.pure)
pyz2 = PYZ(a2.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="redundex",
    console=False,
)
exe_cli = EXE(
    pyz2,
    a2.scripts,
    [],
    exclude_binaries=True,
    name="redundex-cli",
    console=True,
)
coll = COLLECT(
    exe, exe_cli, a.binaries, a.zipfiles, a.datas, a2.binaries, a2.zipfiles,
    name="redundex",
)
