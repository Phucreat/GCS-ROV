"""
mission_planner.py - 3D Mission Planning Panel
==============================================
Panel lap ke hoach nhiem vu:
  - Table danh sach waypoints (index, ten, NED x/y/z, depth, hold_time)
  - Them WP bang tay (dialog) hoac tu click 3D widget
  - Upload mission len ROV qua MAVLink
  - Hien thi uoc tinh quang duong + thoi gian
  - Export/Import mission tu JSON file
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, asdict, field
from typing import List, Optional

from PyQt6.QtCore import (
    Qt, QThread, pyqtSignal, QObject, QTimer
)
from PyQt6.QtGui import (
    QColor, QFont, QIcon, QKeySequence, QPalette
)
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QToolBar, QTableWidget, QTableWidgetItem,
    QPushButton, QProgressBar, QDialog, QFormLayout,
    QLineEdit, QDoubleSpinBox, QDialogButtonBox,
    QMessageBox, QFileDialog, QSizePolicy,
    QHeaderView, QAbstractItemView, QFrame,
    QSpacerItem
)

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────
ROV_SPEED_MS: float = 0.5          # m/s cruising speed for ETA estimate
COL_IDX   = 0
COL_NAME  = 1
COL_X     = 2
COL_Y     = 3
COL_DEPTH = 4
COL_HOLD  = 5
COLUMNS   = ["#", "Name", "X (m)", "Y (m)", "Depth (m)", "Hold (s)"]

# Dark-theme colours
CLR_BG          = "#0d1117"
CLR_SURFACE     = "#161b22"
CLR_BORDER      = "#30363d"
CLR_TEXT        = "#e6edf3"
CLR_MUTED       = "#8b949e"
CLR_ACCENT      = "#58a6ff"        # blue highlight
CLR_GREEN       = "#3fb950"
CLR_ORANGE      = "#d29922"
CLR_RED         = "#f85149"
CLR_UPLOAD_BTN  = "#1f6feb"
CLR_UPLOAD_HOV  = "#388bfd"
CLR_SEL_ROW     = "#1c2c3f"
CLR_HEADER      = "#21262d"


# ─────────────────────────────────────────────────────────────────────────────
# Data class
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class WaypointItem:
    """Single mission waypoint in local NED frame."""
    index:   int   = 0
    name:    str   = "WP"
    ned_x:   float = 0.0   # North  (m)
    ned_y:   float = 0.0   # East   (m)
    ned_z:   float = 0.0   # Down   (m, positive down)
    depth_m: float = 0.0   # absolute depth (positive = below surface)
    hold_s:  float = 5.0   # hover / hold time at this waypoint (seconds)
    radius_m: float = 1.0  # acceptance radius (m)

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "WaypointItem":
        return WaypointItem(**{k: v for k, v in d.items()
                               if k in WaypointItem.__dataclass_fields__})


# ─────────────────────────────────────────────────────────────────────────────
# Mission Uploader QThread
# ─────────────────────────────────────────────────────────────────────────────
class MissionUploader(QThread):
    """
    Background thread: simulates (or performs) MAVLink waypoint upload.
    Replace the body of run() with real MAVLink calls when available.
    """
    sig_progress = pyqtSignal(int, int)   # (current, total)
    sig_done     = pyqtSignal(bool, str)  # (success, message)

    def __init__(self, waypoints: List[WaypointItem], parent: Optional[QObject] = None):
        super().__init__(parent)
        self._waypoints = waypoints
        self._abort = False

    def abort(self):
        self._abort = True

    def run(self):
        total = len(self._waypoints)
        if total == 0:
            self.sig_done.emit(False, "Mission is empty – nothing to upload.")
            return

        try:
            # ── Replace this section with real MAVLink upload logic ──────────
            # Example:
            #   vehicle = connect(...)
            #   cmds = vehicle.commands
            #   cmds.clear()
            #   for wp in self._waypoints:
            #       cmds.add(Command(...))
            #   cmds.upload()
            # ─────────────────────────────────────────────────────────────────
            for i, wp in enumerate(self._waypoints, start=1):
                if self._abort:
                    self.sig_done.emit(False, "Upload aborted by user.")
                    return
                # Simulate network latency per waypoint
                time.sleep(0.25)
                self.sig_progress.emit(i, total)

            self.sig_done.emit(True, f"Mission uploaded: {total} waypoints.")

        except Exception as exc:
            self.sig_done.emit(False, f"Upload error: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# Add / Edit Waypoint Dialog
# ─────────────────────────────────────────────────────────────────────────────
class WaypointDialog(QDialog):
    """Modal dialog for creating or editing a WaypointItem."""

    def __init__(self, parent: Optional[QWidget] = None,
                 existing: Optional[WaypointItem] = None,
                 suggested_index: int = 0):
        super().__init__(parent)
        self.setWindowTitle("Add Waypoint" if existing is None else "Edit Waypoint")
        self.setMinimumWidth(360)
        self._build_ui(existing, suggested_index)
        self._apply_styles()

    # ── UI construction ──────────────────────────────────────────────────────
    def _build_ui(self, wp: Optional[WaypointItem], idx: int):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # Title
        title = QLabel("➕  New Waypoint" if wp is None else f"✏️  Edit WP{wp.index}")
        title.setStyleSheet(f"color:{CLR_ACCENT}; font-size:14px; font-weight:bold;")
        layout.addWidget(title)

        # Form
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(10)

        def spin(min_=-9999.0, max_=9999.0, step=0.1, dec=2, suffix=""):
            s = QDoubleSpinBox()
            s.setRange(min_, max_)
            s.setSingleStep(step)
            s.setDecimals(dec)
            s.setSuffix(suffix)
            s.setMinimumWidth(160)
            return s

        self.f_name   = QLineEdit(wp.name   if wp else f"WP{idx:02d}")
        self.f_ned_x  = spin(suffix=" m"); self.f_ned_x.setValue(wp.ned_x  if wp else 0.0)
        self.f_ned_y  = spin(suffix=" m"); self.f_ned_y.setValue(wp.ned_y  if wp else 0.0)
        self.f_depth  = spin(min_=0.0, max_=6000.0, suffix=" m")
        self.f_depth.setValue(wp.depth_m if wp else 0.0)
        self.f_hold   = spin(min_=0.0, max_=3600.0, step=1.0, dec=1, suffix=" s")
        self.f_hold.setValue(wp.hold_s  if wp else 5.0)
        self.f_radius = spin(min_=0.1, max_=100.0, step=0.1, suffix=" m")
        self.f_radius.setValue(wp.radius_m if wp else 1.0)

        form.addRow("Name:",       self.f_name)
        form.addRow("NED X (N):",  self.f_ned_x)
        form.addRow("NED Y (E):",  self.f_ned_y)
        form.addRow("Depth:",      self.f_depth)
        form.addRow("Hold Time:",  self.f_hold)
        form.addRow("Radius:",     self.f_radius)
        layout.addLayout(form)

        # Buttons
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _apply_styles(self):
        self.setStyleSheet(f"""
            QDialog {{
                background: {CLR_BG};
                color: {CLR_TEXT};
            }}
            QLabel {{
                color: {CLR_TEXT};
            }}
            QLineEdit, QDoubleSpinBox {{
                background: {CLR_SURFACE};
                color: {CLR_TEXT};
                border: 1px solid {CLR_BORDER};
                border-radius: 4px;
                padding: 4px 8px;
            }}
            QLineEdit:focus, QDoubleSpinBox:focus {{
                border-color: {CLR_ACCENT};
            }}
            QPushButton {{
                background: {CLR_SURFACE};
                color: {CLR_TEXT};
                border: 1px solid {CLR_BORDER};
                border-radius: 4px;
                padding: 5px 16px;
            }}
            QPushButton:hover {{
                background: {CLR_BORDER};
            }}
        """)

    # ── Result access ─────────────────────────────────────────────────────────
    def get_waypoint(self, index: int) -> WaypointItem:
        """Return a WaypointItem built from the dialog fields."""
        ned_z = self.f_depth.value()   # NED-Z = depth (positive down)
        return WaypointItem(
            index   = index,
            name    = self.f_name.text().strip() or f"WP{index:02d}",
            ned_x   = self.f_ned_x.value(),
            ned_y   = self.f_ned_y.value(),
            ned_z   = ned_z,
            depth_m = self.f_depth.value(),
            hold_s  = self.f_hold.value(),
            radius_m= self.f_radius.value(),
        )


# ─────────────────────────────────────────────────────────────────────────────
# Main Widget
# ─────────────────────────────────────────────────────────────────────────────
class MissionPlanner(QWidget):
    """
    Mission planning panel.

    Signals emitted:
        sig_waypoint_added(WaypointItem)        – new WP appended
        sig_waypoint_removed(int)               – WP at index removed
        sig_upload_started(list[WaypointItem])  – upload thread kicked off
        sig_upload_done(bool, str)              – result of upload
        sig_preview_waypoint(float, float, float) – NED x,y,z for 3-D preview
    """

    sig_waypoint_added    = pyqtSignal(object)          # WaypointItem
    sig_waypoint_removed  = pyqtSignal(int)             # index
    sig_upload_started    = pyqtSignal(list)            # List[WaypointItem]
    sig_upload_done       = pyqtSignal(bool, str)       # (success, message)
    sig_preview_waypoint  = pyqtSignal(float, float, float)  # NED x, y, z

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._waypoints: List[WaypointItem] = []
        self._uploader: Optional[MissionUploader] = None

        self._build_ui()
        self._apply_styles()
        self._update_stats()

    # ══════════════════════════════════════════════════════════════════════════
    # UI Construction
    # ══════════════════════════════════════════════════════════════════════════
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # ── Title bar ────────────────────────────────────────────────────────
        title_row = QHBoxLayout()
        icon_lbl = QLabel("🗺")
        icon_lbl.setStyleSheet("font-size:20px;")
        title_lbl = QLabel("MISSION PLANNER")
        title_lbl.setStyleSheet(
            f"color:{CLR_ACCENT}; font-size:15px; font-weight:bold; "
            f"letter-spacing:2px;"
        )
        title_row.addWidget(icon_lbl)
        title_row.addWidget(title_lbl)
        title_row.addStretch()
        root.addLayout(title_row)

        # ── Divider ──────────────────────────────────────────────────────────
        root.addWidget(self._make_divider())

        # ── Toolbar ──────────────────────────────────────────────────────────
        self.toolbar = self._build_toolbar()
        root.addWidget(self.toolbar)

        # ── Waypoint Table ───────────────────────────────────────────────────
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(False)
        self.table.setShowGrid(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setMinimumHeight(200)

        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(COL_IDX,   QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(COL_NAME,  QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(COL_X,     QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(COL_Y,     QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(COL_DEPTH, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(COL_HOLD,  QHeaderView.ResizeMode.ResizeToContents)

        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.doubleClicked.connect(self._on_table_double_click)
        root.addWidget(self.table, stretch=1)

        # ── Stats label ──────────────────────────────────────────────────────
        self.lbl_stats = QLabel("Waypoints: 0 | Distance: 0.0 m | Est. Time: 0.0 min")
        self.lbl_stats.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.lbl_stats)

        root.addWidget(self._make_divider())

        # ── Upload button ─────────────────────────────────────────────────────
        self.btn_upload = QPushButton("⬆  UPLOAD MISSION")
        self.btn_upload.setMinimumHeight(44)
        self.btn_upload.setObjectName("upload_btn")
        self.btn_upload.clicked.connect(self._on_upload_clicked)
        root.addWidget(self.btn_upload)

        # ── Progress bar ──────────────────────────────────────────────────────
        self.upload_progress = QProgressBar()
        self.upload_progress.setRange(0, 100)
        self.upload_progress.setValue(0)
        self.upload_progress.setVisible(False)
        self.upload_progress.setTextVisible(True)
        self.upload_progress.setFormat("Uploading  %v / %m  waypoints")
        self.upload_progress.setFixedHeight(20)
        root.addWidget(self.upload_progress)

        # ── Status label ──────────────────────────────────────────────────────
        self.lbl_status = QLabel("")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_status.setStyleSheet(f"color:{CLR_MUTED}; font-size:11px;")
        root.addWidget(self.lbl_status)

    # ── Toolbar factory ───────────────────────────────────────────────────────
    def _build_toolbar(self) -> QToolBar:
        tb = QToolBar()
        tb.setMovable(False)
        tb.setFloatable(False)
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        tb.setStyleSheet(f"""
            QToolBar {{
                background: {CLR_SURFACE};
                border: 1px solid {CLR_BORDER};
                border-radius: 6px;
                spacing: 4px;
                padding: 4px;
            }}
            QToolButton {{
                background: transparent;
                color: {CLR_TEXT};
                border: none;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 12px;
            }}
            QToolButton:hover {{
                background: {CLR_BORDER};
            }}
            QToolButton:pressed {{
                background: #3d444d;
            }}
        """)

        def add_btn(text, slot, tip=""):
            act = tb.addAction(text)
            act.setToolTip(tip)
            act.triggered.connect(slot)
            return act

        add_btn("➕ Add",      self._on_add_clicked,       "Add new waypoint")
        add_btn("✏️ Edit",     self._on_edit_clicked,      "Edit selected waypoint")
        tb.addSeparator()
        add_btn("🗑 Remove",   self._on_remove_clicked,    "Remove selected waypoint")
        add_btn("🧹 Clear",    self._on_clear_clicked,     "Clear all waypoints")
        tb.addSeparator()
        self._act_up   = add_btn("▲ Up",    self._on_move_up,   "Move waypoint up")
        self._act_down = add_btn("▼ Down",  self._on_move_down, "Move waypoint down")
        tb.addSeparator()
        add_btn("📥 Import",   self._on_import_json,       "Import mission from JSON")
        add_btn("📤 Export",   self._on_export_json,       "Export mission to JSON")

        return tb

    # ── Helper widgets ────────────────────────────────────────────────────────
    @staticmethod
    def _make_divider() -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"color: {CLR_BORDER};")
        return line

    # ══════════════════════════════════════════════════════════════════════════
    # Styling
    # ══════════════════════════════════════════════════════════════════════════
    def _apply_styles(self):
        self.setStyleSheet(f"""
            /* ── Widget base ──────────────────────────────────── */
            QWidget {{
                background: {CLR_BG};
                color: {CLR_TEXT};
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 12px;
            }}

            /* ── Table ────────────────────────────────────────── */
            QTableWidget {{
                background: {CLR_SURFACE};
                gridline-color: {CLR_BORDER};
                border: 1px solid {CLR_BORDER};
                border-radius: 6px;
                selection-background-color: {CLR_SEL_ROW};
                selection-color: {CLR_ACCENT};
                outline: none;
            }}
            QHeaderView::section {{
                background: {CLR_HEADER};
                color: {CLR_MUTED};
                border: none;
                border-bottom: 1px solid {CLR_BORDER};
                padding: 4px 8px;
                font-weight: bold;
                font-size: 11px;
                letter-spacing: 1px;
            }}
            QTableWidget::item {{
                padding: 4px 8px;
                border-bottom: 1px solid {CLR_BORDER};
            }}
            QTableWidget::item:selected {{
                background: {CLR_SEL_ROW};
                color: {CLR_ACCENT};
            }}

            /* ── Stats label ──────────────────────────────────── */
            #stats_lbl {{
                color: {CLR_MUTED};
                font-size: 11px;
            }}

            /* ── Upload button ────────────────────────────────── */
            QPushButton#upload_btn {{
                background: {CLR_UPLOAD_BTN};
                color: #ffffff;
                border: none;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
                letter-spacing: 1px;
            }}
            QPushButton#upload_btn:hover {{
                background: {CLR_UPLOAD_HOV};
            }}
            QPushButton#upload_btn:pressed {{
                background: #1158b5;
            }}
            QPushButton#upload_btn:disabled {{
                background: #1c2c40;
                color: {CLR_MUTED};
            }}

            /* ── Progress bar ─────────────────────────────────── */
            QProgressBar {{
                background: {CLR_SURFACE};
                border: 1px solid {CLR_BORDER};
                border-radius: 4px;
                text-align: center;
                color: {CLR_TEXT};
                font-size: 11px;
            }}
            QProgressBar::chunk {{
                background: {CLR_GREEN};
                border-radius: 3px;
            }}

            /* ── Scrollbars ───────────────────────────────────── */
            QScrollBar:vertical {{
                background: {CLR_SURFACE};
                width: 8px;
                border-radius: 4px;
            }}
            QScrollBar::handle:vertical {{
                background: {CLR_BORDER};
                border-radius: 4px;
                min-height: 24px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {CLR_MUTED};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
        """)

        # Stats label styling directly
        self.lbl_stats.setObjectName("stats_lbl")
        self.lbl_stats.setStyleSheet(f"color:{CLR_MUTED}; font-size:11px;")

    # ══════════════════════════════════════════════════════════════════════════
    # Table population helpers
    # ══════════════════════════════════════════════════════════════════════════
    def _refresh_table(self):
        """Rebuild the table rows from self._waypoints."""
        self.table.setRowCount(0)
        for wp in self._waypoints:
            self._append_table_row(wp)
        self._update_stats()

    def _append_table_row(self, wp: WaypointItem):
        row = self.table.rowCount()
        self.table.insertRow(row)

        def cell(text, align=Qt.AlignmentFlag.AlignCenter) -> QTableWidgetItem:
            item = QTableWidgetItem(str(text))
            item.setTextAlignment(align)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            return item

        self.table.setItem(row, COL_IDX,   cell(wp.index))
        self.table.setItem(row, COL_NAME,  cell(wp.name, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter))
        self.table.setItem(row, COL_X,     cell(f"{wp.ned_x:+.2f}"))
        self.table.setItem(row, COL_Y,     cell(f"{wp.ned_y:+.2f}"))
        self.table.setItem(row, COL_DEPTH, cell(f"{wp.depth_m:.1f}"))
        self.table.setItem(row, COL_HOLD,  cell(f"{wp.hold_s:.1f}"))

    def _reindex_waypoints(self):
        """Re-assign sequential indices and refresh table."""
        for i, wp in enumerate(self._waypoints):
            wp.index = i + 1
        self._refresh_table()

    # ══════════════════════════════════════════════════════════════════════════
    # Stats calculation
    # ══════════════════════════════════════════════════════════════════════════
    def _calc_stats(self):
        """Return (total_distance_m, total_time_min)."""
        wps = self._waypoints
        dist = 0.0
        hold = sum(wp.hold_s for wp in wps)

        for i in range(1, len(wps)):
            dx = wps[i].ned_x - wps[i-1].ned_x
            dy = wps[i].ned_y - wps[i-1].ned_y
            dz = wps[i].ned_z - wps[i-1].ned_z
            dist += math.sqrt(dx*dx + dy*dy + dz*dz)

        travel_time = dist / ROV_SPEED_MS if ROV_SPEED_MS > 0 else 0.0
        total_time  = (travel_time + hold) / 60.0   # seconds → minutes
        return dist, total_time

    def _update_stats(self):
        n = len(self._waypoints)
        dist, t_min = self._calc_stats()
        self.lbl_stats.setText(
            f"Waypoints: {n}  |  Distance: {dist:.1f} m  |  Est. Time: {t_min:.1f} min"
        )

    # ══════════════════════════════════════════════════════════════════════════
    # Toolbar / button slots
    # ══════════════════════════════════════════════════════════════════════════
    def _on_add_clicked(self):
        next_idx = len(self._waypoints) + 1
        dlg = WaypointDialog(self, suggested_index=next_idx)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            wp = dlg.get_waypoint(next_idx)
            self._add_waypoint(wp)

    def _on_edit_clicked(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self._waypoints):
            return
        wp = self._waypoints[row]
        dlg = WaypointDialog(self, existing=wp, suggested_index=wp.index)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            updated = dlg.get_waypoint(wp.index)
            self._waypoints[row] = updated
            self._refresh_table()
            self.sig_preview_waypoint.emit(updated.ned_x, updated.ned_y, updated.ned_z)

    def _on_remove_clicked(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self._waypoints):
            return
        removed = self._waypoints.pop(row)
        self.sig_waypoint_removed.emit(removed.index)
        self._reindex_waypoints()

    def _on_clear_clicked(self):
        if not self._waypoints:
            return
        reply = QMessageBox.question(
            self, "Clear Mission",
            "Remove all waypoints from the mission?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._waypoints.clear()
            self._refresh_table()

    def _on_move_up(self):
        row = self.table.currentRow()
        if row <= 0:
            return
        self._waypoints[row-1], self._waypoints[row] = \
            self._waypoints[row], self._waypoints[row-1]
        self._reindex_waypoints()
        self.table.selectRow(row - 1)

    def _on_move_down(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self._waypoints) - 1:
            return
        self._waypoints[row+1], self._waypoints[row] = \
            self._waypoints[row], self._waypoints[row+1]
        self._reindex_waypoints()
        self.table.selectRow(row + 1)

    def _on_selection_changed(self):
        row = self.table.currentRow()
        if 0 <= row < len(self._waypoints):
            wp = self._waypoints[row]
            self.sig_preview_waypoint.emit(wp.ned_x, wp.ned_y, wp.ned_z)

    def _on_table_double_click(self):
        self._on_edit_clicked()

    # ── Upload ────────────────────────────────────────────────────────────────
    def _on_upload_clicked(self):
        if not self._waypoints:
            QMessageBox.warning(self, "Empty Mission",
                                "Add at least one waypoint before uploading.")
            return

        if self._uploader and self._uploader.isRunning():
            # Abort running upload
            self._uploader.abort()
            self.btn_upload.setText("⬆  UPLOAD MISSION")
            self.upload_progress.setVisible(False)
            self._set_status("Upload aborted.", CLR_ORANGE)
            return

        self._start_upload()

    def _start_upload(self):
        wps = list(self._waypoints)
        self._uploader = MissionUploader(wps, parent=self)
        self._uploader.sig_progress.connect(self.on_upload_progress)
        self._uploader.sig_done.connect(self._on_upload_done)

        self.upload_progress.setMaximum(len(wps))
        self.upload_progress.setValue(0)
        self.upload_progress.setVisible(True)
        self.btn_upload.setText("⛔  ABORT UPLOAD")
        self._set_status("Uploading mission…", CLR_ACCENT)

        self.sig_upload_started.emit(wps)
        self._uploader.start()

    # ── Upload progress / done ────────────────────────────────────────────────
    def on_upload_progress(self, current: int, total: int):
        """Slot – update progress bar (called from uploader thread via signal)."""
        self.upload_progress.setMaximum(total)
        self.upload_progress.setValue(current)

    def _on_upload_done(self, success: bool, msg: str):
        self.btn_upload.setText("⬆  UPLOAD MISSION")
        self.upload_progress.setVisible(False)
        color = CLR_GREEN if success else CLR_RED
        self._set_status(msg, color)
        self.sig_upload_done.emit(success, msg)
        if not success:
            QMessageBox.critical(self, "Upload Failed", msg)

    # ── Import / Export ───────────────────────────────────────────────────────
    def _on_import_json(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Mission", "", "JSON Files (*.json);;All Files (*)"
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            wps = [WaypointItem.from_dict(d) for d in data]
            self._waypoints = wps
            self._reindex_waypoints()
            self._set_status(f"Imported {len(wps)} waypoints from {path}", CLR_GREEN)
        except Exception as exc:
            QMessageBox.critical(self, "Import Error", str(exc))

    def _on_export_json(self):
        if not self._waypoints:
            QMessageBox.information(self, "Empty Mission", "No waypoints to export.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Mission", "mission.json",
            "JSON Files (*.json);;All Files (*)"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump([wp.to_dict() for wp in self._waypoints], f, indent=2)
            self._set_status(f"Exported to {path}", CLR_GREEN)
        except Exception as exc:
            QMessageBox.critical(self, "Export Error", str(exc))

    # ══════════════════════════════════════════════════════════════════════════
    # Public API
    # ══════════════════════════════════════════════════════════════════════════
    def add_waypoint_from_3d(self, x: float, y: float, z: float):
        """
        Slot: receive a 3-D click from the 3D visualisation widget and
        automatically create a waypoint at those NED coordinates.
        """
        idx = len(self._waypoints) + 1
        wp = WaypointItem(
            index   = idx,
            name    = f"WP{idx:02d}",
            ned_x   = x,
            ned_y   = y,
            ned_z   = z,
            depth_m = abs(z),
            hold_s  = 5.0,
            radius_m= 1.0,
        )
        self._add_waypoint(wp)

    def get_waypoints(self) -> List[WaypointItem]:
        """Return a copy of the current waypoint list."""
        return list(self._waypoints)

    def load_waypoints(self, waypoints: List[WaypointItem]):
        """Programmatically load an entire waypoint list."""
        self._waypoints = list(waypoints)
        self._reindex_waypoints()

    # ══════════════════════════════════════════════════════════════════════════
    # Internal helpers
    # ══════════════════════════════════════════════════════════════════════════
    def _add_waypoint(self, wp: WaypointItem):
        self._waypoints.append(wp)
        self._append_table_row(wp)
        self._update_stats()
        self.sig_waypoint_added.emit(wp)
        self.sig_preview_waypoint.emit(wp.ned_x, wp.ned_y, wp.ned_z)
        # Scroll to the new row
        self.table.scrollToBottom()

    def _set_status(self, msg: str, color: str = CLR_MUTED):
        self.lbl_status.setText(msg)
        self.lbl_status.setStyleSheet(f"color:{color}; font-size:11px;")
        # Auto-clear after 6 s
        QTimer.singleShot(6000, lambda: self.lbl_status.setText(""))
