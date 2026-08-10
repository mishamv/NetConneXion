# -*- mode: python ; coding: utf-8 -*-
# NetConneXion v2.0 — PyInstaller spec
# Сборка: pyinstaller NetConneXion.spec
# Результат: dist\NetConneXion\NetConneXion.exe

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files

ROOT = Path(SPEC).parent  # корень проекта

block_cipher = None

a = Analysis(
    [str(ROOT / 'quickip' / 'ui_qt' / 'main_window.py')],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        # Ресурсы приложения
        (str(ROOT / 'data'),                          'data'),
        (str(ROOT / 'quickip' / 'ui_qt' / 'qss'),    'quickip/ui_qt/qss'),
        (str(ROOT / 'quickip' / 'ui_qt' / 'assets'), 'quickip/ui_qt/assets'),
        # openpyxl — шаблоны и данные (обязательно для записи xlsx)
        *collect_data_files('openpyxl'),
    ],
    hiddenimports=[
        # pywin32 — DPAPI vault
        'win32crypt',
        'win32ctypes',
        'win32ctypes.pywin32',
        'pywintypes',
        # PySide6 — нужные модули
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'PySide6.QtNetwork',
        # Внутренние модули quickip
        'quickip.app.bootstrap',
        'quickip.ui_qt.pages.wifi_page',
        'quickip.ui_qt.pages.profiles_page',
        'quickip.ui_qt.pages.tools_page',
        'quickip.ui_qt.pages.settings_page',
        'quickip.features.wifi.presenter',
        'quickip.features.wifi.service',
        'quickip.features.wifi.repository',
        'quickip.features.wifi.netsh_parser',
        'quickip.features.wifi.xml_builder',
        'quickip.features.profiles.presenter',
        'quickip.features.profiles.service',
        'quickip.features.profiles.import_export',
        'quickip.core.security.vault',
        'quickip.core.security.keyring_vault',
        'quickip.shared.privilege_check',
        'quickip.features.auto_switch',
        # keyring backends (Windows Credential Manager)
        'keyring',
        'keyring.backends',
        'keyring.backends.Windows',
        # Excel support
        'openpyxl',
        'openpyxl.styles',
        'openpyxl.utils',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Исключаем ненужное — уменьшает размер
        'tkinter',
        'matplotlib',
        'numpy',
        'PIL',
        'scipy',
        'pandas',
        'IPython',
        'PyQt5',
        'PyQt6',
        'wx',
        'gi',
        'test',
        'unittest',
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
    [],
    exclude_binaries=True,
    name='NetConneXion',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,                        # сжатие UPX (опционально)
    console=False,                   # без консольного окна
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / 'data' / 'app.ico'),      # иконка exe
    uac_admin=False,                 # elevation через ShellExecuteW в main()
    version=str(ROOT / 'version_info.txt') if (ROOT / 'version_info.txt').exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[
        'vcruntime140.dll',
        'python310.dll',
        'PySide6',
    ],
    name='NetConneXion',
)
