# -*- mode: python ; coding: utf-8 -*-
"""
F.R.I.D.A.Y. 3.0 — Production Windows PyInstaller Specification
Builds standalone, directory-based production application bundle.
"""

import os
from PyInstaller.utils.hooks import collect_all, collect_submodules

# Base datas: Local application assets and modelfiles
datas = [
    ('friday_ui/assets', 'friday_ui/assets'),
    ('friday_core/router/Modelfile.decider', 'friday_core/router'),
]
binaries = []
hiddenimports = [
    'win32com',
    'win32com.client',
    'pythoncom',
    'pywintypes',
    'win32api',
    'win32gui',
    'win32con',
    'win32process',
    'win32clipboard',
    'comtypes',
    'speech_recognition',
    'pygame',
    'edge_tts',
    'rapidfuzz',
    'numpy',
    'PIL',
    'bs4',
    'sqlite3',
    'certifi',
    'qasync',
    'unittest',
    'unittest.mock',
]

# Collect all submodules for internal packages to guarantee zero missing dynamic imports
hiddenimports += collect_submodules('friday_core')
hiddenimports += collect_submodules('friday_ui')

# Explicitly collect third-party packages requiring native dynamic libraries, data schemas, and runtime templates
packages_to_collect = [
    'qfluentwidgets',
    'certifi',
    'soundfile',
    '_soundfile_data',
    '_sounddevice_data',
    'kokoro_onnx',
    'onnxruntime',
    'faster_whisper',
    'ctranslate2',
    'uiautomation',
    'docx',
    'pypdf',
    'lxml',
    'psutil',
    'mss',
    'ollama',
    'duckduckgo_search',
]

for pkg in packages_to_collect:
    try:
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
        datas += pkg_datas
        binaries += pkg_binaries
        hiddenimports += pkg_hidden
    except Exception as ex:
        print(f"[SPEC_WARNING] collect_all failed for {pkg}: {ex}")

# Exclude unneeded development and test suites from production bundle
excludes = [
    'tests',
    'pytest',
    'tkinter',
    'setuptools',
]

a = Analysis(
    ['run_friday_gui.py'],
    pathex=['.'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='F.R.I.D.A.Y. 3.0',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='friday_ui/assets/friday_icon.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='F.R.I.D.A.Y. 3.0',
)
