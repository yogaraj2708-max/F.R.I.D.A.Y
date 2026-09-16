# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('C:/Users/Admin/OneDrive/Documents/jarvis voice/friday_ui', 'friday_ui'), ('C:/Users/Admin/OneDrive/Documents/jarvis voice/friday_core', 'friday_core')]
binaries = []
hiddenimports = ['qfluentwidgets', 'qasync', 'certifi', 'win32com', 'win32com.client', 'pythoncom', 'sounddevice', 'pygame', 'speech_recognition', 'edge_tts', 'ollama', 'duckduckgo_search', 'sqlite3', 'friday_ui', 'friday_ui.widgets.command_bar', 'friday_ui.widgets.operations_panel', 'friday_core', 'friday_core.gatekeeper', 'friday_core.system', 'friday_core.web', 'friday_core.calc', 'friday_core.settings', 'friday_core.platform_guard']
tmp_ret = collect_all('qfluentwidgets')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('qasync')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('certifi')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('win32com')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['C:/Users/Admin/OneDrive/Documents/jarvis voice/run_friday_gui.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='FRIDAY_2.0',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='FRIDAY_2.0',
)
