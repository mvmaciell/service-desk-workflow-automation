# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec para MegaHub Monitor.

Build:
    pip install pyinstaller
    pyinstaller megahub-monitor.spec

Output: dist/megahub-monitor/ (one-folder distribution)
"""

import os
from pathlib import Path

block_cipher = None
project_root = os.path.abspath(".")

a = Analysis(
    ["main.py"],
    pathex=[project_root],
    binaries=[],
    datas=[
        ("config/*.toml", "config"),
        (".env.example", "."),
    ],
    hiddenimports=[
        "pystray",
        "pystray._win32",
        "PIL",
        "PIL.Image",
        "PIL.ImageDraw",
        "tkinter",
        "tkinter.ttk",
        "tkinter.messagebox",
        "tkinter.filedialog",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="megahub-monitor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="megahub-monitor",
)
