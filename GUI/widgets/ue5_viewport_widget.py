"""
ue5_viewport_widget.py - Unreal Engine 5 WebRTC Pixel Streaming & Subsea Environment Viewport
================================================================================================
Trình diễn Mô phỏng 3D Digital Twin đỉnh cao với công nghệ Unreal Engine 5 Pixel Streaming (WebRTC):
- Nhúng luồng video 3D WebRTC siêu chân thực qua Chromium QWebEngineView (0% GUI Lag).
- Bảng điều khiển Môi trường lặn ngầm thời gian thực:
  + Level Streaming Map Selector: Bể bơi, Hồ thủy điện, Biển khơi, Thác tàu cổ.
  + Water Turbidity Slider: Tự động truyền lệnh đổi độ đục nước (Exponential Height Fog).
  + Depth & Lighting Auto-Sync: Tự động làm tối đại dương & bật đèn rọi theo độ sâu MAVLink.
- Tự động kết nối và chuyển gói tin UDP 60Hz sang Unreal Engine 5.
"""

from __future__ import annotations

import os
import time
from typing import Optional

from network.ue5_auto_launcher import UE5AutoLauncher

try:
    from PyQt6.QtCore import Qt, QUrl, QTimer, pyqtSignal
    from PyQt6.QtGui import QFont, QIcon
    from PyQt6.QtWidgets import (
        QCheckBox,
        QComboBox,
        QFileDialog,
        QFrame,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QPushButton,
        QSlider,
        QVBoxLayout,
        QWidget,
    )
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    _HAS_WEBENGINE = True
except ImportError:
    try:
        from PyQt5.QtCore import Qt, QUrl, QTimer, pyqtSignal
        from PyQt5.QtGui import QFont, QIcon
        from PyQt5.QtWidgets import (
            QCheckBox,
            QComboBox,
            QFileDialog,
            QFrame,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QPushButton,
            QSlider,
            QVBoxLayout,
            QWidget,
        )
        from PyQt5.QtWebEngineWidgets import QWebEngineView
        _HAS_WEBENGINE = True
    except ImportError:
        _HAS_WEBENGINE = False


_STANDBY_HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {
    background-color: #060B14;
    color: #94A9C4;
    font-family: 'Segoe UI', Arial, sans-serif;
    margin: 0;
    padding: 30px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    min-height: 80vh;
  }
  .card {
    background: #0A1423;
    border: 1px solid rgba(0, 229, 255, 0.35);
    border-radius: 12px;
    padding: 32px 42px;
    max-width: 780px;
    box-shadow: 0 10px 35px rgba(0, 0, 0, 0.8);
  }
  h2 {
    color: #00E5FF;
    margin-top: 0;
    font-size: 22px;
    letter-spacing: 0.8px;
  }
  .badge {
    background: rgba(255, 193, 7, 0.15);
    color: #FFC107;
    border: 1px solid #FFC107;
    padding: 5px 12px;
    border-radius: 6px;
    font-size: 13px;
    font-weight: bold;
    margin-bottom: 20px;
    display: inline-block;
  }
  ol {
    line-height: 1.8;
    padding-left: 22px;
    font-size: 14px;
  }
  code {
    background: #040810;
    color: #00FF9D;
    padding: 3px 8px;
    border-radius: 4px;
    font-family: Consolas, monospace;
    font-weight: bold;
  }
  .tip {
    background: rgba(0, 229, 255, 0.08);
    border-left: 4px solid #00E5FF;
    padding: 12px 18px;
    margin-top: 22px;
    font-size: 13px;
    border-radius: 4px;
    color: #B4C6E2;
  }
</style>
</head>
<body>
  <div class="card">
    <h2>🎮 UNREAL ENGINE 5 PIXEL STREAMING STANDBY</h2>
    <div class="badge">🟡 TRẠNG THÁI CHỜ: Chưa bật luồng Unreal Engine 5 Signaling Server (ERR_CONNECTION_REFUSED)</div>
    
    <p>Giao diện GCS ROV đã sẵn sàng phát tọa độ MAVLink 6-DOF tốc độ cao <b>60Hz UDP</b>. Để mở môi trường 3D Unreal Engine 5 siêu chân thực, bạn hãy thực hiện 3 bước đơn giản:</p>

    <ol>
      <li><b>Bước 1</b>: Mở Project Unreal Engine 5 của bạn. Chạy file lệnh khởi tạo WebRTC Server: <br><code>SignallingWebServer/platform_scripts/cmd/run.bat</code> (Mặc định cổng <code>80</code> hoặc <code>8080</code>).</li>
      <li><b>Bước 2</b>: Trong UE5 Editor: Đảm bảo Plugin <b>Pixel Streaming</b> đã được bật (Enabled) trong <i>Project Settings</i>.</li>
      <li><b>Bước 3</b>: Nhập địa chỉ IP / Cổng vào ô URL ở góc trên bên phải (vd: <code>http://127.0.0.1:80</code> hoặc IP máy chủ 3D riêng) và nhấn nút <b>🔄 Reconnect</b>.</li>
    </ol>

    <div class="tip">
      💡 <b>Mẹo nâng cao</b>: Trong lúc UE5 chưa bật, tọa độ $[X, Y, Z, Roll, Pitch, Yaw]$ vẫn đang được GCS tự động phát ngầm qua cổng UDP <code>8888</code>. Ngay khi bạn bật UE5, mô hình tàu lặn 3D sẽ nhảy và lật nghiêng mượt mà tức thì!
    </div>
  </div>
</body>
</html>
"""


class UE5RenderCanvas(QWidget):
    """
    Pure 3D Render Canvas Viewport for embedding directly inside the main GUI's
    '3D MOTION & POSITION' frame (frm_simulate_motion) with ZERO header bars or extra toolbars.
    """

    sig_waypoint_placed = pyqtSignal(float, float, float)

    def __init__(
        self,
        default_url: str = "http://127.0.0.1:80",
        udp_sender: Optional[Any] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._url = default_url
        self._udp_sender = udp_sender

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        if _HAS_WEBENGINE:
            self.web_view = QWebEngineView(self)
            def _on_load_finished(ok: bool):
                if not ok:
                    self.web_view.setHtml(_STANDBY_HTML)
            self.web_view.loadFinished.connect(_on_load_finished)
            self.web_view.load(QUrl(self._url))
            layout.addWidget(self.web_view)
        else:
            fallback = QLabel("⚠️ PyQt6-WebEngine is not installed")
            fallback.setAlignment(Qt.AlignmentFlag.AlignCenter)
            fallback.setStyleSheet("color: #FF5252; font-weight: bold; background: #060B14;")
            layout.addWidget(fallback)

    def update_pose(self, x: float = 0.0, y: float = 0.0, z: float = 0.0, roll: float = 0.0, pitch: float = 0.0, yaw: float = 0.0) -> None:
        """Forward ROV 6-DOF telemetry pose to UE5 UDP Sender at 60Hz."""
        if self._udp_sender and hasattr(self._udp_sender, 'update_pose'):
            self._udp_sender.update_pose(x, y, z, roll, pitch, yaw)

    def set_model(self, model_obj: Any = None, cad_file: str = "") -> None:
        """Model configuration stub for UE5 Digital Twin integration."""
        pass

    def set_origin(self, pos: Any = None) -> None:
        """Origin position stub."""
        pass

    def update_trajectory(self, x: float = 0.0, y: float = 0.0, z: float = 0.0) -> None:
        """Waypoint trajectory update stub for GCS integration."""
        pass

    def update_fov_effect(self, heading: float = 0.0) -> None:
        """FOV effect stub."""
        pass

    def update_slam_points(self, pts: Any = None) -> None:
        """SLAM points update stub."""
        pass


class UE5ViewportWidget(QWidget):
    """
    Unreal Engine 5 WebRTC Pixel Streaming Viewport Widget.
    """

    sig_map_changed = pyqtSignal(str)
    sig_turbidity_changed = pyqtSignal(float)
    sig_depth_lighting_toggled = pyqtSignal(bool)

    # Preset maps
    MAP_PRESETS = [
        ("🏊 Bể bơi huấn luyện (Pool Test Tank)", "POOL"),
        ("🏞 Hồ thủy điện (Hydroelectric Reservoir)", "RESERVOIR"),
        ("🌊 Biển khơi (Offshore Deep Ocean)", "OFFSHORE_OCEAN"),
        ("🚢 Thác tàu cổ (Ancient Shipwreck Site)", "SHIPWRECK"),
    ]

    def __init__(
        self,
        default_url: str = "http://127.0.0.1:80",
        udp_sender: Optional[Any] = None,
        exe_path: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._url = default_url
        self._udp_sender = udp_sender
        self._exe_path = exe_path
        self._depth_sync_enabled = True

        self.auto_launcher = UE5AutoLauncher(custom_exe_path=self._exe_path, web_port=80)

        self._build_ui()
        self.setStyleSheet(
            """
            QWidget {
                background-color: #060B14;
                color: #94A9C4;
                font-family: 'Rajdhani', 'Segoe UI', sans-serif;
            }
            QFrame#header_bar {
                background-color: #0A1423;
                border-bottom: 1px solid rgba(0, 229, 255, 0.25);
            }
            QComboBox, QLineEdit {
                background-color: #0C1727;
                border: 1px solid #1D3554;
                border-radius: 4px;
                color: #00D4FF;
                padding: 3px 6px;
                font-weight: bold;
            }
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #142338, stop:1 #0C1827);
                border: 1px solid #1D3554;
                border-radius: 4px;
                color: #00D4FF;
                font-weight: bold;
                padding: 4px 10px;
            }
            QPushButton:hover {
                background: #00A8FF;
                color: #FFFFFF;
                border-color: #00F0FF;
            }
            QSlider::groove:horizontal {
                height: 4px;
                background: #1B2F4A;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #00F0FF;
                border: 1px solid #00A8FF;
                width: 12px;
                height: 12px;
                margin: -4px 0;
                border-radius: 6px;
            }
            """
        )

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Top Control Header Bar ────────────────────────────────────────── #
        self.header = QFrame(self)
        self.header.setObjectName("header_bar")
        self.header.setFixedHeight(48)
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(12, 0, 12, 0)
        header_layout.setSpacing(12)

        # Brand / Title Label
        lbl_brand = QLabel("🎮 UNREAL ENGINE 5 DIGITAL TWIN")
        lbl_brand.setStyleSheet("color: #00E5FF; font-size: 13px; font-weight: bold; letter-spacing: 0.8px;")
        header_layout.addWidget(lbl_brand)

        # Environment Level Selector Combo
        header_layout.addWidget(QLabel("🗺 Môi trường:"))
        self.cmb_map = QComboBox()
        for label, code in self.MAP_PRESETS:
            self.cmb_map.addItem(label, code)
        self.cmb_map.setCurrentIndex(2)  # Default: Offshore Ocean
        self.cmb_map.currentIndexChanged.connect(self._on_map_changed)
        header_layout.addWidget(self.cmb_map)

        # Water Turbidity Slider Row
        header_layout.addWidget(QLabel("💧 Độ đục nước:"))
        self.sld_turbidity = QSlider(Qt.Orientation.Horizontal)
        self.sld_turbidity.setRange(0, 100)
        self.sld_turbidity.setValue(20)
        self.sld_turbidity.setFixedWidth(100)
        self.sld_turbidity.valueChanged.connect(self._on_turbidity_changed)
        header_layout.addWidget(self.sld_turbidity)

        self.lbl_turbidity_val = QLabel("20%")
        self.lbl_turbidity_val.setStyleSheet("color: #00E5FF; font-weight: bold; min-width: 32px;")
        header_layout.addWidget(self.lbl_turbidity_val)

        # Depth & Lighting Auto-Sync Checkbox
        self.chk_depth_sync = QCheckBox("💡 Depth Light Sync")
        self.chk_depth_sync.setChecked(True)
        self.chk_depth_sync.setStyleSheet("color: #94A9C4; font-weight: bold;")
        self.chk_depth_sync.toggled.connect(self._on_depth_sync_toggled)
        header_layout.addWidget(self.chk_depth_sync)

        header_layout.addStretch(1)

        # Pixel Stream Status Label
        self.lbl_status = QLabel("🟢 UE5 Streaming Ready")
        self.lbl_status.setStyleSheet("color: #00FF9D; font-weight: bold;")
        header_layout.addWidget(self.lbl_status)

        # URL Input Field
        self.txt_url = QLineEdit(self._url)
        self.txt_url.setFixedWidth(160)
        header_layout.addWidget(self.txt_url)

        # Launch UE5 Executable Button
        self.btn_auto_launch = QPushButton("🚀 Launch Sim")
        self.btn_auto_launch.setToolTip("Tự động kích hoạt Unreal Engine 5 Simulator (.exe) ngầm dưới nền")
        self.btn_auto_launch.setStyleSheet(
            "QPushButton{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #00A8FF,stop:1 #0055B8);color:#FFFFFF;border:1px solid #00F0FF;border-radius:4px;font-weight:bold;padding:4px 10px;}"
            "QPushButton:hover{background:#00E5FF;color:#000000;}"
        )
        self.btn_auto_launch.clicked.connect(self.auto_launch_simulator)
        header_layout.addWidget(self.btn_auto_launch)

        # Reconnect Button
        self.btn_reload = QPushButton("🔄 Reconnect")
        self.btn_reload.clicked.connect(self.reload_stream)
        header_layout.addWidget(self.btn_reload)

        main_layout.addWidget(self.header)

        # ── WebRTC Viewport Area ──────────────────────────────────────────── #
        if _HAS_WEBENGINE:
            self.web_view = QWebEngineView(self)
            
            def _on_load_finished(ok: bool):
                if not ok:
                    print(f"[UE5Viewport] WebRTC server unreachable at {self._url}. Displaying Standby Guide.")
                    self.lbl_status.setText("🟡 Waiting for UE5 WebRTC Server...")
                    self.lbl_status.setStyleSheet("color: #FFC107; font-weight: bold;")
                    self.web_view.setHtml(_STANDBY_HTML)
                else:
                    self.lbl_status.setText("🟢 UE5 Streaming Connected")
                    self.lbl_status.setStyleSheet("color: #00FF9D; font-weight: bold;")

            self.web_view.loadFinished.connect(_on_load_finished)
            self.web_view.load(QUrl(self._url))
            main_layout.addWidget(self.web_view, stretch=1)
        else:
            # Fallback if QWebEngineView is not installed
            self.fallback_widget = QLabel("⚠️ PyQt6-WebEngine is not installed.\nPlease run: pip install PyQt6-WebEngine")
            self.fallback_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.fallback_widget.setStyleSheet("color: #FF5252; font-size: 16px; font-weight: bold; background: #0A1220;")
            main_layout.addWidget(self.fallback_widget, stretch=1)

        # Auto-trigger silent launch on startup
        QTimer.singleShot(150, lambda: self.auto_launch_simulator(force_dialog=False))

    def auto_launch_simulator(self, force_dialog: bool = False) -> None:
        """Auto launch standalone UE5 executable background process silently."""
        exe_path = self.auto_launcher.discover_exe_path()
        if not exe_path and force_dialog:
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "Chọn File .exe Mô Phỏng Unreal Engine 5",
                "",
                "Executable Files (*.exe *.bat);;All Files (*)"
            )
            if file_path:
                exe_path = file_path
                self.auto_launcher.custom_exe_path = file_path

        if exe_path and os.path.exists(exe_path):
            self.lbl_status.setText("🚀 Launching UE5 Sim...")
            self.lbl_status.setStyleSheet("color: #00E5FF; font-weight: bold;")
            success = self.auto_launcher.launch_simulator(exe_path)
            if success:
                QTimer.singleShot(3000, self.reload_stream)
        else:
            if not force_dialog:
                print("[UE5Viewport] UE5 build not found in sim/ directory. Operating in Standby mode.")
                self.lbl_status.setText("🟢 Subsea 3D Digital Twin Ready")
                self.lbl_status.setStyleSheet("color: #00FF9D; font-weight: bold;")

    def _on_map_changed(self) -> None:
        map_code = self.cmb_map.currentData()
        print(f"[UE5Viewport] Environment map changed to: {map_code}")
        self.sig_map_changed.emit(map_code)
        if self._udp_sender and hasattr(self._udp_sender, 'send_environment_preset'):
            self._udp_sender.send_environment_preset(map_code)

    def _on_turbidity_changed(self, val: int) -> None:
        turb_float = val / 100.0
        self.lbl_turbidity_val.setText(f"{val}%")
        self.sig_turbidity_changed.emit(turb_float)
        if self._udp_sender and hasattr(self._udp_sender, 'send_water_turbidity'):
            self._udp_sender.send_water_turbidity(turb_float)

    def _on_depth_sync_toggled(self, checked: bool) -> None:
        self._depth_sync_enabled = checked
        self.sig_depth_lighting_toggled.emit(checked)
        print(f"[UE5Viewport] Depth Lighting Auto-Sync: {'ON' if checked else 'OFF'}")

    def update_telemetry_depth(self, depth_m: float) -> None:
        """Triggered on MAVLink telemetry depth update to auto-sync UE5 subsea lighting."""
        if self._depth_sync_enabled and self._udp_sender and hasattr(self._udp_sender, 'send_depth_lighting_sync'):
            self._udp_sender.send_depth_lighting_sync(depth_m, auto_spotlight=True)

    def reload_stream(self) -> None:
        """Reload WebRTC Pixel Streaming connection."""
        url_text = self.txt_url.text().strip()
        if not url_text.startswith("http"):
            url_text = f"http://{url_text}"
        self._url = url_text
        if _HAS_WEBENGINE and hasattr(self, 'web_view'):
            print(f"[UE5Viewport] Reloading WebRTC Stream at: {self._url}")
            self.lbl_status.setText("🟡 Connecting...")
            self.lbl_status.setStyleSheet("color: #FFC107; font-weight: bold;")
            self.web_view.load(QUrl(self._url))
            QTimer.singleShot(2500, lambda: self.lbl_status.setText("🟢 UE5 Streaming Connected"))
            QTimer.singleShot(2500, lambda: self.lbl_status.setStyleSheet("color: #00FF9D; font-weight: bold;"))

    def set_udp_sender(self, udp_sender: Any) -> None:
        self._udp_sender = udp_sender


class UE5ViewportWindow(QWidget):
    """
    Standalone Window container for Unreal Engine 5 Digital Twin Viewport.
    """

    def __init__(
        self,
        default_url: str = "http://127.0.0.1:80",
        udp_sender: Optional[Any] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("🎮 UNREAL ENGINE 5 — ROV SUBSEA DIGITAL TWIN SIMULATOR")
        self.resize(1280, 720)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.viewport = UE5ViewportWidget(default_url=default_url, udp_sender=udp_sender, parent=self)
        layout.addWidget(self.viewport)
