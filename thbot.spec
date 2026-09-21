# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_data_files


# Inclui o driver e o Chromium instalados pelo Playwright para que o
# executável funcione em computadores que não têm Python nem navegador.
playwright_datas = collect_data_files('playwright')

a = Analysis(
    ['thbot.py'],
    pathex=[],
    binaries=[],
    datas=[('thbot_icone.ico', '.'), *playwright_datas, *collect_data_files('customtkinter')],
    hiddenimports=['playwright.sync_api'],
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
    a.binaries,
    a.datas,
    [],
    name='thbot',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['thbot_icone.ico'],
)
