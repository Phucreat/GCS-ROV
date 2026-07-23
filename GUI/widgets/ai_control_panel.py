"""
ai_control_panel.py - AI Vision Control Panel
=============================================
Panel cai dat AI: bat/tat detection, chon target class,
confidence threshold, bat auto-track.
Nhung vao tab hoac dock widget.

Ket noi voi AIVisionProcessor:
  panel.sig_detection_enabled  → processor can be started/stopped
  panel.sig_model_changed      → processor.set_model_path()
  panel.sig_confidence_changed → processor.set_confidence()
  panel.sig_auto_track_enabled → processor.set_auto_track()
  panel.sig_track_class_changed→ processor.set_tracking_target()
  panel.sig_track_gain_changed → mavlink speed scalar

  processor.sig_fps            → panel.update_stats(fps, n, id)
"""

from __future__ import annotations

import os
from typing import Optional

try:
    from PyQt6.QtCore import Qt, pyqtSignal
    from PyQt6.QtGui import QFont, QColor
    from PyQt6.QtWidgets import (
        QCheckBox,
        QComboBox,
        QDoubleSpinBox,
        QFileDialog,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QListWidget,
        QListWidgetItem,
        QPushButton,
        QSlider,
        QSizePolicy,
        QSpacerItem,
        QVBoxLayout,
        QWidget,
    )
    _PYQT6 = True
except ImportError:
    from PyQt5.QtCore import Qt, pyqtSignal
    from PyQt5.QtGui import QFont, QColor
    from PyQt5.QtWidgets import (
        QCheckBox,
        QComboBox,
        QDoubleSpinBox,
        QFileDialog,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QListWidget,
        QListWidgetItem,
        QPushButton,
        QSlider,
        QSizePolicy,
        QSpacerItem,
        QVBoxLayout,
        QWidget,
    )
    _PYQT6 = False


# ---------------------------------------------------------------------------
# Dark-theme style sheet (consistent with GCS ROV palette)
# ---------------------------------------------------------------------------
_PANEL_STYLESHEET = """
/* ─── Global ─────────────────────────────────────────────────── */
QWidget {
    background-color: #1a1d23;
    color: #d0d7e3;
    font-family: 'Segoe UI', 'Roboto', sans-serif;
    font-size: 12px;
}

/* ─── GroupBox ────────────────────────────────────────────────── */
QGroupBox {
    background-color: #21252d;
    border: 1px solid #3a4050;
    border-radius: 6px;
    margin-top: 14px;
    padding: 8px 6px 6px 6px;
    font-weight: bold;
    font-size: 11px;
    color: #7eb8f7;
    letter-spacing: 0.5px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 4px;
}

/* ─── CheckBox ────────────────────────────────────────────────── */
QCheckBox {
    spacing: 6px;
    color: #d0d7e3;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #4a5568;
    border-radius: 3px;
    background: #2d3340;
}
QCheckBox::indicator:checked {
    background: #3b82f6;
    border-color: #3b82f6;
    image: none;
}
QCheckBox::indicator:hover {
    border-color: #60a5fa;
}

/* ─── ComboBox ────────────────────────────────────────────────── */
QComboBox {
    background-color: #2d3340;
    border: 1px solid #4a5568;
    border-radius: 4px;
    padding: 4px 8px;
    color: #d0d7e3;
    min-height: 24px;
}
QComboBox:hover   { border-color: #60a5fa; }
QComboBox:focus   { border-color: #3b82f6; }
QComboBox::drop-down {
    border: none;
    width: 20px;
}
QComboBox QAbstractItemView {
    background: #2d3340;
    border: 1px solid #4a5568;
    selection-background-color: #3b82f6;
    color: #d0d7e3;
    outline: none;
}

/* ─── Slider ──────────────────────────────────────────────────── */
QSlider::groove:horizontal {
    height: 4px;
    background: #3a4050;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: #3b82f6;
    border: 2px solid #60a5fa;
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}
QSlider::handle:horizontal:hover { background: #60a5fa; }
QSlider::sub-page:horizontal {
    background: #3b82f6;
    border-radius: 2px;
}

/* ─── ListWidget ──────────────────────────────────────────────── */
QListWidget {
    background-color: #2d3340;
    border: 1px solid #4a5568;
    border-radius: 4px;
    color: #d0d7e3;
    outline: none;
}
QListWidget::item { padding: 4px 8px; }
QListWidget::item:selected {
    background: #3b82f6;
    color: #ffffff;
    border-radius: 3px;
}
QListWidget::item:hover { background: #374151; }

/* ─── PushButton ──────────────────────────────────────────────── */
QPushButton {
    background-color: #2d3340;
    border: 1px solid #4a5568;
    border-radius: 5px;
    color: #d0d7e3;
    padding: 5px 14px;
    min-height: 26px;
}
QPushButton:hover  { background: #374151; border-color: #60a5fa; }
QPushButton:pressed { background: #1e40af; border-color: #3b82f6; }
QPushButton#btn_browse {
    background: #1e3a5f;
    border-color: #3b82f6;
    color: #93c5fd;
}
QPushButton#btn_browse:hover { background: #1e40af; }
QPushButton#btn_lockon {
    background: #1e3a5f;
    border-color: #22d3ee;
    color: #67e8f9;
    font-weight: bold;
}
QPushButton#btn_lockon:hover  { background: #164e63; border-color: #06b6d4; }
QPushButton#btn_lockon[locked="true"] {
    background: #064e3b;
    border-color: #10b981;
    color: #6ee7b7;
}

/* ─── DoubleSpinBox ───────────────────────────────────────────── */
QDoubleSpinBox {
    background: #2d3340;
    border: 1px solid #4a5568;
    border-radius: 4px;
    padding: 3px 6px;
    color: #d0d7e3;
    min-height: 24px;
}
QDoubleSpinBox:hover { border-color: #60a5fa; }
QDoubleSpinBox:focus { border-color: #3b82f6; }
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
    background: #3a4050;
    border: none;
    width: 18px;
}
QDoubleSpinBox::up-button:hover,
QDoubleSpinBox::down-button:hover { background: #4a5568; }

/* ─── Labels ──────────────────────────────────────────────────── */
QLabel#lbl_conf_val {
    color: #60a5fa;
    font-weight: bold;
    min-width: 40px;
    qproperty-alignment: AlignRight;
}
QLabel#lbl_stat_fps    { color: #34d399; font-weight: bold; }
QLabel#lbl_stat_det    { color: #fbbf24; font-weight: bold; }
QLabel#lbl_stat_track  { color: #a78bfa; font-weight: bold; }
"""


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
def _make_label(text: str, obj_name: str = "") -> QLabel:
    lbl = QLabel(text)
    if obj_name:
        lbl.setObjectName(obj_name)
    return lbl


# ---------------------------------------------------------------------------
# AIControlPanel
# ---------------------------------------------------------------------------
class AIControlPanel(QWidget):
    """
    Dark-themed control panel for the GCS AI Vision subsystem.

    Signals
    -------
    sig_detection_enabled   : bool   – AI detection on/off
    sig_model_changed       : str    – absolute path of the selected model
    sig_confidence_changed  : float  – confidence threshold [0.0 – 1.0]
    sig_auto_track_enabled  : bool   – auto-track on/off
    sig_track_class_changed : str    – class name chosen for tracking
    sig_track_gain_changed  : float  – proportional gain for track commands
    """

    # Public signals
    sig_detection_enabled  = pyqtSignal(bool)
    sig_model_changed      = pyqtSignal(str)
    sig_confidence_changed = pyqtSignal(float)
    sig_auto_track_enabled = pyqtSignal(bool)
    sig_track_class_changed = pyqtSignal(str)
    sig_track_gain_changed  = pyqtSignal(float)

    # Pre-defined model entries:  (display label,  model file)
    _MODEL_PRESETS = [
        ("yolov8n  (fast)",   "yolov8n.pt"),
        ("yolov8s",           "yolov8s.pt"),
        ("Custom…",           ""),
    ]

    # Available target classes
    _TARGET_CLASSES = ["Diver", "Pipe", "Debris", "All"]

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self._custom_model_path: str = ""
        self._lock_on_active: bool = False

        self._build_ui()
        self._connect_signals()
        self.setStyleSheet(_PANEL_STYLESHEET)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

    # ------------------------------------------------------------------ #
    #  UI construction                                                     #
    # ------------------------------------------------------------------ #
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(10)

        root.addWidget(self._build_detection_group())
        root.addWidget(self._build_tracking_group())
        root.addWidget(self._build_stats_group())
        root.addSpacerItem(
            QSpacerItem(0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        )

    # ── Detection group ───────────────────────────────────────────────── #
    def _build_detection_group(self) -> QGroupBox:
        grp = QGroupBox("⬡  DETECTION")
        lay = QVBoxLayout(grp)
        lay.setSpacing(8)

        # Enable checkbox
        self.chk_enable = QCheckBox("Enable AI Detection")
        self.chk_enable.setChecked(False)
        lay.addWidget(self.chk_enable)

        # Model selector
        self.cmb_model = QComboBox()
        for label, _ in self._MODEL_PRESETS:
            self.cmb_model.addItem(label)
        lay.addWidget(self.cmb_model)

        # Browse button
        self.btn_browse = QPushButton("📂  Browse Model")
        self.btn_browse.setObjectName("btn_browse")
        lay.addWidget(self.btn_browse)

        # Confidence slider row
        conf_row = QHBoxLayout()
        conf_row.addWidget(_make_label("Confidence:"))
        self.sld_conf = QSlider(Qt.Orientation.Horizontal)
        self.sld_conf.setRange(0, 100)
        self.sld_conf.setValue(50)
        self.sld_conf.setTickInterval(10)
        conf_row.addWidget(self.sld_conf, stretch=1)
        self.lbl_conf_val = _make_label("50 %", "lbl_conf_val")
        conf_row.addWidget(self.lbl_conf_val)
        lay.addLayout(conf_row)

        # Target classes list
        lay.addWidget(_make_label("Target Classes:"))
        self.lst_classes = QListWidget()
        self.lst_classes.setSelectionMode(
            QListWidget.SelectionMode.MultiSelection
        )
        self.lst_classes.setMaximumHeight(88)
        for cls in self._TARGET_CLASSES:
            item = QListWidgetItem(cls)
            self.lst_classes.addItem(item)
        # Select "All" by default
        self.lst_classes.item(self._TARGET_CLASSES.index("All")).setSelected(True)
        lay.addWidget(self.lst_classes)

        return grp

    # ── Tracking group ────────────────────────────────────────────────── #
    def _build_tracking_group(self) -> QGroupBox:
        grp = QGroupBox("◎  TRACKING")
        lay = QVBoxLayout(grp)
        lay.setSpacing(8)

        # Auto-track checkbox
        self.chk_autotrack = QCheckBox("Enable Auto-Track")
        self.chk_autotrack.setChecked(False)
        lay.addWidget(self.chk_autotrack)

        # Track class selector
        tc_row = QHBoxLayout()
        tc_row.addWidget(_make_label("Track Class:"))
        self.cmb_track_class = QComboBox()
        for cls in ["Diver", "Pipe", "Debris"]:
            self.cmb_track_class.addItem(cls)
        tc_row.addWidget(self.cmb_track_class, stretch=1)
        lay.addLayout(tc_row)

        # Gain spinbox
        gain_row = QHBoxLayout()
        gain_row.addWidget(_make_label("Track Gain:"))
        self.spn_gain = QDoubleSpinBox()
        self.spn_gain.setRange(0.1, 2.0)
        self.spn_gain.setSingleStep(0.1)
        self.spn_gain.setValue(1.0)
        self.spn_gain.setDecimals(2)
        gain_row.addWidget(self.spn_gain, stretch=1)
        lay.addLayout(gain_row)

        # Lock-On button
        self.btn_lockon = QPushButton("🎯  Lock On")
        self.btn_lockon.setObjectName("btn_lockon")
        self.btn_lockon.setCheckable(True)
        lay.addWidget(self.btn_lockon)

        return grp

    # ── Stats group ───────────────────────────────────────────────────── #
    def _build_stats_group(self) -> QGroupBox:
        grp = QGroupBox("📊  STATS")
        lay = QVBoxLayout(grp)
        lay.setSpacing(6)

        self.lbl_fps   = _make_label("FPS:        --", "lbl_stat_fps")
        self.lbl_det   = _make_label("Detections: --", "lbl_stat_det")
        self.lbl_track = _make_label("Tracking:   --", "lbl_stat_track")

        for lbl in (self.lbl_fps, self.lbl_det, self.lbl_track):
            lbl.setFont(QFont("Courier New", 11, QFont.Weight.Bold))
            lay.addWidget(lbl)

        return grp

    # ------------------------------------------------------------------ #
    #  Signal wiring                                                       #
    # ------------------------------------------------------------------ #
    def _connect_signals(self) -> None:
        self.chk_enable.toggled.connect(self._on_detection_toggled)
        self.cmb_model.currentIndexChanged.connect(self._on_model_selected)
        self.btn_browse.clicked.connect(self._on_browse_model)
        self.sld_conf.valueChanged.connect(self._on_conf_changed)
        self.chk_autotrack.toggled.connect(self._on_autotrack_toggled)
        self.cmb_track_class.currentTextChanged.connect(
            self.sig_track_class_changed.emit
        )
        self.spn_gain.valueChanged.connect(self.sig_track_gain_changed.emit)
        self.btn_lockon.toggled.connect(self._on_lockon_toggled)

    # ------------------------------------------------------------------ #
    #  Slots – internal                                                    #
    # ------------------------------------------------------------------ #
    def _on_detection_toggled(self, enabled: bool) -> None:
        self.sig_detection_enabled.emit(enabled)

    def _on_model_selected(self, index: int) -> None:
        _, model_file = self._MODEL_PRESETS[index]
        if model_file:
            self.sig_model_changed.emit(model_file)
        else:
            # "Custom…" selected → open file dialog automatically
            self._on_browse_model()

    def _on_browse_model(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select YOLOv8 Model",
            os.path.expanduser("~"),
            "PyTorch Model (*.pt *.pth);;All Files (*)",
        )
        if path:
            self._custom_model_path = path
            # Show short name in combo without duplicating entries
            display = f"Custom: {os.path.basename(path)}"
            # Check if a "Custom: ..." entry already exists
            found = False
            for i in range(self.cmb_model.count()):
                if self.cmb_model.itemText(i).startswith("Custom:"):
                    self.cmb_model.setItemText(i, display)
                    self.cmb_model.blockSignals(True)
                    self.cmb_model.setCurrentIndex(i)
                    self.cmb_model.blockSignals(False)
                    found = True
                    break
            if not found:
                self.cmb_model.blockSignals(True)
                self.cmb_model.addItem(display)
                self.cmb_model.setCurrentIndex(self.cmb_model.count() - 1)
                self.cmb_model.blockSignals(False)

            self.sig_model_changed.emit(path)

    def _on_conf_changed(self, value: int) -> None:
        self.lbl_conf_val.setText(f"{value} %")
        self.sig_confidence_changed.emit(value / 100.0)

    def _on_autotrack_toggled(self, enabled: bool) -> None:
        self.sig_auto_track_enabled.emit(enabled)
        # Reset lock-on if tracking disabled
        if not enabled and self.btn_lockon.isChecked():
            self.btn_lockon.blockSignals(True)
            self.btn_lockon.setChecked(False)
            self.btn_lockon.blockSignals(False)
            self._set_lockon_style(False)

    def _on_lockon_toggled(self, checked: bool) -> None:
        self._lock_on_active = checked
        self._set_lockon_style(checked)
        # Also enable auto-track when locking on
        if checked and not self.chk_autotrack.isChecked():
            self.chk_autotrack.setChecked(True)

    def _set_lockon_style(self, locked: bool) -> None:
        """Visually highlight the Lock-On button when active."""
        if locked:
            self.btn_lockon.setText("🔒  Locked On")
            self.btn_lockon.setProperty("locked", "true")
        else:
            self.btn_lockon.setText("🎯  Lock On")
            self.btn_lockon.setProperty("locked", "false")
        # Force Qt to re-evaluate the stylesheet
        self.btn_lockon.style().unpolish(self.btn_lockon)
        self.btn_lockon.style().polish(self.btn_lockon)

    # ------------------------------------------------------------------ #
    #  Public slot                                                         #
    # ------------------------------------------------------------------ #
    def update_stats(
        self,
        fps: float,
        n_detections: int,
        tracking_id: int,
    ) -> None:
        """
        Update the Stats group box labels.

        Parameters
        ----------
        fps          : current inference FPS
        n_detections : number of detections in last frame
        tracking_id  : ByteTrack ID currently being followed (-1 = none)
        """
        self.lbl_fps.setText(f"FPS:        {fps:6.1f}")
        self.lbl_det.setText(f"Detections: {n_detections:4d}")
        if tracking_id >= 0:
            self.lbl_track.setText(f"Tracking:   ID #{tracking_id}")
        else:
            self.lbl_track.setText("Tracking:   --")

    # ------------------------------------------------------------------ #
    #  Convenience getters                                                 #
    # ------------------------------------------------------------------ #
    @property
    def detection_enabled(self) -> bool:
        return self.chk_enable.isChecked()

    @property
    def auto_track_enabled(self) -> bool:
        return self.chk_autotrack.isChecked()

    @property
    def confidence(self) -> float:
        return self.sld_conf.value() / 100.0

    @property
    def track_gain(self) -> float:
        return self.spn_gain.value()

    @property
    def track_class(self) -> str:
        return self.cmb_track_class.currentText()

    @property
    def selected_model_path(self) -> str:
        idx = self.cmb_model.currentIndex()
        # Custom path
        if self._custom_model_path and idx >= len(self._MODEL_PRESETS):
            return self._custom_model_path
        if idx < len(self._MODEL_PRESETS):
            _, model_file = self._MODEL_PRESETS[idx]
            return model_file
        return self._custom_model_path

    @property
    def selected_classes(self) -> list[str]:
        """Return list of selected class names (lower-case). Empty = All."""
        selected = [
            item.text().lower()
            for item in self.lst_classes.selectedItems()
        ]
        if "all" in selected or not selected:
            return []   # empty list means no class filter
        return selected
