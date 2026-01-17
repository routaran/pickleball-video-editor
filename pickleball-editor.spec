# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for Pickleball Video Editor
# Generated for PyInstaller 6.0+

import sys
from pathlib import Path

block_cipher = None

# Project root directory
project_root = Path(SPECPATH)

# Application metadata
app_name = 'pickleball-editor'
app_version = '0.1.0'

# Source directory
src_dir = project_root / 'src'

# Resources directory (if it exists)
resources_dir = project_root / 'resources'

# -----------------------------------------------------------------------------
# Analysis - Collect all source files and dependencies
# -----------------------------------------------------------------------------
a = Analysis(
    # Entry point
    [str(src_dir / 'main.py')],

    # Additional paths to search for imports
    pathex=[
        str(src_dir),
        str(project_root),
    ],

    # Binary dependencies (shared libraries)
    binaries=[],

    # Data files to include
    datas=[
        # Include resources directory if it exists
        (str(resources_dir), 'resources') if resources_dir.exists() else None,
    ],

    # Hidden imports (modules not automatically detected)
    hiddenimports=[
        # Core application modules
        'src.app',
        'src.main',

        # Core business logic
        'src.core.models',
        'src.core.score_state',
        'src.core.rally_manager',
        'src.core.session_manager',

        # Video layer
        'src.video.player',
        'src.video.probe',

        # UI layer
        'src.ui.main_window',
        'src.ui.setup_dialog',
        'src.ui.review_mode',
        'src.ui.config_dialog',

        # UI widgets
        'src.ui.widgets.timeline',
        'src.ui.widgets.rally_list',
        'src.ui.widgets.score_display',
        'src.ui.widgets.video_controls',

        # UI dialogs
        'src.ui.dialogs.export_dialog',
        'src.ui.dialogs.about_dialog',

        # Output generators
        'src.output.kdenlive_generator',
        'src.output.subtitle_generator',
        'src.output.debug_export',

        # PyQt6 modules
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'PyQt6.QtMultimedia',
        'PyQt6.QtMultimediaWidgets',

        # python-mpv
        'mpv',

        # XML processing
        'lxml',
        'lxml.etree',
        'xml.etree.ElementTree',

        # Standard library modules that may not be auto-detected
        'json',
        'pathlib',
        'dataclasses',
        'functools',
        'hashlib',
        'subprocess',
        'shutil',
        'tempfile',
    ],

    # Modules to exclude from bundling
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Test frameworks
        'pytest',
        'pytest_qt',
        '_pytest',

        # Development tools
        'ruff',
        'mypy',
        'black',
        'pylint',

        # Documentation tools
        'sphinx',
        'docutils',

        # Unused standard library modules (reduces size)
        'tkinter',
        'turtle',
        'test',
        'unittest',
        'pydoc',
        'distutils',

        # Other heavy modules not needed
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
    ],

    # Disable noarchive for better compression
    noarchive=False,

    # Optimize imports
    optimize=2,
)

# Remove None entries from datas
a.datas = [item for item in a.datas if item is not None]

# -----------------------------------------------------------------------------
# PYZ - Python archive
# -----------------------------------------------------------------------------
pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=block_cipher,
)

# -----------------------------------------------------------------------------
# EXE - Executable (directory bundle mode)
# -----------------------------------------------------------------------------
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,  # Binaries go in COLLECT
    name=app_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,      # Strip symbols to reduce size
    upx=True,        # Enable UPX compression
    console=False,   # GUI application (no console window)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# -----------------------------------------------------------------------------
# COLLECT - Bundle all files into a directory
# -----------------------------------------------------------------------------
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=True,
    upx=True,
    upx_exclude=[],
    name=app_name,
)
