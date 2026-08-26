"""
blueos_manager.py - High-Fidelity Responsive BlueOS Onboard ROV Manager
======================================================================
Trình quản trị hệ điều hành robot lặn BlueOS nhúng trực tiếp:
  - Thiết kế Dark Cyber-Subsea Glassmorphism.
  - Tự động hiển thị Standby Dashboard chuyên nghiệp khi BlueOS Offline (không bị màn hình trắng).
  - Tích hợp công cụ chẩn đoán kết nối Tether, IP tĩnh, hướng dẫn từng bước.
  - Thanh công cụ điều hướng Responsive, chống tràn chữ và co giãn mượt mà.
"""

from __future__ import annotations

import os
import urllib.request
import webbrowser
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import pyqtSignal, QUrl, QTimer, Qt

HAS_WEBENGINE = False
try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWebEngineCore import QWebEngineSettings
    HAS_WEBENGINE = True
except ImportError:
    HAS_WEBENGINE = False


_BLUEOS_STYLESHEET = """
QMainWindow, QWidget#central_widget {
    background-color: #070E18;
    color: #C2D6EC;
    font-family: "Segoe UI", "Rajdhani", sans-serif;
}

QToolBar {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #101F33, stop:1 #0A1424);
    border-bottom: 1px solid rgba(0, 212, 255, 0.25);
    padding: 6px 10px;
    spacing: 8px;
}

QLabel {
    color: #00D4FF;
    font-weight: bold;
    font-size: 12px;
}

QLineEdit {
    background-color: #0A1626;
    color: #00FF9D;
    border: 1px solid #1E3D66;
    border-radius: 6px;
    padding: 5px 10px;
    font-family: 'Consolas', monospace;
    font-size: 12px;
    font-weight: bold;
    min-height: 26px;
}

QLineEdit:focus {
    border-color: #00F0FF;
    background-color: #0E223B;
}

QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #162E4D, stop:1 #0C1D33);
    border: 1px solid #244B7A;
    border-radius: 6px;
    color: #00E5FF;
    font-weight: bold;
    padding: 5px 12px;
    min-height: 26px;
}

QPushButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #0077B3, stop:1 #004D73);
    border-color: #00F0FF;
    color: #FFFFFF;
}

QPushButton:pressed {
    background: #00334D;
}

QComboBox {
    background-color: #0A1626;
    color: #00E5FF;
    border: 1px solid #1E3D66;
    border-radius: 6px;
    padding: 4px 10px;
    font-weight: bold;
    min-height: 26px;
}

QComboBox:hover {
    border-color: #00D4FF;
}

QComboBox QAbstractItemView {
    background-color: #0A1626;
    border: 1px solid #00D4FF;
    color: #00E5FF;
    selection-background-color: #005580;
    selection-color: #FFFFFF;
}
"""


class BlueOSManagerWindow(QtWidgets.QMainWindow):
    """
    Embedded BlueOS Control Suite Window for GCS ROV.
    """

    def __init__(self, default_ip: str = "192.168.2.2", parent=None):
        super().__init__(parent)
        self.default_ip = default_ip.strip()
        if not self.default_ip.startswith("http://") and not self.default_ip.startswith("https://"):
            self.base_url = f"http://{self.default_ip}"
        else:
            self.base_url = self.default_ip

        self.setWindowTitle("🌐 BlueOS Onboard ROV Manager (Embedded Suite)")
        self.resize(1280, 800)
        self.setMinimumSize(900, 600)

        self._is_online = False
        self._init_ui()
        self._check_connection()

    def _init_ui(self):
        self.setStyleSheet(_BLUEOS_STYLESHEET)

        central_widget = QtWidgets.QWidget(self)
        central_widget.setObjectName("central_widget")
        self.setCentralWidget(central_widget)
        main_layout = QtWidgets.QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Toolbar Controls ──
        toolbar = QtWidgets.QToolBar("BlueOS Controls", self)
        toolbar.setMovable(False)
        self.addToolBar(QtCore.Qt.ToolBarArea.TopToolBarArea, toolbar)

        self.btn_back = QtWidgets.QPushButton("◀", self)
        self.btn_back.setToolTip("Quay lại (Back)")
        self.btn_forward = QtWidgets.QPushButton("▶", self)
        self.btn_forward.setToolTip("Tiếp theo (Forward)")
        self.btn_reload = QtWidgets.QPushButton("🔄 Tải lại", self)
        self.btn_home = QtWidgets.QPushButton("🏠 Trang chủ", self)

        lbl_url = QtWidgets.QLabel("  BlueOS IP: ", self)
        self.txt_url = QtWidgets.QLineEdit(self.base_url, self)
        self.txt_url.setMinimumWidth(220)
        self.btn_go = QtWidgets.QPushButton("Truy Cập ➜", self)

        lbl_quick = QtWidgets.QLabel("  Menu Nhanh: ", self)
        self.cmb_quick = QtWidgets.QComboBox(self)
        self.cmb_quick.addItems([
            "📌 Bảng điều khiển (Dashboard)",
            "🎥 Quản lý Camera (Camera Setup)",
            "⚙️ Tham số ArduSub (Vehicle Setup)",
            "📡 Cấu hình Mạng (Network Setup)",
            "📦 Kho Tiện ích (Extension Store)",
            "💻 Terminal Dòng Lệnh",
            "📂 Nhật ký Lặn (Log Browser)"
        ])

        self.lbl_status = QtWidgets.QLabel(" 🔴 BlueOS Offline ", self)
        self.lbl_status.setStyleSheet(
            "background: rgba(255, 68, 68, 0.15); border: 1px solid #FF4444; "
            "border-radius: 12px; color: #FF6B6B; font-weight: bold; padding: 3px 10px;"
        )

        toolbar.addWidget(self.btn_back)
        toolbar.addWidget(self.btn_forward)
        toolbar.addWidget(self.btn_reload)
        toolbar.addWidget(self.btn_home)
        toolbar.addSeparator()
        toolbar.addWidget(lbl_url)
        toolbar.addWidget(self.txt_url)
        toolbar.addWidget(self.btn_go)
        toolbar.addSeparator()
        toolbar.addWidget(lbl_quick)
        toolbar.addWidget(self.cmb_quick)
        toolbar.addSeparator()
        toolbar.addWidget(self.lbl_status)

        # ── Stacked Container (Index 0: Standby Screen, Index 1: Web Engine) ──
        self.stacked = QtWidgets.QStackedWidget(self)
        main_layout.addWidget(self.stacked)

        # Page 0: Sleek Standby Screen
        self.page_standby = self._build_standby_page()
        self.stacked.addWidget(self.page_standby)

        # Page 1: WebEngine View
        if HAS_WEBENGINE:
            self.web_view = QWebEngineView(self)
            self.web_view.page().setBackgroundColor(QtGui.QColor("#070E18"))

            settings = self.web_view.settings()
            settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, True)

            self.stacked.addWidget(self.web_view)

            # Signals
            self.btn_back.clicked.connect(self.web_view.back)
            self.btn_forward.clicked.connect(self.web_view.forward)
            self.btn_reload.clicked.connect(self._on_reload_clicked)
            self.btn_home.clicked.connect(lambda: self.load_url(self.base_url))
            self.btn_go.clicked.connect(self._on_go_clicked)
            self.txt_url.returnPressed.connect(self._on_go_clicked)
            self.cmb_quick.currentIndexChanged.connect(self._on_quick_menu_changed)
            self.web_view.urlChanged.connect(self._on_url_changed)
        else:
            lbl_fallback = QtWidgets.QLabel(
                "❌ PyQt6-WebEngine không khả dụng.\nVui lòng cài đặt: pip install PyQt6-WebEngine", self
            )
            lbl_fallback.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            lbl_fallback.setStyleSheet("color: #FF5252; font-size: 16px; font-weight: bold;")
            self.stacked.addWidget(lbl_fallback)

        # Connection poll timer (every 4s)
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self._check_connection)
        self.poll_timer.start(4000)

    # ──────────────────────────────────────────────────────────
    # STANDBY SCREEN (REPLACES BLANK WHITE VOID)
    # ──────────────────────────────────────────────────────────
    def _build_standby_page(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        page.setStyleSheet("background-color: #070E18;")
        lay = QtWidgets.QVBoxLayout(page)
        lay.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(20)

        # Glass Panel Card
        card = QtWidgets.QFrame()
        card.setMaximumWidth(700)
        card.setStyleSheet(
            "background: rgba(14, 26, 46, 0.95); border: 1px solid rgba(0, 212, 255, 0.3);"
            "border-radius: 12px; padding: 24px;"
        )
        card_lay = QtWidgets.QVBoxLayout(card)
        card_lay.setSpacing(16)
        card_lay.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        # Subsea Icon & Title
        lbl_icon = QtWidgets.QLabel("🌐  SUBSEA ROV ONBOARD MANAGER")
        lbl_icon.setStyleSheet("color: #00F0FF; font-size: 20px; font-weight: bold; letter-spacing: 1px;")
        card_lay.addWidget(lbl_icon, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)

        self.lbl_standby_status = QtWidgets.QLabel("🔴 ĐANG CHỜ KẾT NỐI TỚI BLUEOS...")
        self.lbl_standby_status.setStyleSheet("color: #FF6B6B; font-size: 14px; font-weight: bold;")
        card_lay.addWidget(self.lbl_standby_status, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)

        lbl_desc = QtWidgets.QLabel(
            "Hệ thống đang dò tìm máy chủ BlueOS tại địa chỉ: "
            f"<b style='color:#00FF9D;'>{self.base_url}</b><br>"
            "Khi cáp Tether được cắm và ROV khởi động, giao diện BlueOS sẽ tự động hiển thị tại đây."
        )
        lbl_desc.setTextFormat(QtCore.Qt.TextFormat.RichText)
        lbl_desc.setStyleSheet("color: #94A9C4; font-size: 12px; line-height: 140%;")
        lbl_desc.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        card_lay.addWidget(lbl_desc)

        # Action Buttons Row
        btn_box = QtWidgets.QHBoxLayout()
        btn_box.setSpacing(12)

        btn_retry = QtWidgets.QPushButton("⚡ Thử Kết Nối Lại (Ping)")
        btn_retry.setMinimumHeight(36)
        btn_retry.setStyleSheet(
            "background: #0077B3; color: #FFFFFF; font-weight: bold; border-radius: 6px; padding: 0 16px;"
        )
        btn_retry.clicked.connect(self._check_connection)

        btn_ext = QtWidgets.QPushButton("🌐 Mở Bằng Trình Duyệt Ngoài")
        btn_ext.setMinimumHeight(36)
        btn_ext.setStyleSheet(
            "background: #142842; color: #00E5FF; border: 1px solid #00D4FF; font-weight: bold; border-radius: 6px; padding: 0 16px;"
        )
        btn_ext.clicked.connect(lambda: webbrowser.open(self.base_url))

        btn_box.addWidget(btn_retry)
        btn_box.addWidget(btn_ext)
        card_lay.addLayout(btn_box)

        # Quick Checklist
        steps_box = QtWidgets.QFrame()
        steps_box.setStyleSheet("background: #091322; border: 1px solid #173250; border-radius: 8px; padding: 12px;")
        steps_lay = QtWidgets.QVBoxLayout(steps_box)
        steps_lay.setSpacing(8)

        lbl_steps_hdr = QtWidgets.QLabel("📋 HƯỚNG DẪN KIỂM TRA NHANH:")
        lbl_steps_hdr.setStyleSheet("color: #FFC107; font-weight: bold; font-size: 11px;")
        steps_lay.addWidget(lbl_steps_hdr)

        step1 = QtWidgets.QLabel("1. Cắm cáp Tether Ethernet từ ROV vào cổng LAN máy tính.")
        step1.setStyleSheet("color: #C2D6EC; font-size: 11px;")
        step2 = QtWidgets.QLabel("2. Cài đặt IP tĩnh card mạng máy tính: <b>192.168.2.1</b> (Subnet: 255.255.255.0).")
        step2.setStyleSheet("color: #C2D6EC; font-size: 11px;")
        step3 = QtWidgets.QLabel("3. Kiểm tra đèn LED bo mạch Raspberry Pi/Companion trên ROV đã sáng xanh.")
        step3.setStyleSheet("color: #C2D6EC; font-size: 11px;")

        steps_lay.addWidget(step1)
        steps_lay.addWidget(step2)
        steps_lay.addWidget(step3)

        card_lay.addWidget(steps_box)

        lay.addWidget(card, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)
        return page

    # ──────────────────────────────────────────────────────────
    # NAVIGATION & URL LOADING
    # ──────────────────────────────────────────────────────────
    def load_url(self, url_str: str):
        if not url_str.startswith("http://") and not url_str.startswith("https://"):
            url_str = f"http://{url_str}"
        self.txt_url.setText(url_str)
        if HAS_WEBENGINE:
            self.web_view.load(QUrl(url_str))

    def _on_go_clicked(self):
        url_text = self.txt_url.text().strip()
        self.load_url(url_text)
        self._check_connection()

    def _on_reload_clicked(self):
        if HAS_WEBENGINE:
            self.web_view.reload()
        self._check_connection()

    def _on_url_changed(self, qurl: QUrl):
        self.txt_url.setText(qurl.toString())

    def _on_quick_menu_changed(self, index: int):
        base = self.txt_url.text().split("#")[0].rstrip("/")
        routes = [
            "",
            "/#/camera-manager",
            "/#/vehicle-setup",
            "/#/network",
            "/#/extensions",
            "/#/terminal",
            "/#/log-browser"
        ]
        if index < len(routes):
            target = base + routes[index]
            self.load_url(target)

    # ──────────────────────────────────────────────────────────
    # ASYNC HEALTH CHECK & STACK SWITCHING
    # ──────────────────────────────────────────────────────────
    def _check_connection(self):
        def run_ping():
            try:
                url = self.txt_url.text().split("#")[0].rstrip("/")
                req = urllib.request.Request(url, headers={"User-Agent": "GCS-ROV-Client"})
                with urllib.request.urlopen(req, timeout=1.5) as resp:
                    if resp.status in (200, 301, 302):
                        return True
            except Exception:
                return False
            return False

        import threading
        def worker():
            online = run_ping()
            QtCore.QMetaObject.invokeMethod(
                self, "_update_status_ui", QtCore.Qt.ConnectionType.QueuedConnection, QtCore.Q_ARG(bool, online)
            )
        threading.Thread(target=worker, daemon=True).start()

    @QtCore.pyqtSlot(bool)
    def _update_status_ui(self, online: bool):
        self._is_online = online
        if online:
            self.lbl_status.setText(" 🟢 BlueOS Connected ")
            self.lbl_status.setStyleSheet(
                "background: rgba(0, 255, 157, 0.15); border: 1px solid #00FF9D; "
                "border-radius: 12px; color: #00FF9D; font-weight: bold; padding: 3px 10px;"
            )
            if HAS_WEBENGINE and self.stacked.currentIndex() != 1:
                self.stacked.setCurrentIndex(1)
        else:
            self.lbl_status.setText(" 🔴 BlueOS Offline ")
            self.lbl_status.setStyleSheet(
                "background: rgba(255, 68, 68, 0.15); border: 1px solid #FF4444; "
                "border-radius: 12px; color: #FF6B6B; font-weight: bold; padding: 3px 10px;"
            )
            if self.stacked.currentIndex() != 0:
                self.stacked.setCurrentIndex(0)
