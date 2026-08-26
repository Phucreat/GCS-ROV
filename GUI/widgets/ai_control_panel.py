"""
ai_control_panel.py - High-Fidelity Responsive AI Vision & Voice Control Suite
=============================================================================
Bảng điều khiển AI thị giác máy tính & Trợ lý ảo giọng nói thế hệ mới:
  - Thiết kế Responsive Glassmorphism chuẩn Subsea C2 Cockpit.
  - Phân chia Tab thông minh: [🎯 Thị Giác & Tracking] và [🎙️ Trợ Lý Giọng Nói].
  - Hiển thị trực quan, không bị tràn màn hình hay cắt chữ.
  - Tương thích 100% toàn bộ API và tín hiệu (Signals/Slots) với main.py.
"""

from __future__ import annotations

import os
from typing import Optional, List

try:
    from PyQt6.QtCore import Qt, pyqtSignal, QSize
    from PyQt6.QtGui import QFont, QColor, QIcon, QPainter, QLinearGradient
    from PyQt6.QtWidgets import (
        QCheckBox,
        QComboBox,
        QDoubleSpinBox,
        QFileDialog,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QListWidget,
        QListWidgetItem,
        QPushButton,
        QSlider,
        QSizePolicy,
        QSpacerItem,
        QVBoxLayout,
        QWidget,
        QTabWidget,
        QScrollArea,
        QFrame,
    )
    _PYQT6 = True
except ImportError:
    from PyQt5.QtCore import Qt, pyqtSignal, QSize
    from PyQt5.QtGui import QFont, QColor, QIcon, QPainter, QLinearGradient
    from PyQt5.QtWidgets import (
        QCheckBox,
        QComboBox,
        QDoubleSpinBox,
        QFileDialog,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QListWidget,
        QListWidgetItem,
        QPushButton,
        QSlider,
        QSizePolicy,
        QSpacerItem,
        QVBoxLayout,
        QWidget,
        QTabWidget,
        QScrollArea,
        QFrame,
    )
    _PYQT6 = False


# ---------------------------------------------------------------------------
# High-End Glassmorphism Stylesheet
# ---------------------------------------------------------------------------
_MODERN_PANEL_STYLESHEET = """
/* ─── Global Background & Base ────────────────────────────────────────── */
QWidget {
    background-color: #070E18;
    color: #C2D6EC;
    font-family: "Segoe UI", "Rajdhani", sans-serif;
    font-size: 12px;
}

QScrollArea {
    border: none;
    background: transparent;
}

/* ─── Tab Widget Styling ──────────────────────────────────────────────── */
QTabWidget::pane {
    border: 1px solid rgba(0, 212, 255, 0.22);
    border-radius: 8px;
    background-color: #0A1424;
    top: -1px;
}

QTabBar::tab {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #101F33, stop:1 #0A1424);
    border: 1px solid #1E385B;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    padding: 8px 18px;
    color: #8BA8C8;
    font-weight: bold;
    font-size: 11px;
    letter-spacing: 0.5px;
    margin-right: 4px;
}

QTabBar::tab:selected {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #005580, stop:1 #0D223A);
    border: 1px solid #00D4FF;
    border-bottom: 2px solid #00F0FF;
    color: #FFFFFF;
}

QTabBar::tab:hover:!selected {
    background: #142842;
    color: #00E5FF;
}

/* ─── Glass Cards & Group Boxes ──────────────────────────────────────── */
QGroupBox {
    background-color: rgba(14, 26, 46, 0.85);
    border: 1px solid rgba(0, 168, 255, 0.25);
    border-radius: 8px;
    margin-top: 16px;
    padding: 14px 10px 10px 10px;
    font-weight: bold;
    font-size: 11px;
    color: #00E5FF;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 2px 8px;
    background: #070E18;
    border: 1px solid rgba(0, 212, 255, 0.35);
    border-radius: 4px;
    color: #00F0FF;
}

/* ─── CheckBox ────────────────────────────────────────────────────────── */
QCheckBox {
    spacing: 8px;
    color: #DDF0FF;
    font-weight: 600;
}

QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border: 1px solid #234770;
    border-radius: 4px;
    background: #0D1B2D;
}

QCheckBox::indicator:checked {
    background-color: #00D4FF;
    border: 1px solid #00F0FF;
}

QCheckBox::indicator:hover {
    border-color: #00F0FF;
    background-color: #142842;
}

/* ─── Controls: ComboBox, LineEdit, SpinBox ────────────────────────────── */
QComboBox, QLineEdit, QDoubleSpinBox {
    background-color: #0A1626;
    border: 1px solid #1E3D66;
    border-radius: 6px;
    padding: 5px 10px;
    color: #00E5FF;
    font-weight: bold;
    min-height: 28px;
}

QComboBox:hover, QLineEdit:hover, QDoubleSpinBox:hover {
    border-color: #00D4FF;
    background-color: #0E2038;
}

QComboBox:focus, QLineEdit:focus, QDoubleSpinBox:focus {
    border-color: #00F0FF;
    background-color: #102540;
}

QComboBox::drop-down {
    border: none;
    width: 24px;
}

QComboBox QAbstractItemView {
    background-color: #0A1626;
    border: 1px solid #00D4FF;
    border-radius: 6px;
    color: #00E5FF;
    selection-background-color: #005580;
    selection-color: #FFFFFF;
    padding: 4px;
}

/* ─── PushButtons ─────────────────────────────────────────────────────── */
QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #162E4D, stop:1 #0C1D33);
    border: 1px solid #244B7A;
    border-radius: 6px;
    color: #00E5FF;
    font-weight: bold;
    padding: 6px 14px;
    min-height: 28px;
}

QPushButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #0077B3, stop:1 #004D73);
    border-color: #00F0FF;
    color: #FFFFFF;
}

QPushButton:pressed {
    background: #00334D;
}

/* ─── Sliders ─────────────────────────────────────────────────────────── */
QSlider::groove:horizontal {
    height: 6px;
    background: #142842;
    border-radius: 3px;
}

QSlider::sub-page:horizontal {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0077B3, stop:1 #00F0FF);
    border-radius: 3px;
}

QSlider::handle:horizontal {
    background: #00F0FF;
    border: 2px solid #FFFFFF;
    width: 16px;
    height: 16px;
    margin: -5px 0;
    border-radius: 8px;
}

QSlider::handle:horizontal:hover {
    background: #FFFFFF;
    border-color: #00D4FF;
}

/* ─── Target Classes List ─────────────────────────────────────────────── */
QListWidget {
    background-color: #091424;
    border: 1px solid #1E3D66;
    border-radius: 6px;
    color: #C2D6EC;
    padding: 4px;
    min-height: 85px;
}

QListWidget::item {
    padding: 5px 8px;
    border-radius: 4px;
}

QListWidget::item:selected {
    background: rgba(0, 212, 255, 0.25);
    border: 1px solid #00D4FF;
    color: #FFFFFF;
    font-weight: bold;
}

QListWidget::item:hover:!selected {
    background: #10243D;
    color: #00E5FF;
}
"""


def _make_label(text: str, obj_name: str = "") -> QLabel:
    lbl = QLabel(text)
    if obj_name:
        lbl.setObjectName(obj_name)
    return lbl


class AIControlPanel(QWidget):
    """
    High-Fidelity Responsive AI Vision & Voice Control Suite.
    """

    # Public signals
    sig_detection_enabled       = pyqtSignal(bool)
    sig_model_changed           = pyqtSignal(str)
    sig_confidence_changed      = pyqtSignal(float)
    sig_auto_track_enabled      = pyqtSignal(bool)
    sig_track_class_changed     = pyqtSignal(str)
    sig_track_gain_changed      = pyqtSignal(float)
    sig_voice_command_submitted = pyqtSignal(str)
    sig_voice_agent_enabled     = pyqtSignal(bool)
    sig_wake_word_toggled       = pyqtSignal(bool)
    sig_language_changed        = pyqtSignal(str)
    sig_ptt_pressed             = pyqtSignal()
    sig_ptt_released            = pyqtSignal()

    _MODEL_PRESETS = [
        ("yolov8n  (fast)",   "yolov8n.pt"),
        ("yolov8s",           "yolov8s.pt"),
        ("Custom…",           ""),
    ]

    _TARGET_CLASSES = ["Diver", "Pipe", "Debris", "All"]

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._custom_model_path: str = ""
        self._lock_on_active: bool = False

        self.setWindowTitle("🤖 AI Vision & Voice Co-Pilot Control")
        self.setMinimumSize(420, 520)
        self.resize(480, 580)

        self._build_ui()
        self._connect_signals()
        self.setStyleSheet(_MODERN_PANEL_STYLESHEET)

    # ──────────────────────────────────────────────────────────
    # UI CONSTRUCTION WITH RESPONSIVE TABS
    # ──────────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(10, 10, 10, 10)
        main_lay.setSpacing(8)

        # Tabbed Layout
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)

        # ── TAB 1: VISION & TRACKING ──
        tab_vision = QWidget()
        lay_vision = QVBoxLayout(tab_vision)
        lay_vision.setContentsMargins(8, 8, 8, 8)
        lay_vision.setSpacing(10)

        scroll_vision = QScrollArea()
        scroll_vision.setWidgetResizable(True)
        scroll_content_v = QWidget()
        vbox_v = QVBoxLayout(scroll_content_v)
        vbox_v.setContentsMargins(4, 4, 4, 4)
        vbox_v.setSpacing(12)

        vbox_v.addWidget(self._build_detection_group())
        vbox_v.addWidget(self._build_tracking_group())
        vbox_v.addWidget(self._build_stats_group())
        vbox_v.addStretch()

        scroll_vision.setWidget(scroll_content_v)
        lay_vision.addWidget(scroll_vision)

        # ── TAB 2: VOICE CO-PILOT AGENT ──
        tab_voice = QWidget()
        lay_voice = QVBoxLayout(tab_voice)
        lay_voice.setContentsMargins(8, 8, 8, 8)
        lay_voice.setSpacing(10)

        scroll_voice = QScrollArea()
        scroll_voice.setWidgetResizable(True)
        scroll_content_a = QWidget()
        vbox_a = QVBoxLayout(scroll_content_a)
        vbox_a.setContentsMargins(4, 4, 4, 4)
        vbox_a.setSpacing(12)

        vbox_a.addWidget(self._build_voice_agent_group())
        vbox_a.addStretch()

        scroll_voice.setWidget(scroll_content_a)
        lay_voice.addWidget(scroll_voice)

        self.tabs.addTab(tab_vision, "🎯  THỊ GIÁC & TRACKING")
        self.tabs.addTab(tab_voice, "🎙️  TRỢ LÝ GIỌNG NÓI")

        main_lay.addWidget(self.tabs)

    # ── Group 1: Detection ────────────────────────────────────
    def _build_detection_group(self) -> QGroupBox:
        grp = QGroupBox("⬡  NHẬN DIỆN THỊ GIÁC YOLO")
        lay = QVBoxLayout(grp)
        lay.setSpacing(10)

        # Master Checkbox
        self.chk_enable = QCheckBox("Kích hoạt nhận diện AI (Enable Detection)")
        self.chk_enable.setChecked(False)
        lay.addWidget(self.chk_enable)

        # Model Selector Row
        model_row = QHBoxLayout()
        self.cmb_model = QComboBox()
        self._refresh_model_dropdown()
        self.btn_browse = QPushButton("📂 Duyệt Model...")
        self.btn_browse.setObjectName("btn_browse")
        model_row.addWidget(self.cmb_model, stretch=1)
        model_row.addWidget(self.btn_browse)
        lay.addLayout(model_row)

        # Confidence Slider with numeric badge
        conf_box = QVBoxLayout()
        conf_hdr = QHBoxLayout()
        lbl_conf_title = QLabel("Độ tin cậy nhận diện (Confidence):")
        self.lbl_conf_val = QLabel("50 %")
        self.lbl_conf_val.setStyleSheet("color: #00F0FF; font-weight: bold; font-size: 13px;")
        conf_hdr.addWidget(lbl_conf_title)
        conf_hdr.addStretch()
        conf_hdr.addWidget(self.lbl_conf_val)

        self.sld_conf = QSlider(Qt.Orientation.Horizontal)
        self.sld_conf.setRange(10, 95)
        self.sld_conf.setValue(50)
        self.sld_conf.valueChanged.connect(lambda v: self.lbl_conf_val.setText(f"{v} %"))

        conf_box.addLayout(conf_hdr)
        conf_box.addWidget(self.sld_conf)
        lay.addLayout(conf_box)

        # Target classes
        lay.addWidget(QLabel("Mục tiêu lọc nhận diện (Target Classes):"))
        self.lst_classes = QListWidget()
        self.lst_classes.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        for c in self._TARGET_CLASSES:
            item = QListWidgetItem(c)
            self.lst_classes.addItem(item)
            if c in ("Diver", "All"):
                item.setSelected(True)
        lay.addWidget(self.lst_classes)

        return grp

    # ── Group 2: Tracking ─────────────────────────────────────
    def _build_tracking_group(self) -> QGroupBox:
        grp = QGroupBox("◎  BÁM ĐUỔI TỰ ĐỘNG (AUTO-TRACKING)")
        lay = QVBoxLayout(grp)
        lay.setSpacing(10)

        self.chk_autotrack = QCheckBox("Kích hoạt bám đuổi (Enable Auto-Track)")
        self.chk_autotrack.setChecked(False)
        lay.addWidget(self.chk_autotrack)

        # Target class & gain row
        grid = QHBoxLayout()
        v_class = QVBoxLayout()
        v_class.addWidget(QLabel("Loại đối tượng bám:"))
        self.cmb_track_class = QComboBox()
        self.cmb_track_class.addItems(["Diver", "Pipe", "Debris"])
        v_class.addWidget(self.cmb_track_class)

        v_gain = QVBoxLayout()
        v_gain.addWidget(QLabel("Độ nhạy bám (Gain):"))
        self.spn_gain = QDoubleSpinBox()
        self.spn_gain.setRange(0.1, 5.0)
        self.spn_gain.setSingleStep(0.1)
        self.spn_gain.setValue(1.0)
        v_gain.addWidget(self.spn_gain)

        grid.addLayout(v_class, stretch=1)
        grid.addLayout(v_gain, stretch=1)
        lay.addLayout(grid)

        # Lock-On Button
        self.btn_lockon = QPushButton("🎯  KHÓA MỤC TIÊU (LOCK ON)")
        self.btn_lockon.setObjectName("btn_lockon")
        self.btn_lockon.setStyleSheet(
            "QPushButton { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #004D73,stop:1 #002233);"
            "border: 1px solid #00D4FF; color: #00F0FF; font-weight: bold; min-height: 32px; font-size: 12px; }"
            "QPushButton:hover { background: #00D4FF; color: #070E18; }"
        )
        lay.addWidget(self.btn_lockon)

        return grp

    # ── Group 3: Stats Group ──────────────────────────────────
    def _build_stats_group(self) -> QGroupBox:
        grp = QGroupBox("📊  THỐNG KÊ THỊ GIÁC THỜI GIAN THỰC")
        lay = QHBoxLayout(grp)
        lay.setSpacing(8)

        def _make_stat_card(title: str, val_widget: QLabel):
            f = QFrame()
            f.setStyleSheet("background: #081320; border: 1px solid #173250; border-radius: 6px; padding: 4px;")
            l = QVBoxLayout(f)
            l.setContentsMargins(4, 4, 4, 4)
            l.setSpacing(2)
            t = QLabel(title)
            t.setStyleSheet("color: #7B9BBF; font-size: 10px; font-weight: bold;")
            l.addWidget(t, alignment=Qt.AlignmentFlag.AlignCenter)
            l.addWidget(val_widget, alignment=Qt.AlignmentFlag.AlignCenter)
            return f

        self.lbl_fps = QLabel("0.0")
        self.lbl_fps.setStyleSheet("color: #00FF9D; font-weight: bold; font-size: 14px;")

        self.lbl_det = QLabel("0")
        self.lbl_det.setStyleSheet("color: #FFC107; font-weight: bold; font-size: 14px;")

        self.lbl_track = QLabel("--")
        self.lbl_track.setStyleSheet("color: #00D4FF; font-weight: bold; font-size: 13px;")

        lay.addWidget(_make_stat_card("TỐC ĐỘ FPS", self.lbl_fps), stretch=1)
        lay.addWidget(_make_stat_card("SỐ VẬT THỂ", self.lbl_det), stretch=1)
        lay.addWidget(_make_stat_card("ĐỐI TƯỢNG BÁM", self.lbl_track), stretch=1)

        return grp

    # ── Group 4: Voice Co-Pilot Agent ─────────────────────────
    def _build_voice_agent_group(self) -> QGroupBox:
        grp = QGroupBox("🎙️  TRỢ LÝ ẢO ĐIỀU KHIỂN GIỌNG NÓI (NEXOS AI)")
        lay = QVBoxLayout(grp)
        lay.setSpacing(12)

        # Master Checkbox
        self.chk_voice_agent = QCheckBox("Kích hoạt Trợ lý ảo AI (Offline 100%)")
        self.chk_voice_agent.setChecked(True)
        lay.addWidget(self.chk_voice_agent)

        # Language selection row
        lang_row = QHBoxLayout()
        lbl_l = QLabel("🌐 Ngôn ngữ phản hồi:")
        self.cmb_language = QComboBox()
        self.cmb_language.addItem("🇻🇳 Tiếng Việt (Vietnamese)", "vi")
        self.cmb_language.addItem("🇺🇸 English (US)", "en")
        self.cmb_language.addItem("🇯🇵 Japanese (日本語)", "ja")
        self.cmb_language.addItem("🇨🇳 Chinese (中文)", "zh")
        self.cmb_language.addItem("🇰🇷 Korean (한국어)", "ko")
        self.cmb_language.addItem("🇫🇷 French (Français)", "fr")
        self.cmb_language.addItem("🇩🇪 German (Deutsch)", "de")
        self.cmb_language.addItem("🇪🇸 Spanish (Español)", "es")
        self.cmb_language.addItem("🇷🇺 Russian (Русский)", "ru")
        self.cmb_language.setCurrentIndex(0)
        lang_row.addWidget(lbl_l)
        lang_row.addWidget(self.cmb_language, stretch=1)
        lay.addLayout(lang_row)

        self.chk_wake_word = QCheckBox("🗣️ Lắng nghe liên tục từ đánh thức 'Hey Nexos' / 'Nexos ơi'")
        self.chk_wake_word.setChecked(True)
        lay.addWidget(self.chk_wake_word)

        # Push To Talk Button
        self.btn_ptt = QPushButton("🎙️  NẮM GIỮ ĐỂ NÓI (PUSH-TO-TALK)")
        self.btn_ptt.setStyleSheet(
            "QPushButton { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #006699,stop:1 #00334D);"
            "border: 2px solid #00E5FF; border-radius: 8px; color: #FFFFFF; font-weight: bold; font-size: 13px; min-height: 42px; }"
            "QPushButton:pressed { background: #00E5FF; color: #070E18; border-color: #FFFFFF; }"
        )
        lay.addWidget(self.btn_ptt)

        # Status & Response Card
        card_resp = QFrame()
        card_resp.setStyleSheet("background: #081322; border: 1px solid #16304E; border-radius: 8px; padding: 8px;")
        lay_card = QVBoxLayout(card_resp)
        lay_card.setSpacing(6)

        self.lbl_mic_status = QLabel("Mic VAD: 🔴 Mute / Ready")
        self.lbl_mic_status.setStyleSheet("color: #00D4FF; font-weight: bold;")
        lay_card.addWidget(self.lbl_mic_status)

        self.lbl_agent_speech = QLabel("Agent: Ready for commands")
        self.lbl_agent_speech.setStyleSheet("color: #00FF9D; font-weight: 500; font-size: 12px;")
        self.lbl_agent_speech.setWordWrap(True)
        lay_card.addWidget(self.lbl_agent_speech)

        lay.addWidget(card_resp)

        # Text input row
        cmd_row = QHBoxLayout()
        self.txt_voice_cmd = QLineEdit()
        self.txt_voice_cmd.setPlaceholderText("Nhập câu lệnh bằng tay (vd: lặn xuống 5m, quay video, bật đèn)...")
        self.btn_send_voice_cmd = QPushButton("💬 Gửi")
        self.btn_send_voice_cmd.setStyleSheet("background: #00A8FF; color: white; font-weight: bold; min-width: 60px;")
        cmd_row.addWidget(self.txt_voice_cmd, stretch=1)
        cmd_row.addWidget(self.btn_send_voice_cmd)
        lay.addLayout(cmd_row)

        def _on_submit():
            txt = self.txt_voice_cmd.text().strip()
            if txt:
                self.sig_voice_command_submitted.emit(txt)
                self.txt_voice_cmd.clear()

        self.btn_send_voice_cmd.clicked.connect(_on_submit)
        self.txt_voice_cmd.returnPressed.connect(_on_submit)

        # Safety Human in the loop confirmation
        self.grp_safety = QGroupBox("⚠️  XÁC NHẬN AN TOÀN (SAFETY CONFIRMATION)")
        self.grp_safety.setStyleSheet("QGroupBox { border: 1px solid #FFC107; background: rgba(255,193,7,0.1); color: #FFC107; font-weight: bold; }")
        lay_safe = QVBoxLayout(self.grp_safety)
        self.lbl_safety_prompt = QLabel("No pending critical action.")
        self.lbl_safety_prompt.setStyleSheet("color: #FFF3CD; font-weight: bold;")
        self.lbl_safety_prompt.setWordWrap(True)
        lay_safe.addWidget(self.lbl_safety_prompt)

        btn_safe_row = QHBoxLayout()
        self.btn_confirm_action = QPushButton("✓  XÁC NHẬN")
        self.btn_confirm_action.setStyleSheet("background: #00C853; color: white; font-weight: bold;")
        self.btn_cancel_action = QPushButton("✗  HỦY")
        self.btn_cancel_action.setStyleSheet("background: #D50000; color: white; font-weight: bold;")
        btn_safe_row.addWidget(self.btn_confirm_action)
        btn_safe_row.addWidget(self.btn_cancel_action)
        lay_safe.addLayout(btn_safe_row)
        self.grp_safety.setVisible(False)
        lay.addWidget(self.grp_safety)

        return grp

    # ──────────────────────────────────────────────────────────
    # SIGNAL CONNECTIONS & HELPERS
    # ──────────────────────────────────────────────────────────
    def _connect_signals(self) -> None:
        self.chk_enable.toggled.connect(self.sig_detection_enabled.emit)
        self.cmb_model.currentIndexChanged.connect(self._on_model_changed)
        self.btn_browse.clicked.connect(self._on_browse_model)
        self.sld_conf.valueChanged.connect(lambda v: self.sig_confidence_changed.emit(v / 100.0))
        self.chk_autotrack.toggled.connect(self.sig_auto_track_enabled.emit)
        self.cmb_track_class.currentTextChanged.connect(self.sig_track_class_changed.emit)
        self.spn_gain.valueChanged.connect(self.sig_track_gain_changed.emit)
        self.btn_lockon.clicked.connect(self._on_lock_on_clicked)

        self.chk_voice_agent.toggled.connect(self.sig_voice_agent_enabled.emit)
        self.chk_wake_word.toggled.connect(self.sig_wake_word_toggled.emit)
        self.cmb_language.currentIndexChanged.connect(
            lambda: self.sig_language_changed.emit(self.cmb_language.currentData())
        )
        self.btn_ptt.pressed.connect(self.sig_ptt_pressed.emit)
        self.btn_ptt.released.connect(self.sig_ptt_released.emit)

    def _refresh_model_dropdown(self) -> None:
        self.cmb_model.clear()
        for label, _ in self._MODEL_PRESETS:
            self.cmb_model.addItem(label)
        try:
            for f in os.listdir("."):
                if f.endswith(".pt") and not any(f == p[1] for p in self._MODEL_PRESETS):
                    self.cmb_model.addItem(f"📁 {f}", f)
        except Exception:
            pass

    def _on_browse_model(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Chọn File Mô hình YOLO", "", "PyTorch Weights (*.pt *.engine *.onnx);;All Files (*)"
        )
        if path:
            self._custom_model_path = path
            fname = os.path.basename(path)
            self.cmb_model.addItem(f"📂 {fname}", path)
            self.cmb_model.setCurrentIndex(self.cmb_model.count() - 1)
            self.sig_model_changed.emit(path)

    def _on_model_changed(self, idx: int) -> None:
        if idx == 2 and not self._custom_model_path:
            self._on_browse_model()
            return
        self.sig_model_changed.emit(self.selected_model_path)

    def _on_lock_on_clicked(self) -> None:
        self._lock_on_active = not self._lock_on_active
        if self._lock_on_active:
            self.btn_lockon.setText("🔒  ĐANG KHÓA (LOCKED)")
            self.btn_lockon.setStyleSheet(
                "QPushButton { background: #00FF9D; color: #070E18; font-weight: bold; min-height: 32px; }"
            )
            self.chk_autotrack.setChecked(True)
        else:
            self.btn_lockon.setText("🎯  KHÓA MỤC TIÊU (LOCK ON)")
            self.btn_lockon.setStyleSheet(
                "QPushButton { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #004D73,stop:1 #002233);"
                "border: 1px solid #00D4FF; color: #00F0FF; font-weight: bold; min-height: 32px; }"
            )

    # ──────────────────────────────────────────────────────────
    # PUBLIC SLOTS & PROPERTIES
    # ──────────────────────────────────────────────────────────
    def update_stats(self, fps: float, n_detections: int, tracking_id: int) -> None:
        self.lbl_fps.setText(f"{fps:.1f}")
        self.lbl_det.setText(f"{n_detections}")
        self.lbl_track.setText(f"ID #{tracking_id}" if tracking_id >= 0 else "--")

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
        if self.cmb_model.itemData(idx):
            return self.cmb_model.itemData(idx)
        if idx < len(self._MODEL_PRESETS):
            return self._MODEL_PRESETS[idx][1]
        return self._custom_model_path or "yolov8n.pt"

    @property
    def selected_classes(self) -> list[str]:
        selected = [item.text().lower() for item in self.lst_classes.selectedItems()]
        if "all" in selected or not selected:
            return []
        return selected
