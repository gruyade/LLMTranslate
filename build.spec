# -*- mode: python ; coding: utf-8 -*-
# PyInstaller ビルド設定
# 使用方法: pyinstaller build.spec

import sys
from pathlib import Path

block_cipher = None

a = Analysis(
    ['run.py'],
    pathex=[str(Path('.').resolve())],
    binaries=[],
    datas=[
        ('src/resources/icon.png', 'resources'),
    ],
    hiddenimports=[
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'mss',
        'mss.tools',
        'PIL',
        'PIL.Image',
        'httpx',
        'numpy',
        # 翻訳モジュール（importlib動的インポートのためPyInstallerが自動検出できない）
        'src.core.translations',
        'src.core.translations.en',
        'src.core.translations.ja',
        'src.core.translations.fr',
        'src.core.translations.de',
        'src.core.translations.th',
        'src.core.translations.zh_CN',
        'src.core.translations.zh_TW',
        'src.core.translations.pt_BR',
        'src.core.translations.es_419',
        'src.core.translations.ko',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'scipy',
        'pandas',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='LLMTranslate',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # コンソール非表示
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='src/resources/icon.ico',  # Windowsアイコン
    version_file=None,
)
