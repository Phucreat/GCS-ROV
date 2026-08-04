# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files

datas = [('GUI', 'GUI'), ('AI', 'AI'), ('assets', 'assets'), ('3DC.obj', '.'), ('3DC.mtl', '.'), ('6DC.obj', '.'), ('6DC.mtl', '.'), ('yolov8n.pt', '.')]
datas += collect_data_files('ultralytics')


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=['PyQt6', 'PyQt6.QtCore', 'PyQt6.QtGui', 'PyQt6.QtWidgets', 'PyQt6.QtOpenGLWidgets', 'pyqtgraph', 'OpenGL', 'OpenGL.GL', 'ultralytics', 'cv2', 'torch', 'zmq', 'pygame', 'pygame.joystick', 'pydantic', 'pymavlink', 'pyttsx3', 'pyttsx3.drivers.sapi5', 'sounddevice'],
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
    name='GCS_ROV',
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
    icon=['GUI\\img\\iconapp.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='GCS_ROV',
)
