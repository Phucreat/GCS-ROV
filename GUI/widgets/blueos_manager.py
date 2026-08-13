"""
BlueOS Manager Widget for GCS ROV
Embeds BlueOS (Blue Robotics ROV OS) directly into the PyQt6 GCS Application
using Chromium-based QWebEngineView.
"""

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import pyqtSignal, QUrl, QTimer
import urllib.request

HAS_WEBENGINE = False
try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWebEngineCore import QWebEngineSettings
    HAS_WEBENGINE = True
except ImportError:
    HAS_WEBENGINE = False


class BlueOSManagerWindow(QtWidgets.QMainWindow):
    """
    Embedded BlueOS Control Suite Window for GCS ROV.
    Allows configuring BlueOS (ArduSub parameters, camera setup, extensions, terminal)
    directly inside the GCS software without opening external web browsers.
    """

    def __init__(self, default_ip: str = "192.168.2.2", parent=None):
        super().__init__(parent)
        self.default_ip = default_ip.strip()
        if not self.default_ip.startswith("http://") and not self.default_ip.startswith("https://"):
            self.base_url = f"http://{self.default_ip}"
        else:
            self.base_url = self.default_ip

        self.setWindowTitle("🌐 BlueOS Onboard ROV Manager (Embedded)")
        self.resize(1280, 800)
        self._init_ui()
        self._check_connection()

    def _init_ui(self):
        # Apply dark industrial theme matching GCS ROV
        self.setStyleSheet("""
            QMainWindow {
                background-color: #0A1423;
                color: #E2F1FF;
            }
            QToolBar {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #142338, stop:1 #0C1827);
                border-bottom: 1px solid #1D3554;
                padding: 6px;
                spacing: 8px;
            }
            QLabel {
                color: #00D4FF;
                font-weight: bold;
                font-size: 12px;
            }
            QLineEdit {
                background-color: #070E17;
                color: #00FF9D;
                border: 1px solid #1D3554;
                border-radius: 4px;
                padding: 4px 8px;
                font-family: 'Consolas', monospace;
                font-size: 12px;
            }
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1A314D, stop:1 #0F2035);
                color: #E2F1FF;
                border: 1px solid #2B4C7E;
                border-radius: 4px;
                padding: 5px 12px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                background: #00A8FF;
                color: #FFFFFF;
                border-color: #00F0FF;
            }
            QComboBox {
                background-color: #070E17;
                color: #00D4FF;
                border: 1px solid #1D3554;
                border-radius: 4px;
                padding: 4px 8px;
                font-weight: bold;
            }
        """)

        central_widget = QtWidgets.QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QtWidgets.QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Toolbar Controls ──
        toolbar = QtWidgets.QToolBar("BlueOS Controls", self)
        toolbar.setMovable(False)
        self.addToolBar(QtCore.Qt.ToolBarArea.TopToolBarArea, toolbar)

        # Nav buttons
        self.btn_back = QtWidgets.QPushButton("◀ Back", self)
        self.btn_forward = QtWidgets.QPushButton("Forward ▶", self)
        self.btn_reload = QtWidgets.QPushButton("🔄 Refresh", self)
        self.btn_home = QtWidgets.QPushButton("🏠 Home", self)

        # URL address bar
        lbl_url = QtWidgets.QLabel("BlueOS IP:", self)
        self.txt_url = QtWidgets.QLineEdit(self.base_url, self)
        self.txt_url.setMinimumWidth(220)

        self.btn_go = QtWidgets.QPushButton("Go ➜", self)

        # Status badge
        self.lbl_status = QtWidgets.QLabel("🔴 Offline", self)
        self.lbl_status.setStyleSheet("color: #FF5252; font-weight: bold; padding: 0 8px;")

        # Quick Links Dropdown
        lbl_quick = QtWidgets.QLabel("Quick Menu:", self)
        self.cmb_quick = QtWidgets.QComboBox(self)
        self.cmb_quick.addItems([
            "📌 Dashboard Root",
            "🎥 Camera Manager",
            "⚙️ ArduSub Parameters",
            "📡 Network Setup",
            "📦 Extension Store",
            "💻 System Terminal",
            "📂 Log Downloader"
        ])

        # Add to toolbar
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
        toolbar.addSeparator()
        toolbar.addWidget(self.lbl_status)

        # ── Web View Container ──
        if HAS_WEBENGINE:
            self.web_view = QWebEngineView(self)
            # Enable plugins, local storage, javascript
            settings = self.web_view.settings()
            settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, True)

            self.web_view.load(QUrl(self.base_url))
            main_layout.addWidget(self.web_view)

            # Signal connections
            self.btn_back.clicked.connect(self.web_view.back)
            self.btn_forward.clicked.connect(self.web_view.forward)
            self.btn_reload.clicked.connect(self.web_view.reload)
            self.btn_home.clicked.connect(lambda: self.load_url(self.base_url))
            self.btn_go.clicked.connect(self._on_go_clicked)
            self.txt_url.returnPressed.connect(self._on_go_clicked)
            self.cmb_quick.currentIndexChanged.connect(self._on_quick_menu_changed)
            self.web_view.urlChanged.connect(self._on_url_changed)
        else:
            # Fallback if WebEngine missing
            lbl_fallback = QtWidgets.QLabel(
                "❌ PyQt6-WebEngine không khả dụng.\nVui lòng cài đặt: pip install PyQt6-WebEngine", self)
            lbl_fallback.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            lbl_fallback.setStyleSheet("color: #FF5252; font-size: 16px; font-weight: bold;")
            main_layout.addWidget(lbl_fallback)

        # Connection poll timer (every 5s)
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self._check_connection)
        self.poll_timer.start(5000)

    def load_url(self, url_str: str):
        if not url_str.startswith("http://") and not url_str.startswith("https://"):
            url_str = f"http://{url_str}"
        self.txt_url.setText(url_str)
        if HAS_WEBENGINE:
            self.web_view.load(QUrl(url_str))

    def _on_go_clicked(self):
        url_text = self.txt_url.text().strip()
        self.load_url(url_text)

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

    def _check_connection(self):
        """Asynchronously check if BlueOS web server responds on HTTP."""
        def run_ping():
            try:
                url = self.txt_url.text().split("#")[0].rstrip("/")
                req = urllib.request.Request(url, headers={"User-Agent": "GCS-ROV-Client"})
                with urllib.request.urlopen(req, timeout=2.0) as resp:
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
        if online:
            self.lbl_status.setText("🟢 BlueOS Connected")
            self.lbl_status.setStyleSheet("color: #00FF9D; font-weight: bold; padding: 0 8px;")
        else:
            self.lbl_status.setText("🔴 BlueOS Offline")
            self.lbl_status.setStyleSheet("color: #FF5252; font-weight: bold; padding: 0 8px;")
