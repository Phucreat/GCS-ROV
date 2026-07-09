"""
Widgets Package
===============
Chứa các widget tùy chỉnh nhúng vào guirov.py.
"""
from .gl_3d_widget import GLROVWidget
from .gl_compass_3d_widget import GLCompass3DWidget
from .power_widget import PowerWidget
from .settings_dialog import SettingsDialog, QToggleSwitch

__all__ = ["GLROVWidget", "GLCompass3DWidget", "PowerWidget", "SettingsDialog", "QToggleSwitch"]
