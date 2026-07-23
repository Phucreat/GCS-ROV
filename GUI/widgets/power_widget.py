"""
power_widget.py - Power System Visualization Widget
=====================================================
Widget vẽ đồ thị Power System (pin, dòng, công suất, thruster).
Nhúng vào ogl_powersys (frm_power_sys) trong guirov.py.
Dùng QPainter để vẽ trực tiếp — không cần OpenGL cho phần này.

Layout:
  ┌─────────────────────────────────────────────────┐
  │  BATTERY          CURRENT        POWER           │
  │  ████████ 14.8V   ─────── 8.2A   ─── 121.4W     │
  │                                                   │
  │  THRUSTER LOADS (Bar chart)                       │
  │  T1  T2  T3  T4  T5  T6                          │
  │  ██  ██  █   ██  █   ██                          │
  │       VOLTAGE HISTORY ─────────────              │
  └─────────────────────────────────────────────────┘
"""
import math
import numpy as np
from collections import deque
from PyQt6 import QtCore, QtGui, QtWidgets


class PowerWidget(QtWidgets.QWidget):
    """
    Power System visualization widget.
    
    Cách dùng:
        self.power_widget = PowerWidget(parent=self.frm_power_sys)
        # Mỗi frame MAVLink SYS_STATUS:
        self.power_widget.set_battery(voltage_v, current_a, remaining_pct)
        # Mỗi frame physics:
        self.power_widget.set_thruster_loads([t1, t2, t3, t4, t5, t6])  # 0.0-1.0
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
    COLOR_BAR_BG  = QtGui.QColor(20, 35, 55)

    # Ngưỡng cảnh báo pin
    BAT_WARN_PCT  = 30
    BAT_CRIT_PCT  = 15

    HISTORY_LEN   = 120   # ~2 phút với 1Hz
    MAX_ALERTS    = 6     # Số cảnh báo tối đa hiển thị

    def __init__(self, parent=None, n_thrusters: int = 6):
        super().__init__(parent)
        self._n_thrusters    = n_thrusters
        self._voltage        = 16.8
        self._current        = 0.0
        self._remaining_pct  = 100
        self._thruster_loads = [0.0] * n_thrusters
        self._volt_history   = deque([16.8] * self.HISTORY_LEN, maxlen=self.HISTORY_LEN)
        self._curr_history   = deque([0.0]  * self.HISTORY_LEN, maxlen=self.HISTORY_LEN)
        # Alerts: deque of (level, message, timestamp)
        self._alerts: deque  = deque(maxlen=self.MAX_ALERTS)
        self._dive_time_min: float = -1.0   # -1 = chưa tính được
        self._blink_phase   = True          # cho hiệu ứng nhấp nháy CRITICAL
        self.setMinimumHeight(120)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding
        )
        # Timer nhấp nháy cho CRITICAL alerts
        self._blink_timer = QtCore.QTimer(self)
        self._blink_timer.timeout.connect(self._on_blink)
        self._blink_timer.start(600)

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
        """loads: list float 0.0–1.0 cho mỗi thruster."""
        self._thruster_loads = list(loads[:self._n_thrusters])
        while len(self._thruster_loads) < self._n_thrusters:
            self._thruster_loads.append(0.0)
        self.update()

    def set_n_thrusters(self, n: int):
        self._n_thrusters = n
        self._thruster_loads = [0.0] * n
        self.update()

    def add_alert(self, level: str, message: str):
        """
        Thêm cảnh báo mới vào panel.
        level: 'INFO' | 'WARN' | 'CRITICAL'
        """
        import time as _time
        ts = _time.strftime("%H:%M:%S")
        self._alerts.appendleft((level.upper(), message, ts))
        self.update()

    def set_dive_time(self, minutes: float):
        """Cập nhật thời gian lặn còn lại (phút). -1 = chưa xác định."""
        self._dive_time_min = minutes
        self.update()

    def clear_alerts(self):
        self._alerts.clear()
        self.update()

    def _on_blink(self):
        self._blink_phase = not self._blink_phase
        # Chỉ redraw nếu có CRITICAL alert
        if any(a[0] == 'CRITICAL' for a in self._alerts):
            self.update()

    # --------------------------------------------------------
    # VẼ
    # --------------------------------------------------------
    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        # Nền
        p.fillRect(0, 0, w, h, self.COLOR_BG)

        # Chia layout: gauges | thrusters | chart | dive_timer | alerts
        top_h    = int(h * 0.28)
        mid_h    = int(h * 0.25)
        chart_h  = int(h * 0.20)
        timer_h  = int(h * 0.09)
        alerts_h = h - top_h - mid_h - chart_h - timer_h

        self._draw_top_gauges(p, 0, 0, w, top_h)
        self._draw_thruster_bars(p, 0, top_h, w, mid_h)
        self._draw_voltage_chart(p, 0, top_h + mid_h, w, chart_h)
        self._draw_dive_timer(p, 0, top_h + mid_h + chart_h, w, timer_h)
        self._draw_alerts(p, 0, top_h + mid_h + chart_h + timer_h, w, alerts_h)

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

    def _draw_thruster_bars(self, p, x, y, w, h):
        """Vẽ thanh dọc cho từng thruster."""
        n = self._n_thrusters
        if n == 0:
            return
        pad_top = 12
        pad_bot = 18
        bar_area_w = (w - 8) // n
        bar_w = max(6, bar_area_w - 4)
        max_bar_h = h - pad_top - pad_bot

        # Header
        p.setPen(self.COLOR_LABEL)
        p.setFont(QtGui.QFont("Rajdhani", 7, QtGui.QFont.Weight.Bold))
        p.drawText(x + 4, y + 10, "THRUSTER LOADS")

        for i, load in enumerate(self._thruster_loads):
            load = abs(load)
            bx = x + 4 + i * bar_area_w + (bar_area_w - bar_w)//2
            # Nền
            p.setPen(QtCore.Qt.PenStyle.NoPen)
            p.setBrush(self.COLOR_BAR_BG)
            p.drawRoundedRect(bx, y + pad_top, bar_w, max_bar_h, 2, 2)
            # Fill
            fill_h = int(max_bar_h * load)
            bar_color = self._thruster_color(load)
            p.setBrush(bar_color)
            p.drawRoundedRect(
                bx, y + pad_top + (max_bar_h - fill_h),
                bar_w, fill_h, 2, 2
            )
            # Label
            p.setPen(self.COLOR_TEXT)
            p.setFont(QtGui.QFont("Rajdhani", 7))
            p.drawText(bx, y + h - 4, f"T{i+1}")

    def _thruster_color(self, load: float) -> QtGui.QColor:
        if load < 0.5:
            return self.COLOR_CYAN
        elif load < 0.8:
            return self.COLOR_YELLOW
        else:
            return self.COLOR_RED

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

    def _draw_alerts(self, p, x, y, w, h):
        """Vẽ panel cảnh báo cuộn (tối đa MAX_ALERTS dòng)."""
        if h < 14 or not self._alerts:
            return
        pad  = 6
        line_h = max(13, h // (self.MAX_ALERTS + 1))

        # Header
        p.setPen(QtGui.QPen(self.COLOR_BORDER, 1))
        p.drawLine(x + pad, y, x + w - pad, y)
        p.setPen(self.COLOR_LABEL)
        p.setFont(QtGui.QFont("Rajdhani", 7, QtGui.QFont.Weight.Bold))
        p.drawText(x + pad, y + 11, "SYSTEM ALERTS")

        LEVEL_COLOR = {
            'INFO':     self.COLOR_CYAN,
            'WARN':     self.COLOR_YELLOW,
            'CRITICAL': self.COLOR_RED if self._blink_phase else QtGui.QColor(100, 30, 30),
        }
        for i, (lvl, msg, ts) in enumerate(self._alerts):
            ry = y + 14 + i * line_h
            if ry + line_h > y + h:
                break
            color = LEVEL_COLOR.get(lvl, self.COLOR_TEXT)
            # Badge level
            badge_w = 42
            p.fillRect(x + pad, ry + 1, badge_w, line_h - 2, QtGui.QColor(color.red(), color.green(), color.blue(), 30))
            p.setPen(color)
            p.setFont(QtGui.QFont("Rajdhani", 7, QtGui.QFont.Weight.Bold))
            p.drawText(x + pad + 2, ry + line_h - 3, f"{lvl[:4]}")
            # Message
            p.setPen(self.COLOR_TEXT)
            p.setFont(QtGui.QFont("Rajdhani", 7))
            p.drawText(x + pad + badge_w + 4, ry + line_h - 3, f"{ts} {msg}")
