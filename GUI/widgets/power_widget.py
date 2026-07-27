"""
power_widget.py - Power System + Notification Log Widget
=========================================================
Widget vẽ đồ thị Power System (pin, dòng, công suất) + Log thông báo.
Nhúng vào ogl_powersys (frm_power_sys) trong guirov.py.
Dùng QPainter để vẽ trực tiếp — không cần OpenGL cho phần này.

Layout:
  ┌─────────────────────────────────────────────────┐
  │  BATTERY          CURRENT        POWER           │
  │  ████████ 14.8V   ─────── 8.2A   ─── 121.4W     │
  │                                                   │
  │  📋 EVENT LOG (scrollable list)                   │
  │  12:30:01 [INFO] Kết nối MAVLink                  │
  │  12:30:05 [WARN] Pin thấp 25%                     │
  │  12:30:08 [INFO] AI model loaded                  │
  │                                                   │
  │  ⚠ ACTIVE ALERTS (persistent until resolved)     │
  │  🚨 CRITICAL: Mất kết nối MAVLink                │
  │       VOLTAGE HISTORY                             │
  │  ─────────────────────────────────                │
  │       DIVE TIME: 23:45                            │
  └─────────────────────────────────────────────────┘
"""
import math
import numpy as np
from collections import deque
from PyQt6 import QtCore, QtGui, QtWidgets


class PowerWidget(QtWidgets.QWidget):
    """
    Power System + Event Log + Active Alerts widget.

    Cách dùng:
        self.power_widget = PowerWidget(parent=self.frm_power_sys)
        # Mỗi frame MAVLink SYS_STATUS:
        self.power_widget.set_battery(voltage_v, current_a, remaining_pct)
        # Event log:
        self.power_widget.add_log("Kết nối MAVLink", "SUCCESS")
        # Active alert (persistent):
        self.power_widget.set_active_alert("Mất kết nối MAVLink", "CRITICAL")
        self.power_widget.clear_active_alert()
    """

    # --- Màu sắc ---
    COLOR_BG      = QtGui.QColor(6,  11, 20)
    COLOR_PANEL   = QtGui.QColor(13, 23, 38)
    COLOR_BORDER  = QtGui.QColor(30, 53, 80)
    COLOR_TEXT    = QtGui.QColor(160, 178, 198)
    COLOR_LABEL   = QtGui.QColor(91, 116, 142)
    COLOR_CYAN    = QtGui.QColor(0,  168, 255)
    COLOR_GREEN   = QtGui.QColor(0,  255, 102)
    COLOR_YELLOW  = QtGui.QColor(255, 200, 0)
    COLOR_RED     = QtGui.QColor(255, 70, 70)
    COLOR_ORANGE  = QtGui.QColor(255, 150, 30)
    COLOR_BAR_BG  = QtGui.QColor(20, 35, 55)
    COLOR_LOG_BG  = QtGui.QColor(10, 18, 30)
    COLOR_ALERT_BG = QtGui.QColor(50, 8, 8)

    # Ngưỡng cảnh báo pin
    BAT_WARN_PCT  = 30
    BAT_CRIT_PCT  = 15

    HISTORY_LEN   = 120   # ~2 phút với 1Hz
    MAX_LOG_ITEMS = 50    # Tổng log lưu trữ
    MAX_LOG_VISIBLE = 8   # Số dòng log hiển thị trên màn hình

    def __init__(self, parent=None, n_thrusters: int = 6):
        super().__init__(parent)
        self._n_thrusters    = n_thrusters
        self._voltage        = 16.8
        self._current        = 0.0
        self._remaining_pct  = 100
        self._thruster_loads = [0.0] * n_thrusters
        self._volt_history   = deque([16.8] * self.HISTORY_LEN, maxlen=self.HISTORY_LEN)
        self._curr_history   = deque([0.0]  * self.HISTORY_LEN, maxlen=self.HISTORY_LEN)

        # ── Event Log: danh sách (level, message, timestamp) ──
        self._log_entries: deque = deque(maxlen=self.MAX_LOG_ITEMS)
        self._log_scroll_offset: int = 0   # scroll position

        # ── Active Alerts: persistent until cleared ──
        # list of (level, message, timestamp)
        self._active_alerts: list = []

        # ── Legacy alerts for backward compat ──
        self._alerts: deque = deque(maxlen=6)

        self._dive_time_min: float = -1.0
        self._blink_phase   = True
        self.setMinimumHeight(120)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding
        )
        # Timer nhấp nháy cho CRITICAL alerts
        self._blink_timer = QtCore.QTimer(self)
        self._blink_timer.timeout.connect(self._on_blink)
        self._blink_timer.start(600)

        # Enable mouse wheel scrolling for log
        self.setMouseTracking(True)

    # --------------------------------------------------------
    # API
    # --------------------------------------------------------
    def set_battery(self, voltage_v: float, current_a: float,
                    remaining_pct: int = -1):
        self._voltage   = voltage_v
        self._current   = current_a
        if remaining_pct >= 0:
            self._remaining_pct = remaining_pct
        else:
            self._remaining_pct = self._estimate_pct(voltage_v)
        self._volt_history.append(voltage_v)
        self._curr_history.append(current_a)
        self.update()

    def set_thruster_loads(self, loads: list):
        """loads: list float 0.0–1.0 cho mỗi thruster (kept for compat)."""
        self._thruster_loads = list(loads[:self._n_thrusters])
        while len(self._thruster_loads) < self._n_thrusters:
            self._thruster_loads.append(0.0)

    def set_n_thrusters(self, n: int):
        self._n_thrusters = n
        self._thruster_loads = [0.0] * n

    def add_log(self, message: str, level: str = "INFO"):
        """
        Thêm một dòng log vào danh sách event log.
        level: 'INFO' | 'SUCCESS' | 'WARNING' | 'ERROR' | 'CRITICAL'
        """
        import time as _time
        ts = _time.strftime("%H:%M:%S")
        self._log_entries.appendleft((level.upper(), message, ts))
        self._log_scroll_offset = 0   # auto-scroll to top on new log
        self.update()

    def add_alert(self, level: str, message: str):
        """
        Legacy API — routes to add_log + set_active_alert for CRITICAL.
        """
        self.add_log(message, level)
        if level.upper() == 'CRITICAL':
            self.set_active_alert(message, level)

    def set_active_alert(self, message: str, level: str = "CRITICAL"):
        """
        Đặt cảnh báo khẩn cấp cố định (persistent).
        Không tự biến mất — phải gọi clear_active_alert() để xóa.
        """
        import time as _time
        ts = _time.strftime("%H:%M:%S")
        # Tránh duplicate
        for a in self._active_alerts:
            if a[1] == message:
                return
        self._active_alerts.append((level.upper(), message, ts))
        self.update()

    def clear_active_alert(self, message: str = None):
        """
        Xóa cảnh báo khẩn cấp.
        Nếu message=None → xóa tất cả.
        Nếu message=str → chỉ xóa alert có message đó.
        """
        if message is None:
            self._active_alerts.clear()
        else:
            self._active_alerts = [
                a for a in self._active_alerts if a[1] != message
            ]
        self.update()

    def set_dive_time(self, minutes: float):
        """Cập nhật thời gian lặn còn lại (phút). -1 = chưa xác định."""
        self._dive_time_min = minutes
        self.update()

    def clear_alerts(self):
        self._active_alerts.clear()
        self.update()

    def clear_log(self):
        self._log_entries.clear()
        self._log_scroll_offset = 0
        self.update()

    def _on_blink(self):
        self._blink_phase = not self._blink_phase
        if self._active_alerts:
            self.update()

    # --------------------------------------------------------
    # SCROLL
    # --------------------------------------------------------
    def wheelEvent(self, event):
        """Scroll log list with mouse wheel."""
        delta = event.angleDelta().y()
        max_scroll = max(0, len(self._log_entries) - self.MAX_LOG_VISIBLE)
        if delta > 0:
            self._log_scroll_offset = max(0, self._log_scroll_offset - 1)
        else:
            self._log_scroll_offset = min(max_scroll, self._log_scroll_offset + 1)
        self.update()
        event.accept()

    # --------------------------------------------------------
    # VẼ
    # --------------------------------------------------------
    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        # Nền
        p.fillRect(0, 0, w, h, self.COLOR_BG)

        # Chia layout động:
        #   top_h     = Battery/Current/Power gauges (~22%)
        #   log_h     = Event log list (~35%)
        #   alert_h   = Active alerts (dynamic, 0 if no alerts, else ~15%)
        #   chart_h   = Voltage history (~18%)
        #   timer_h   = Dive time (~10%)
        has_alerts = len(self._active_alerts) > 0

        top_h    = int(h * 0.22)
        alert_h  = int(h * 0.16) if has_alerts else 0
        chart_h  = int(h * 0.18)
        timer_h  = int(h * 0.09)
        log_h    = h - top_h - alert_h - chart_h - timer_h

        y_cursor = 0
        self._draw_top_gauges(p, 0, y_cursor, w, top_h)
        y_cursor += top_h

        self._draw_event_log(p, 0, y_cursor, w, log_h)
        y_cursor += log_h

        if has_alerts:
            self._draw_active_alerts(p, 0, y_cursor, w, alert_h)
            y_cursor += alert_h

        self._draw_voltage_chart(p, 0, y_cursor, w, chart_h)
        y_cursor += chart_h

        self._draw_dive_timer(p, 0, y_cursor, w, timer_h)

        p.end()

    def _draw_top_gauges(self, p, x, y, w, h):
        """Vẽ 3 gauge: BATTERY, CURRENT, POWER."""
        section_w = w // 3

        # --- BATTERY ---
        self._draw_battery_gauge(p, x, y, section_w, h)
        # --- CURRENT ---
        self._draw_simple_gauge(p, x + section_w, y, section_w, h,
                                "CURRENT", f"{self._current:.1f} A",
                                self._current / 30.0,
                                self.COLOR_CYAN)
        # --- POWER ---
        power = self._voltage * self._current
        self._draw_simple_gauge(p, x + 2*section_w, y, section_w, h,
                                "POWER", f"{power:.0f} W",
                                power / 500.0,
                                self.COLOR_YELLOW)

    def _draw_battery_gauge(self, p, x, y, w, h):
        """Vẽ gauge pin với màu thay đổi theo mức."""
        pct = self._remaining_pct
        if pct > self.BAT_WARN_PCT:
            bar_color = self.COLOR_GREEN
        elif pct > self.BAT_CRIT_PCT:
            bar_color = self.COLOR_YELLOW
        else:
            bar_color = self.COLOR_RED

        pad = 6
        # Label
        p.setPen(self.COLOR_LABEL)
        p.setFont(QtGui.QFont("Rajdhani", 7, QtGui.QFont.Weight.Bold))
        p.drawText(x + pad, y + 14, "BATTERY")

        # Giá trị
        p.setPen(bar_color)
        p.setFont(QtGui.QFont("Rajdhani", 10, QtGui.QFont.Weight.Bold))
        p.drawText(x + pad, y + 28, f"{self._voltage:.1f} V")

        # Thanh ngang
        bar_x = x + pad
        bar_y = y + 35
        bar_w = w - pad*2
        bar_h = 8
        p.setPen(QtCore.Qt.PenStyle.NoPen)
        p.setBrush(self.COLOR_BAR_BG)
        p.drawRoundedRect(bar_x, bar_y, bar_w, bar_h, 3, 3)
        fill_w = int(bar_w * pct / 100)
        p.setBrush(bar_color)
        p.drawRoundedRect(bar_x, bar_y, fill_w, bar_h, 3, 3)

        # %
        p.setPen(self.COLOR_TEXT)
        p.setFont(QtGui.QFont("Rajdhani", 8))
        p.drawText(x + pad, y + 55, f"{pct}%")

    def _draw_simple_gauge(self, p, x, y, w, h, label, val_str, frac, color):
        """Gauge đơn giản: label + giá trị + thanh ngang."""
        frac = max(0.0, min(1.0, frac))
        pad  = 6
        p.setPen(self.COLOR_LABEL)
        p.setFont(QtGui.QFont("Rajdhani", 7, QtGui.QFont.Weight.Bold))
        p.drawText(x + pad, y + 14, label)

        p.setPen(color)
        p.setFont(QtGui.QFont("Rajdhani", 10, QtGui.QFont.Weight.Bold))
        p.drawText(x + pad, y + 28, val_str)

        bar_x = x + pad
        bar_y = y + 35
        bar_w = w - pad*2
        bar_h = 8
        p.setPen(QtCore.Qt.PenStyle.NoPen)
        p.setBrush(self.COLOR_BAR_BG)
        p.drawRoundedRect(bar_x, bar_y, bar_w, bar_h, 3, 3)
        p.setBrush(color)
        p.drawRoundedRect(bar_x, bar_y, int(bar_w * frac), bar_h, 3, 3)

    # ── EVENT LOG (danh sách thông báo dạng log) ─────────────
    def _draw_event_log(self, p, x, y, w, h):
        """Vẽ danh sách log sự kiện có thể cuộn."""
        if h < 20:
            return
        pad = 6
        line_h = 16
        header_h = 16

        # Border + Background
        p.setPen(QtGui.QPen(self.COLOR_BORDER, 1))
        p.drawLine(x + pad, y, x + w - pad, y)

        # Header
        p.setPen(self.COLOR_CYAN)
        p.setFont(QtGui.QFont("Rajdhani", 8, QtGui.QFont.Weight.Bold))
        p.drawText(x + pad, y + 12, "📋 EVENT LOG")

        # Count badge
        count = len(self._log_entries)
        if count > 0:
            count_str = str(count)
            p.setPen(self.COLOR_LABEL)
            p.setFont(QtGui.QFont("Rajdhani", 7))
            p.drawText(x + w - pad - 30, y + 12, f"({count})")

        # Log area background
        log_y = y + header_h
        log_h = h - header_h - 2
        p.setPen(QtCore.Qt.PenStyle.NoPen)
        p.setBrush(self.COLOR_LOG_BG)
        p.drawRoundedRect(x + pad, log_y, w - pad*2, log_h, 4, 4)

        if not self._log_entries:
            # Empty state
            p.setPen(QtGui.QColor(60, 80, 100))
            p.setFont(QtGui.QFont("Segoe UI", 8))
            p.drawText(x + pad + 8, log_y + log_h // 2 + 4, "Chưa có thông báo...")
            return

        # Tính số dòng hiển thị
        visible_lines = max(1, (log_h - 4) // line_h)
        self.MAX_LOG_VISIBLE = visible_lines

        # Level color map
        LEVEL_COLORS = {
            'INFO':     (self.COLOR_CYAN,   "ℹ"),
            'SUCCESS':  (self.COLOR_GREEN,  "✓"),
            'WARNING':  (self.COLOR_YELLOW, "⚠"),
            'ERROR':    (self.COLOR_RED,    "✕"),
            'CRITICAL': (self.COLOR_RED,    "🚨"),
            'WARN':     (self.COLOR_YELLOW, "⚠"),
        }

        # Clip painting
        p.setClipRect(x + pad, log_y, w - pad*2, log_h)

        entries = list(self._log_entries)
        start = self._log_scroll_offset
        end = min(start + visible_lines, len(entries))

        for i in range(start, end):
            lvl, msg, ts = entries[i]
            ry = log_y + 2 + (i - start) * line_h
            if ry + line_h > log_y + log_h:
                break

            color, icon = LEVEL_COLORS.get(lvl, (self.COLOR_TEXT, "•"))

            # Alternating row background
            if (i - start) % 2 == 0:
                p.setPen(QtCore.Qt.PenStyle.NoPen)
                p.setBrush(QtGui.QColor(15, 25, 40, 120))
                p.drawRect(x + pad, ry, w - pad*2, line_h)

            # Timestamp
            p.setPen(QtGui.QColor(70, 90, 110))
            p.setFont(QtGui.QFont("Consolas", 7))
            p.drawText(x + pad + 4, ry + line_h - 4, ts)

            # Level icon + color bar
            bar_x = x + pad + 52
            p.setPen(QtCore.Qt.PenStyle.NoPen)
            p.setBrush(QtGui.QColor(color.red(), color.green(), color.blue(), 40))
            p.drawRoundedRect(bar_x, ry + 2, 3, line_h - 4, 1, 1)

            # Message
            p.setPen(color if lvl in ('ERROR', 'CRITICAL', 'WARNING', 'WARN') else self.COLOR_TEXT)
            p.setFont(QtGui.QFont("Segoe UI", 7))
            # Truncate message to fit
            available_w = w - pad*2 - 62
            fm = p.fontMetrics()
            elided = fm.elidedText(msg, QtCore.Qt.TextElideMode.ElideRight, available_w)
            p.drawText(bar_x + 6, ry + line_h - 4, elided)

        p.setClipping(False)

        # Scroll indicator
        if len(entries) > visible_lines:
            scroll_track_h = log_h - 4
            scroll_ratio = visible_lines / len(entries)
            thumb_h = max(12, int(scroll_track_h * scroll_ratio))
            if len(entries) - visible_lines > 0:
                thumb_y = log_y + 2 + int(
                    (scroll_track_h - thumb_h) *
                    self._log_scroll_offset / (len(entries) - visible_lines)
                )
            else:
                thumb_y = log_y + 2
            # Track
            sx = x + w - pad - 4
            p.setPen(QtCore.Qt.PenStyle.NoPen)
            p.setBrush(QtGui.QColor(25, 40, 60))
            p.drawRoundedRect(sx, log_y + 2, 3, scroll_track_h, 1, 1)
            # Thumb
            p.setBrush(QtGui.QColor(0, 168, 255, 120))
            p.drawRoundedRect(sx, thumb_y, 3, thumb_h, 1, 1)

    # ── ACTIVE ALERTS (persistent, won't auto-dismiss) ───────
    def _draw_active_alerts(self, p, x, y, w, h):
        """Vẽ panel cảnh báo khẩn cấp cố định."""
        if h < 14 or not self._active_alerts:
            return
        pad = 6

        # Background đỏ đậm
        bg_alpha = 180 if self._blink_phase else 140
        p.setPen(QtCore.Qt.PenStyle.NoPen)
        p.setBrush(QtGui.QColor(60, 5, 5, bg_alpha))
        p.drawRoundedRect(x + pad, y + 2, w - pad*2, h - 4, 6, 6)

        # Border nhấp nháy
        border_color = self.COLOR_RED if self._blink_phase else QtGui.QColor(120, 30, 30)
        p.setPen(QtGui.QPen(border_color, 1.5))
        p.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(x + pad, y + 2, w - pad*2, h - 4, 6, 6)

        # Header
        header_color = self.COLOR_RED if self._blink_phase else QtGui.QColor(180, 50, 50)
        p.setPen(header_color)
        p.setFont(QtGui.QFont("Rajdhani", 8, QtGui.QFont.Weight.Bold))
        p.drawText(x + pad + 8, y + 16, "🚨 ACTIVE ALERTS")

        # Alert entries
        line_h = 15
        alert_y = y + 20
        for i, (lvl, msg, ts) in enumerate(self._active_alerts):
            ry = alert_y + i * line_h
            if ry + line_h > y + h - 2:
                break

            # Blinking dot
            if self._blink_phase:
                p.setPen(QtCore.Qt.PenStyle.NoPen)
                p.setBrush(self.COLOR_RED)
                p.drawEllipse(x + pad + 10, ry + 3, 6, 6)

            # Message
            p.setPen(QtGui.QColor(255, 180, 180) if self._blink_phase else QtGui.QColor(200, 120, 120))
            p.setFont(QtGui.QFont("Segoe UI", 7, QtGui.QFont.Weight.Bold))
            available_w = w - pad*2 - 24
            fm = p.fontMetrics()
            elided = fm.elidedText(f"[{ts}] {msg}", QtCore.Qt.TextElideMode.ElideRight, available_w)
            p.drawText(x + pad + 20, ry + 11, elided)

    def _draw_voltage_chart(self, p, x, y, w, h):
        """Vẽ biểu đồ lịch sử điện áp."""
        if h < 20:
            return
        pad = 6
        # Header
        p.setPen(self.COLOR_LABEL)
        p.setFont(QtGui.QFont("Rajdhani", 7, QtGui.QFont.Weight.Bold))
        p.drawText(x + pad, y + 11, "VOLTAGE HISTORY")

        # Vẽ đường
        hist = list(self._volt_history)
        if len(hist) < 2:
            return
        v_min = max(min(hist) - 0.5, 0)
        v_max = max(hist) + 0.5
        v_range = v_max - v_min or 1.0

        chart_x = x + pad
        chart_y = y + 15
        chart_w = w - pad*2
        chart_h = h - 20

        pts = []
        for i, v in enumerate(hist):
            px = chart_x + int(i * chart_w / (len(hist) - 1))
            py = chart_y + chart_h - int((v - v_min) / v_range * chart_h)
            pts.append(QtCore.QPointF(px, py))

        path = QtGui.QPainterPath()
        path.moveTo(pts[0])
        for pt in pts[1:]:
            path.lineTo(pt)

        # Fill dưới đường
        fill_path = QtGui.QPainterPath(path)
        fill_path.lineTo(chart_x + chart_w, chart_y + chart_h)
        fill_path.lineTo(chart_x, chart_y + chart_h)
        fill_path.closeSubpath()
        grad = QtGui.QLinearGradient(0, chart_y, 0, chart_y + chart_h)
        grad.setColorAt(0.0, QtGui.QColor(0, 168, 255, 60))
        grad.setColorAt(1.0, QtGui.QColor(0, 168, 255, 5))
        p.setPen(QtCore.Qt.PenStyle.NoPen)
        p.setBrush(QtGui.QBrush(grad))
        p.drawPath(fill_path)

        # Đường chính
        p.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        p.setPen(QtGui.QPen(self.COLOR_CYAN, 1.5))
        p.drawPath(path)

    # --------------------------------------------------------
    # TIỆN ÍCH
    # --------------------------------------------------------
    @staticmethod
    def _estimate_pct(voltage: float,
                      v_min: float = 14.0, v_max: float = 16.8) -> int:
        pct = (voltage - v_min) / (v_max - v_min) * 100
        return max(0, min(100, int(pct)))

    def _draw_dive_timer(self, p, x, y, w, h):
        """Hiển thị đồng hồ đếm ngược thời gian lặn còn lại."""
        if h < 12:
            return
        pad = 6
        # Đường kẻ ngăn cách
        p.setPen(QtGui.QPen(self.COLOR_BORDER, 1))
        p.drawLine(x + pad, y, x + w - pad, y)

        if self._dive_time_min < 0:
            time_str = "DIVE TIME: Calculating..."
            color = self.COLOR_LABEL
        else:
            mins = int(self._dive_time_min)
            secs = int((self._dive_time_min - mins) * 60)
            time_str = f"DIVE TIME REMAINING: {mins:02d}:{secs:02d}"
            if self._dive_time_min < 5:
                color = self.COLOR_RED if self._blink_phase else QtGui.QColor(80, 20, 20)
            elif self._dive_time_min < 15:
                color = self.COLOR_YELLOW
            else:
                color = self.COLOR_GREEN

        p.setPen(color)
        p.setFont(QtGui.QFont("Rajdhani", 8, QtGui.QFont.Weight.Bold))
        p.drawText(x + pad, y + h - 3, time_str)
