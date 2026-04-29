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
        'PIL.ImageChops',
        'PIL.ImageStat',
        'httpx',
        # RapidOCR（capture.py で使用）
        'rapidocr_onnxruntime',
        'onnxruntime',
        'cv2',
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
        # --- サードパーティ（未使用） ---
        'tkinter',
        'matplotlib',
        'scipy',
        'pandas',
        'setuptools',
        'pkg_resources',
        'distutils',
        # --- PySide6 未使用モジュール ---
        'PySide6.Qt3DAnimation',
        'PySide6.Qt3DCore',
        'PySide6.Qt3DExtras',
        'PySide6.Qt3DInput',
        'PySide6.Qt3DLogic',
        'PySide6.Qt3DRender',
        'PySide6.QtBluetooth',
        'PySide6.QtCharts',
        'PySide6.QtDataVisualization',
        'PySide6.QtDesigner',
        'PySide6.QtHelp',
        'PySide6.QtLocation',
        'PySide6.QtMultimedia',
        'PySide6.QtMultimediaWidgets',
        'PySide6.QtNfc',
        'PySide6.QtOpenGL',
        'PySide6.QtOpenGLWidgets',
        'PySide6.QtPositioning',
        'PySide6.QtPrintSupport',
        'PySide6.QtQml',
        'PySide6.QtQuick',
        'PySide6.QtQuickControls2',
        'PySide6.QtQuickWidgets',
        'PySide6.QtRemoteObjects',
        'PySide6.QtScxml',
        'PySide6.QtSensors',
        'PySide6.QtSerialBus',
        'PySide6.QtSerialPort',
        'PySide6.QtSpatialAudio',
        'PySide6.QtSql',
        'PySide6.QtSvg',
        'PySide6.QtSvgWidgets',
        'PySide6.QtTest',
        'PySide6.QtUiTools',
        'PySide6.QtWebChannel',
        'PySide6.QtWebEngineCore',
        'PySide6.QtWebEngineQuick',
        'PySide6.QtWebEngineWidgets',
        'PySide6.QtWebSockets',
        'PySide6.QtXml',
        # --- 標準ライブラリ（未使用） ---
        'unittest',
        'doctest',
        'difflib',
        'pydoc',
        'xmlrpc',
        'http.server',
        'ftplib',
        'imaplib',
        'poplib',
        'smtplib',
        'sqlite3',
        'turtle',
        'curses',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# one-dir モード: %TEMP% への展開が不要になりアンチウイルスの誤検知を回避
exe = EXE(
    pyz,
    a.scripts,
    [],                         # one-dir: binaries/datas は COLLECT に渡す
    exclude_binaries=True,      # one-dir の必須設定
    name='LLMTranslate',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,              # コンソール非表示
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='src/resources/icon.ico',
    version_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='LLMTranslate',        # dist/LLMTranslate/ フォルダに出力
)
