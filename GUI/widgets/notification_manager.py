"""
notification_manager.py - Log System Helper
============================================
Proxy helper module to direct log and alert messages cleanly to PowerWidget.
No floating toasts or screen-blocking popups.
"""

from __future__ import annotations
from typing import Optional
try:
    from PyQt6.QtCore import QObject, pyqtSignal
except ImportError:
    from PyQt5.QtCore import QObject, pyqtSignal


class NotificationManager(QObject):
    """
    Thread-safe notification dispatcher.
    Routes messages directly to PowerWidget (Event Log + Active Alerts).
    """

    _sig_notify = pyqtSignal(str, str, int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._main_window = parent
        self._sig_notify.connect(self._do_notify)

    def notify(
        self,
        message: str,
        level: str = "INFO",
        duration_ms: int = 4000,
    ) -> None:
        """Thread-safe notify API."""
        self._sig_notify.emit(message, level, duration_ms)

    def _do_notify(self, message: str, level: str, duration_ms: int) -> None:
        """Route to PowerWidget if main_window exists."""
        if hasattr(self._main_window, 'power_widget') and self._main_window.power_widget:
            self._main_window.power_widget.add_log(message, level)
            if level.upper() == 'CRITICAL':
                self._main_window.power_widget.set_active_alert(message, level)
