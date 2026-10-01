# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files


projeto = Path(SPECPATH).resolve().parent
icone = projeto / 'assets' / 'thbot_icone.ico'


# Inclui o driver e o Chromium instalados pelo Playwright para que o
# executável funcione em computadores que não têm Python nem navegador.
playwright_datas = collect_data_files('playwright')

a = Analysis(
    [str(projeto / 'thbot' / '__main__.py')],
    pathex=[str(projeto)],
    binaries=[],
    datas=[(str(icone), 'assets'), *playwright_datas, *collect_data_files('customtkinter')],
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
    icon=[str(icone)],
)
