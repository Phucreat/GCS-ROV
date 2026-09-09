# -*- mode: python ; coding: utf-8 -*-
import sys
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = [
    ('GUI', 'GUI'),
    ('AI', 'AI'),
    ('assets', 'assets'),
    ('core', 'core'),
    ('database', 'database'),
    ('network', 'network'),
    ('utils', 'utils'),
    ('3DC.obj', '.'),
    ('3DC.mtl', '.'),
    ('6DC.obj', '.'),
    ('6DC.mtl', '.'),
    ('yolov8n.pt', '.'),
    ('LICENSE.txt', '.'),
]

try:
    datas += collect_data_files('ultralytics')
except Exception:
    pass

try:
    datas += collect_data_files('pyqtgraph')
except Exception:
    pass

hiddenimports = [
    'PyQt6', 'PyQt6.QtCore', 'PyQt6.QtGui', 'PyQt6.QtWidgets', 'PyQt6.QtOpenGLWidgets',
    'pyqtgraph', 'pyqtgraph.opengl',
    'OpenGL', 'OpenGL.GL', 'OpenGL.arrays', 'OpenGL.platform',
    'ultralytics', 'cv2', 'torch', 'torchvision', 'zmq',
    'pygame', 'pygame.joystick', 'pygame.mixer', 'pydantic', 'pymavlink',
    'pymavlink.dialects.v20.ardupilotmega',
    'pyttsx3', 'pyttsx3.drivers', 'pyttsx3.drivers.sapi5',
    'sounddevice', 'speech_recognition', 'requests', 'sqlite3',
    'edge_tts', 'aiohttp', 'asyncio', 'certifi',
    'numpy', 'scipy', 'pybullet', 'json', 'uuid', 'hmac', 'hashlib', 'winreg',
    'core', 'core.licensing', 'core.physics_engine', 'core.autonomous_controller', 'core.updater',
    'core.models.rov_3thruster', 'core.models.rov_6thruster',
    'database', 'database.db_manager', 'database.telemetry_logger', 'database.report_exporter',
    'network', 'network.mavlink_worker', 'network.slam_udp_receiver', 'network.video_receiver',
    'AI', 'AI.agent_brain', 'AI.safety_guard', 'AI.stt_worker', 'AI.tts_worker', 'AI.vad_worker', 'AI.cv_engine',
    'utils', 'utils.path_utils', 'utils.geo_utils'
]

try:
    hiddenimports += collect_submodules('ultralytics')
except Exception:
    pass

a = Analysis(
    ['main.py'],
    pathex=['D:\\python\\GCS_ROV'],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib.tests', 'scipy.tests', 'torch.testing'],
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