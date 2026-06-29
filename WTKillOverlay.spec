from pathlib import Path
from PyInstaller.utils.hooks import collect_all

root = Path.cwd()
av_datas, av_binaries, av_hiddenimports = collect_all("av")

a = Analysis(
    ["app.py"],
    pathex=[str(root / "src")],
    binaries=av_binaries,
    datas=[
        (str(root / "resources"), "resources"),
        *av_datas,
    ],
    hiddenimports=av_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="WTKillOverlay",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    icon=str(root / "resources" / "app.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="WTKillOverlay",
)
