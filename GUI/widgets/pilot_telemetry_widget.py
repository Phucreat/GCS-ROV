"""
pilot_telemetry_widget.py - Commercial Subsea Pilot Telemetry Glass Cockpit Suite
=================================================================================
Thiết kế giao diện UI/UX chuyên dụng cho Phi công (Pilot) điều khiển ROV:
  - Chế độ PILOT COCKPIT: Các thẻ thông số (Telemetry Cards) trực quan, chữ to rõ nét,
    kèm thước đo đồ hoạ (Visual Gauges & Progress Bars), cảnh báo màu sắc theo ngưỡng an toàn.
  - Phân nhóm dữ liệu khoa học:
      1. 🧭 NAVIGATION & ATTITUDE: La bàn lớn, thước đo thăng bằng Roll/Pitch, góc Yaw.
      2. 🌊 DEPTH & DIVING: Độ sâu số lớn phát quang, thước đo độ sâu, tốc độ lặn/nổi (Vz).
      3. ⚡ POWER SYSTEM: Điện áp pin (Voltage), dòng xả (Current), công suất (Watts) & pin %.
      4. 🚀 DYNAMICS & VELOCITY: Tổng vận tốc (Speed), Surge (Vx), Sway (Vy), công suất đẩy (Throttle).
      5. 📍 POSITION & GPS: Toạ độ NED, nút bấm mở Google Maps vị trí ROV.
  - Chế độ RAW TABLE: Bảng số liệu chi tiết kỹ thuật (dành cho kỹ sư phân tích).
"""

from __future__ import annotations

import math
from typing import Callable, Dict, Optional

from PyQt6 import QtCore, QtGui, QtWidgets


# ═══════════════════════════════════════════════════════════════
# PILOT COCKPIT CANVAS (Custom QPainter Graphic Gauges & Cards)
# ═══════════════════════════════════════════════════════════════
class _PilotCockpitCanvas(QtWidgets.QWidget):
    """Bảng đồng hồ viễn trắc trực quan cao cấp dành riêng cho Pilot."""

    sig_gps_clicked = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_OpaquePaintEvent)

        # Telemetry Cache
        self._roll      = 0.0
        self._pitch     = 0.0
        self._yaw       = 0.0
        self._depth     = 0.0
        self._heading   = 0.0
        self._voltage   = 16.8
        self._current   = 0.0
        self._vel_x     = 0.0
        self._vel_y     = 0.0
        self._vel_z     = 0.0
        self._throttle  = 0.0
        self._pos_ned   = [0.0, 0.0, 0.0]
        self._max_depth = 0.0
        self._gps_text  = "GCS GPS Home"

        self._blink_phase = True
        self._blink_timer = QtCore.QTimer(self)
        self._blink_timer.timeout.connect(self._toggle_blink)
        self._blink_timer.start(500)

        # Fonts
        self._font_xs  = QtGui.QFont("Consolas", 8)
        self._font_sm  = QtGui.QFont("Consolas", 9, QtGui.QFont.Weight.Bold)
        self._font_md  = QtGui.QFont("Consolas", 11, QtGui.QFont.Weight.Bold)
        self._font_lg  = QtGui.QFont("Consolas", 15, QtGui.QFont.Weight.Bold)
        self._font_xl  = QtGui.QFont("Consolas", 20, QtGui.QFont.Weight.Bold)

        self.setMouseTracking(True)
        self._gps_rect = QtCore.QRect()

    def _toggle_blink(self):
        self._blink_phase = not self._blink_phase
        if self._voltage < 14.8 or abs(self._roll) > 35 or abs(self._pitch) > 35:
            self.update()

    def update_telemetry_data(self, **kw):
        for k, v in kw.items():
            attr = f"_{k}"
            if hasattr(self, attr):
                setattr(self, attr, v)
        if abs(self._depth) > self._max_depth:
            self._max_depth = abs(self._depth)
        self.update()

    def mousePressEvent(self, event: QtGui.QMouseEvent):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            if self._gps_rect.contains(event.pos()):
                self.sig_gps_clicked.emit()
        super().mousePressEvent(event)

    def paintEvent(self, event):
        W, H = self.width(), self.height()
        if W < 50 or H < 50:
            return

        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        # ── Nền tối chuyên dụng cho phòng điều khiển ───────────
        p.fillRect(0, 0, W, H, QtGui.QColor(6, 12, 22))

        # Phân chia 4 Thẻ Viễn Trắc chính (2x2 Grid)
        margin = 6
        gap = 6
        card_w = (W - margin * 2 - gap) // 2
        card_h = (H - margin * 2 - gap) // 2

        r1 = QtCore.QRect(margin, margin, card_w, card_h)
        r2 = QtCore.QRect(margin + card_w + gap, margin, W - (margin + card_w + gap) - margin, card_h)
        r3 = QtCore.QRect(margin, margin + card_h + gap, card_w, H - (margin + card_h + gap) - margin)
        r4 = QtCore.QRect(margin + card_w + gap, margin + card_h + gap, W - (margin + card_w + gap) - margin, H - (margin + card_h + gap) - margin)

        self._draw_card_navigation(p, r1)
        self._draw_card_depth(p, r2)
        self._draw_card_power(p, r3)
        self._draw_card_dynamics(p, r4)

        p.end()

    # ──────────────────────────────────────────────────────────
    # CARD 1: NAVIGATION & ATTITUDE
    # ──────────────────────────────────────────────────────────
    def _draw_card_navigation(self, p: QtGui.QPainter, r: QtCore.QRect):
        self._draw_card_frame(p, r, "🧭 NAVIGATION & ATTITUDE", "#00d4ff")

        # 1. Heading lớn
        hdg = self._heading
        cardinal = "N" if (hdg < 22.5 or hdg >= 337.5) else "NE" if hdg < 67.5 else "E" if hdg < 112.5 else "SE" if hdg < 157.5 else "S" if hdg < 202.5 else "SW" if hdg < 247.5 else "W" if hdg < 292.5 else "NW"

        p.setFont(self._font_xl)
        p.setPen(QtGui.QColor(0, 240, 255))
        p.drawText(r.x() + 14, r.y() + 44, f"{hdg:05.1f}°")

        p.setFont(self._font_md)
        p.setPen(QtGui.QColor(255, 215, 0))
        p.drawText(r.x() + 115, r.y() + 42, cardinal)

        # 2. Roll & Pitch Level Bars
        # Roll
        p.setFont(self._font_xs)
        p.setPen(QtGui.QColor(140, 185, 210))
        p.drawText(r.x() + 14, r.y() + 66, "ROLL")

        roll_val = self._roll
        roll_col = QtGui.QColor(0, 255, 120) if abs(roll_val) < 15 else (QtGui.QColor(255, 180, 0) if abs(roll_val) < 30 else QtGui.QColor(255, 70, 70))
        p.setFont(self._font_sm)
        p.setPen(roll_col)
        p.drawText(r.x() + 50, r.y() + 66, f"{roll_val:+05.1f}°")

        # Roll balance bar
        bar_x, bar_y, bar_w, bar_h = r.x() + 105, r.y() + 56, r.width() - 118, 10
        p.fillRect(bar_x, bar_y, bar_w, bar_h, QtGui.QColor(10, 25, 42))
        center_x = bar_x + bar_w // 2
        p.setPen(QtGui.QPen(QtGui.QColor(60, 100, 130), 1))
        p.drawLine(center_x, bar_y - 2, center_x, bar_y + bar_h + 2)

        roll_offset = int((roll_val / 45.0) * (bar_w // 2))
        roll_offset = max(-bar_w // 2, min(bar_w // 2, roll_offset))
        p.fillRect(min(center_x, center_x + roll_offset), bar_y + 1, abs(roll_offset), bar_h - 2, roll_col)

        # Pitch
        p.setFont(self._font_xs)
        p.setPen(QtGui.QColor(140, 185, 210))
        p.drawText(r.x() + 14, r.y() + 84, "PITCH")

        pitch_val = self._pitch
        pitch_col = QtGui.QColor(0, 255, 120) if abs(pitch_val) < 15 else (QtGui.QColor(255, 180, 0) if abs(pitch_val) < 30 else QtGui.QColor(255, 70, 70))
        p.setFont(self._font_sm)
        p.setPen(pitch_col)
        p.drawText(r.x() + 50, r.y() + 84, f"{pitch_val:+05.1f}°")

        # Pitch balance bar
        bar_y2 = r.y() + 74
        p.fillRect(bar_x, bar_y2, bar_w, bar_h, QtGui.QColor(10, 25, 42))
        p.setPen(QtGui.QPen(QtGui.QColor(60, 100, 130), 1))
        p.drawLine(center_x, bar_y2 - 2, center_x, bar_y2 + bar_h + 2)

        pitch_offset = int((pitch_val / 45.0) * (bar_w // 2))
        pitch_offset = max(-bar_w // 2, min(bar_w // 2, pitch_offset))
        p.fillRect(min(center_x, center_x + pitch_offset), bar_y2 + 1, abs(pitch_offset), bar_h - 2, pitch_col)

    # ──────────────────────────────────────────────────────────
    # CARD 2: DEPTH & DIVING
    # ──────────────────────────────────────────────────────────
    def _draw_card_depth(self, p: QtGui.QPainter, r: QtCore.QRect):
        self._draw_card_frame(p, r, "🌊 DEPTH & DIVING", "#00ffcc")

        d_val = abs(self._depth)
        p.setFont(self._font_xl)
        p.setPen(QtGui.QColor(0, 255, 204))
        p.drawText(r.x() + 14, r.y() + 44, f"{d_val:.2f}")

        p.setFont(self._font_md)
        p.setPen(QtGui.QColor(0, 200, 170))
        p.drawText(r.x() + 115, r.y() + 42, "m")

        # Max depth
        p.setFont(self._font_xs)
        p.setPen(QtGui.QColor(130, 180, 200))
        p.drawText(r.x() + 14, r.y() + 64, f"MAX DEPTH: {self._max_depth:.2f} m")

        # Vertical velocity (Climb/Dive rate Vz)
        vz = self._vel_z
        vz_text = f"CLIMB: {abs(vz):.2f} m/s" if vz < -0.05 else (f"DIVE:  {vz:.2f} m/s" if vz > 0.05 else "LEVEL: 0.00 m/s")
        vz_col = QtGui.QColor(0, 255, 120) if abs(vz) < 0.5 else (QtGui.QColor(255, 180, 0) if abs(vz) < 1.2 else QtGui.QColor(255, 80, 80))
        p.setPen(vz_col)
        p.setFont(self._font_xs)
        p.drawText(r.x() + 14, r.y() + 80, vz_text)

        # Depth progress meter
        gauge_x, gauge_y, gauge_w, gauge_h = r.x() + r.width() - 28, r.y() + 24, 16, r.height() - 32
        p.fillRect(gauge_x, gauge_y, gauge_w, gauge_h, QtGui.QColor(8, 22, 36))
        p.setPen(QtGui.QPen(QtGui.QColor(0, 150, 180, 100), 1))
        p.drawRect(gauge_x, gauge_y, gauge_w, gauge_h)

        max_meter = 40.0
        fill_ratio = min(1.0, d_val / max_meter)
        fill_h = int(gauge_h * fill_ratio)
        if fill_h > 0:
            grad = QtGui.QLinearGradient(gauge_x, gauge_y, gauge_x, gauge_y + gauge_h)
            grad.setColorAt(0.0, QtGui.QColor(0, 240, 255))
            grad.setColorAt(1.0, QtGui.QColor(0, 80, 180))
            p.fillRect(gauge_x + 2, gauge_y + gauge_h - fill_h, gauge_w - 4, fill_h, QtGui.QBrush(grad))

    # ──────────────────────────────────────────────────────────
    # CARD 3: POWER SYSTEM
    # ──────────────────────────────────────────────────────────
    def _draw_card_power(self, p: QtGui.QPainter, r: QtCore.QRect):
        v = self._voltage
        is_low = v < 14.8
        card_border = "#ff3366" if (is_low and self._blink_phase) else "#00ff9d"
        self._draw_card_frame(p, r, "⚡ POWER & BATTERY", card_border)

        # 1. Voltage
        v_col = QtGui.QColor(0, 255, 157) if v >= 15.5 else (QtGui.QColor(255, 200, 0) if v >= 14.8 else QtGui.QColor(255, 60, 60))
        p.setFont(self._font_xl)
        p.setPen(v_col)
        p.drawText(r.x() + 14, r.y() + 44, f"{v:.2f}")

        p.setFont(self._font_md)
        p.setPen(v_col.darker(120))
        p.drawText(r.x() + 95, r.y() + 42, "V")

        # Battery Health Bar
        # 4S LiPo: 13.6V (0%) - 16.8V (100%)
        bat_pct = max(0, min(100, int((v - 13.6) / (16.8 - 13.6) * 100)))
        bar_x, bar_y, bar_w, bar_h = r.x() + 14, r.y() + 54, r.width() - 28, 8
        p.fillRect(bar_x, bar_y, bar_w, bar_h, QtGui.QColor(10, 25, 40))
        fill_w = int((bat_pct / 100.0) * (bar_w - 2))
        if fill_w > 0:
            p.fillRect(bar_x + 1, bar_y + 1, fill_w, bar_h - 2, v_col)

        # 2. Current & Power
        curr = self._current
        watts = v * curr
        p.setFont(self._font_xs)
        p.setPen(QtGui.QColor(140, 190, 210))
        p.drawText(r.x() + 14, r.y() + 78, f"CURRENT: {curr:5.2f} A")
        p.drawText(r.x() + 14, r.y() + 92, f"POWER:   {watts:5.1f} W")

        p.setFont(self._font_sm)
        p.setPen(QtGui.QColor(0, 230, 255))
        p.drawText(r.x() + r.width() - 65, r.y() + 85, f"[{bat_pct}%]")

    # ──────────────────────────────────────────────────────────
    # CARD 4: DYNAMICS & NAVIGATION
    # ──────────────────────────────────────────────────────────
    def _draw_card_dynamics(self, p: QtGui.QPainter, r: QtCore.QRect):
        self._draw_card_frame(p, r, "🚀 DYNAMICS & GPS", "#ffaa00")

        # 1. Total Velocity
        speed = math.sqrt(self._vel_x**2 + self._vel_y**2 + self._vel_z**2)
        p.setFont(self._font_lg)
        p.setPen(QtGui.QColor(255, 180, 0))
        p.drawText(r.x() + 14, r.y() + 40, f"{speed:.2f}")

        p.setFont(self._font_xs)
        p.setPen(QtGui.QColor(200, 160, 80))
        p.drawText(r.x() + 65, r.y() + 38, "m/s SPEED")

        # Throttle Load
        p.drawText(r.x() + 130, r.y() + 38, f"THRUST: {int(self._throttle)}%")

        # 2. Velocity breakdown (Vx, Vy)
        p.setFont(self._font_xs)
        p.setPen(QtGui.QColor(130, 180, 200))
        p.drawText(r.x() + 14, r.y() + 58, f"Vx(Surge):{self._vel_x:+5.2f}  Vy(Sway):{self._vel_y:+5.2f}")

        # 3. Interactive GPS Button
        btn_x, btn_y, btn_w, btn_h = r.x() + 12, r.y() + 66, r.width() - 24, 24
        self._gps_rect = QtCore.QRect(btn_x, btn_y, btn_w, btn_h)

        p.setPen(QtCore.Qt.PenStyle.NoPen)
        p.setBrush(QtGui.QColor(12, 35, 58))
        p.drawRoundedRect(self._gps_rect, 4, 4)

        p.setPen(QtGui.QPen(QtGui.QColor(0, 180, 240, 150), 1))
        p.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(self._gps_rect, 4, 4)

        p.setFont(self._font_xs)
        p.setPen(QtGui.QColor(0, 220, 255))
        p.drawText(btn_x + 8, btn_y + 16, f"🗺 Google Maps (X:{self._pos_ned[0]:.1f}, Y:{self._pos_ned[1]:.1f})")

    # ──────────────────────────────────────────────────────────
    # HELPER: DRAW GLASS PANEL FRAME
    # ──────────────────────────────────────────────────────────
    def _draw_card_frame(self, p: QtGui.QPainter, r: QtCore.QRect, title: str, accent_color: str):
        col = QtGui.QColor(accent_color)
        # Background
        p.setPen(QtCore.Qt.PenStyle.NoPen)
        p.setBrush(QtGui.QColor(10, 20, 34))
        p.drawRoundedRect(r, 6, 6)

        # Border
        p.setPen(QtGui.QPen(col.darker(150), 1))
        p.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r, 6, 6)

        # Title bar
        p.setFont(self._font_xs)
        p.setPen(col)
        p.drawText(r.x() + 8, r.y() + 15, title)


# ═══════════════════════════════════════════════════════════════
# PILOT TELEMETRY WIDGET (Dual Mode Suite)
# ═══════════════════════════════════════════════════════════════
class PilotTelemetryWidget(QtWidgets.QWidget):
    """
    Main Telemetry Suite:
      - Mode 1: PILOT COCKPIT (Default): Thẻ số liệu & đồng hồ đồ họa trực quan.
      - Mode 2: RAW TABLE: Bảng dữ liệu chi tiết dạng bảng dành cho kỹ sư.
    """

    def __init__(self, parent=None, on_gps_callback: Optional[Callable] = None):
        super().__init__(parent)
        self._on_gps_callback = on_gps_callback

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(2)

        # ── Header Bar with Segmented Mode Switcher ───────────
        self._header = QtWidgets.QFrame(self)
        self._header.setFixedHeight(28)
        self._header.setStyleSheet("""
            QFrame {
                background: #081626;
                border-bottom: 1px solid #143552;
            }
            QLabel {
                color: #00E5FF;
                font-family: Consolas, Arial;
                font-size: 11px;
                font-weight: bold;
                letter-spacing: 1px;
            }
            QPushButton {
                background: #092038;
                color: #8cb8d6;
                border: 1px solid #144066;
                border-radius: 3px;
                padding: 2px 8px;
                font-family: Consolas, Arial;
                font-size: 9px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #0077aa;
                color: #ffffff;
            }
            QPushButton:checked {
                background: #0088cc;
                color: #ffffff;
                border: 1px solid #00f0ff;
            }
        """)

        h_layout = QtWidgets.QHBoxLayout(self._header)
        h_layout.setContentsMargins(8, 2, 8, 2)
        h_layout.setSpacing(6)

        self.lbl_title = QtWidgets.QLabel("📊 TELEMETRY DATA")
        h_layout.addWidget(self.lbl_title)
        h_layout.addStretch(1)

        self.btn_mode_cockpit = QtWidgets.QPushButton("🎛 PILOT COCKPIT")
        self.btn_mode_cockpit.setCheckable(True)
        self.btn_mode_cockpit.setChecked(True)
        self.btn_mode_cockpit.clicked.connect(lambda: self.set_view_mode("COCKPIT"))
        h_layout.addWidget(self.btn_mode_cockpit)

        self.btn_mode_table = QtWidgets.QPushButton("📋 RAW TABLE")
        self.btn_mode_table.setCheckable(True)
        self.btn_mode_table.setChecked(False)
        self.btn_mode_table.clicked.connect(lambda: self.set_view_mode("TABLE"))
        h_layout.addWidget(self.btn_mode_table)

        main_layout.addWidget(self._header)

        # ── Stacked View ──────────────────────────────────────
        self._stack = QtWidgets.QStackedWidget(self)

        # 1. Pilot Cockpit Canvas View
        self._cockpit = _PilotCockpitCanvas(self)
        if on_gps_callback:
            self._cockpit.sig_gps_clicked.connect(on_gps_callback)
        self._stack.addWidget(self._cockpit)

        # 2. Raw Table View
        self._table = QtWidgets.QTableWidget(self)
        self._setup_raw_table()
        self._stack.addWidget(self._table)

        main_layout.addWidget(self._stack)

    def set_view_mode(self, mode: str):
        if mode == "TABLE":
            self.btn_mode_cockpit.setChecked(False)
            self.btn_mode_table.setChecked(True)
            self._stack.setCurrentWidget(self._table)
        else:
            self.btn_mode_cockpit.setChecked(True)
            self.btn_mode_table.setChecked(False)
            self._stack.setCurrentWidget(self._cockpit)

    def _setup_raw_table(self):
        """Khởi tạo bảng số liệu chi tiết."""
        table = self._table
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(["Sensor", "Value", "Unit"])
        table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        table.setStyleSheet("""
            QTableWidget {
                background-color: #060C17;
                color: #94A9C4;
                alternate-background-color: #0A1424;
                gridline-color: #162B47;
                border: none;
                font-size: 11px;
            }
            QHeaderView::section {
                background-color: #101E33;
                color: #00E5FF;
                border: none;
                border-bottom: 2px solid #00F0FF;
                font-size: 9px;
                font-weight: bold;
                padding: 4px 6px;
                text-transform: uppercase;
            }
            QTableWidget::item {
                padding: 3px 6px;
                border-bottom: 1px solid rgba(27, 47, 74, 0.4);
            }
        """)

        self._telem_rows = {
            "ROLL":      ("Roll",     "°"),
            "PITCH":     ("Pitch",    "°"),
            "YAW":       ("Yaw",      "°"),
            "DEPTH":     ("Depth",    "m"),
            "HEADING":   ("Heading",  "°"),
            "VOLTAGE":   ("Voltage",  "V"),
            "CURRENT":   ("Current",  "A"),
            "VEL_X":     ("Vel X",    "m/s"),
            "VEL_Y":     ("Vel Y",    "m/s"),
            "VEL_Z":     ("Vel Z",    "m/s"),
            "THROTTLE":  ("Throttle", "%"),
            "GPS_MAP":   ("GPS Map Link", "Maps"),
        }
        table.setRowCount(len(self._telem_rows))
        self._telem_items = {}
        for row, (key, (name, unit)) in enumerate(self._telem_rows.items()):
            name_item = QtWidgets.QTableWidgetItem(name)
            name_item.setForeground(QtGui.QBrush(QtGui.QColor(91, 116, 142)))
            table.setItem(row, 0, name_item)

            if key == "GPS_MAP":
                val_item = QtWidgets.QTableWidgetItem("Click to view Map")
                font = QtGui.QFont()
                font.setUnderline(True)
                val_item.setFont(font)
                val_item.setForeground(QtGui.QBrush(QtGui.QColor(0, 168, 255)))
            else:
                val_item = QtWidgets.QTableWidgetItem("—")
                val_item.setForeground(QtGui.QBrush(QtGui.QColor(0, 168, 255)))

            table.setItem(row, 1, val_item)
            unit_item = QtWidgets.QTableWidgetItem(unit)
            unit_item.setForeground(QtGui.QBrush(QtGui.QColor(91, 116, 142)))
            table.setItem(row, 2, unit_item)
            self._telem_items[key] = val_item

        table.cellClicked.connect(self._on_table_cell_clicked)

    def _on_table_cell_clicked(self, row, col):
        if self._table.item(row, 0) and self._table.item(row, 0).text() == "GPS Map Link":
            if self._on_gps_callback:
                self._on_gps_callback()

    # ──────────────────────────────────────────────────────────
    # PUBLIC API FOR MAIN APPLICATION
    # ──────────────────────────────────────────────────────────
    def update_telemetry(
        self,
        roll_deg: float,
        pitch_deg: float,
        yaw_deg: float,
        depth_m: float,
        heading_deg: float,
        voltage_v: float,
        current_a: float,
        vel_x: float,
        vel_y: float,
        vel_z: float,
        throttle_pct: float,
        pos_ned: list
    ):
        """Cập nhật dữ liệu viễn trắc cho cả màn hình Pilot và Raw Table."""
        # 1. Update Pilot Cockpit Canvas
        self._cockpit.update_telemetry_data(
            roll=roll_deg,
            pitch=pitch_deg,
            yaw=yaw_deg,
            depth=depth_m,
            heading=heading_deg,
            voltage=voltage_v,
            current=current_a,
            vel_x=vel_x,
            vel_y=vel_y,
            vel_z=vel_z,
            throttle=throttle_pct,
            pos_ned=pos_ned
        )

        # 2. Update Raw Table
        table_data = {
            "ROLL":     f"{roll_deg:+.1f}",
            "PITCH":    f"{pitch_deg:+.1f}",
            "YAW":      f"{yaw_deg:+.1f}",
            "DEPTH":    f"{depth_m:.2f}",
            "HEADING":  f"{heading_deg:.1f}",
            "VOLTAGE":  f"{voltage_v:.2f}",
            "CURRENT":  f"{current_a:.2f}",
            "VEL_X":    f"{vel_x:.2f}",
            "VEL_Y":    f"{vel_y:.2f}",
            "VEL_Z":    f"{vel_z:.2f}",
            "THROTTLE": f"{throttle_pct:.0f}",
        }
        for k, val_str in table_data.items():
            if k in self._telem_items:
                self._telem_items[k].setText(val_str)

    def update_named_value(self, name: str, value: float):
        """Thêm hoặc cập nhật cảm biến NAMED_VALUE_FLOAT trong Raw Table."""
        table = self._table
        for row in range(table.rowCount()):
            if table.item(row, 0) and table.item(row, 0).text() == name:
                table.item(row, 1).setText(f"{value:.4f}")
                return
        row = table.rowCount()
        table.setRowCount(row + 1)
        name_item = QtWidgets.QTableWidgetItem(name)
        name_item.setForeground(QtGui.QBrush(QtGui.QColor(0, 200, 100)))
        table.setItem(row, 0, name_item)
        val_item = QtWidgets.QTableWidgetItem(f"{value:.4f}")
        val_item.setForeground(QtGui.QBrush(QtGui.QColor(0, 255, 150)))
        table.setItem(row, 1, val_item)
        table.setItem(row, 2, QtWidgets.QTableWidgetItem(""))
