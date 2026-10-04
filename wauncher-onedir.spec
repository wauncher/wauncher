# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for the one-folder build: dist\wauncher\wauncher.exe plus an _internal folder.
# Starts faster than the single-file exe because nothing has to be unpacked to a temp folder first.
import os
import re

with open("app/version.py", encoding="utf-8") as fh:
    _version = re.search(r'VERSION\s*=\s*"([^"]+)"', fh.read()).group(1)

datas = [(p, "assets") for p in ("assets/icon.ico", "assets/icon.png") if os.path.exists(p)]

a = Analysis(
    ["run.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=["psutil", "pystray._win32", "PIL.Image", "PIL.ImageDraw"],
    hookspath=[],
    runtime_hooks=[],
    excludes=["numpy", "matplotlib", "PyQt5", "PySide6", "IPython", "pytest", "Crypto", "win32crypt"],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="wauncher",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon="assets/icon.ico" if os.path.exists("assets/icon.ico") else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="wauncher",
)
