"""
settings_dialog.py - ROV Configuration Settings Dialog
======================================================
Hộp thoại cấu hình nâng cao cho GCS ROV.
Chứa nút gạt Toggle Switch (Premium style) và giao diện Tabbed Settings.
"""
import os
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtWidgets import (
    QDialog, QWidget, QFormLayout, QLineEdit, QSpinBox, QDoubleSpinBox,
    QComboBox, QLabel, QCheckBox, QHBoxLayout, QVBoxLayout, QFileDialog,
    QDialogButtonBox, QTabWidget, QAbstractButton
)

# Bản đồ phím để hiển thị và lưu trữ
KEY_OPTIONS = ["W", "S", "A", "D", "Q", "E", "R", "F", "I", "K", "J", "L", "U", "O", "Up", "Down", "Left", "Right"]
TIMEZONE_OPTIONS = [
    "Asia/Ho_Chi_Minh", "UTC", "Asia/Bangkok", "Asia/Singapore", 
    "Asia/Tokyo", "Europe/London", "America/New_York", "Australia/Sydney"
]


class QToggleSwitch(QAbstractButton):
    """
    Nút gạt ON/OFF (Toggle Switch) thiết kế hiện đại, mượt mà.
    """
    def __init__(self, parent=None, width=44, height=22):
        super().__init__(parent)
        self.setCheckable(True)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed)
        self._width = width
        self._height = height
        self.setMinimumSize(width, height)
        
        # Biến hoạt họa vị trí nút tròn
        self._thumb_position = 2.0 if not self.isChecked() else float(self._width - self._height + 2)
        self._anim = QtCore.QPropertyAnimation(self, b"thumb_position", self)
        self._anim.setDuration(120)

    @QtCore.pyqtProperty(float)
    def thumb_position(self):
        return self._thumb_position

    @thumb_position.setter
    def thumb_position(self, pos):
        self._thumb_position = pos
        self.update()

    def setChecked(self, checked):
        super().setChecked(checked)
        target = float(self._width - self._height + 2) if checked else 2.0
        self._thumb_position = target
        self.update()

    def nextCheckState(self):
        self.setChecked(not self.isChecked())
        # Kích hoạt hoạt họa trượt
        target = float(self._width - self._height + 2) if self.isChecked() else 2.0
        self._anim.stop()
        self._anim.setStartValue(self._thumb_position)
        self._anim.setEndValue(target)
        self._anim.start()
        self.clicked.emit(self.isChecked())

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        
        # Vẽ nền nút gạt
        r = self._height / 2.0
        path = QtGui.QPainterPath()
        path.addRoundedRect(QtCore.QRectF(0, 0, self._width, self._height), r, r)
        
        # Màu nền thay đổi theo trạng thái
        if self.isChecked():
            bg_color = QtGui.QColor(0, 168, 255, 220)  # Cyan
        else:
            bg_color = QtGui.QColor(30, 53, 80, 180)   # Navy tối
        
        painter.fillPath(path, bg_color)
        
        # Vẽ nút tròn (Thumb)
        thumb_size = self._height - 4
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(QtGui.QColor(255, 255, 255, 240))
        painter.drawEllipse(QtCore.QRectF(self._thumb_position, 2, thumb_size, thumb_size))
        
        painter.end()


class SettingsDialog(QDialog):
    """
    Hộp thoại cài đặt phân chia theo Tab.
    Đã lược bỏ các mục tự động hóa (MockMode, CAD load) và gộp Logs.
    """
    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ROV Configuration & System Settings")
        self.setMinimumWidth(500)
        self.setMinimumHeight(380)
        self.settings = dict(settings)

        self.tabs = QTabWidget()

        # --- TAB 1: KẾT NỐI & HỆ THỐNG ---
        tab_gen = QWidget()
        form_gen = QFormLayout(tab_gen)
        
        self.ed_conn = QLineEdit(settings.get("connection", "udp:0.0.0.0:14550"))
        form_gen.addRow("MAVLink Connection:", self.ed_conn)

        self.sp_slam_port = QSpinBox()
        self.sp_slam_port.setRange(1024, 65535)
        self.sp_slam_port.setValue(settings.get("slam_port", 5010))
        form_gen.addRow("SLAM UDP Port:", self.sp_slam_port)

        self.cb_tz = QComboBox()
        self.cb_tz.addItems(TIMEZONE_OPTIONS)
        self.cb_tz.setCurrentText(settings.get("timezone", "Asia/Ho_Chi_Minh"))
        form_gen.addRow("Timezone:", self.cb_tz)

        # Vị trí GCS (dùng để tính toạ độ ROV trên Google Maps)
        lbl_gcs_hdr = QLabel("Vị trí trạm GCS (Google Maps)")
        lbl_gcs_hdr.setStyleSheet("color:#00A8FF;font-weight:bold;margin-top:6px;")
        form_gen.addRow(lbl_gcs_hdr)

        self.ed_gcs_lat = QLineEdit(str(settings.get("gcs_lat", "")))
        self.ed_gcs_lat.setPlaceholderText("21.028511 (vĩ độ — bắt buộc)")
        form_gen.addRow("GCS Latitude:", self.ed_gcs_lat)

        self.ed_gcs_lng = QLineEdit(str(settings.get("gcs_lng", "")))
        self.ed_gcs_lng.setPlaceholderText("105.854167 (kinh độ — bắt buộc)")
        form_gen.addRow("GCS Longitude:", self.ed_gcs_lng)

        btn_get_loc = QtWidgets.QPushButton("📍 Lấy vị trí hiện tại")
        btn_get_loc.setToolTip("Lấy GPS từ máy tính (nếu có module GPS/Wi-Fi)")
        btn_get_loc.clicked.connect(self._auto_detect_location)
        form_gen.addRow("", btn_get_loc)

        lbl_gcs_info = QLabel(
            "Nhập đúng toạ độ GCS để Google Maps hiển thị đúng vị trí ROV.\n"
            "Mẹo: Google Maps → chuột phải vào vị trí → sao chép toạ độ."
        )
        lbl_gcs_info.setWordWrap(True)
        lbl_gcs_info.setStyleSheet("color:#5B748E;font-size:10px;")
        form_gen.addRow("", lbl_gcs_info)

        # --- TAB 2: LƯU TRỮ VÀ LOGS (GỘP CHUNG) ---
        tab_log = QWidget()
        form_log = QFormLayout(tab_log)
        
        row_logs = QWidget()
        hl_logs = QHBoxLayout(row_logs)
        hl_logs.setContentsMargins(0, 0, 0, 0)
        self.ed_logs = QLineEdit(settings.get("blackbox_path", "logs"))
        btn_logs = QtWidgets.QPushButton("Browse...")
        btn_logs.clicked.connect(self._browse_logs_folder)
        hl_logs.addWidget(self.ed_logs)
        hl_logs.addWidget(btn_logs)
        form_log.addRow("Blackbox & CSV Logs Path:", row_logs)
        
        lbl_info = QLabel("Cả Blackbox nhị phân và file CSV hoạt động của ROV sẽ được tự động lưu chung trong thư mục này.")
        lbl_info.setWordWrap(True)
        lbl_info.setStyleSheet("color: #5B748E; font-size: 10px;")
        form_log.addRow("", lbl_info)

        # --- TAB 3: GÁN PHÍM & TAY CẦM ---
        tab_ctrl = QWidget()
        form_ctrl = QFormLayout(tab_ctrl)
        
        self.cb_fwd = QComboBox()
        self.cb_fwd.addItems(KEY_OPTIONS)
        self.cb_fwd.setCurrentText(settings.get("key_forward", "W"))
        form_ctrl.addRow("Surge Forward (Tiến):", self.cb_fwd)

        self.cb_bwd = QComboBox()
        self.cb_bwd.addItems(KEY_OPTIONS)
        self.cb_bwd.setCurrentText(settings.get("key_backward", "S"))
        form_ctrl.addRow("Surge Backward (Lùi):", self.cb_bwd)

        self.cb_left = QComboBox()
        self.cb_left.addItems(KEY_OPTIONS)
        self.cb_left.setCurrentText(settings.get("key_left", "A"))
        form_ctrl.addRow("Yaw Left (Xoay Trái):", self.cb_left)

        self.cb_right = QComboBox()
        self.cb_right.addItems(KEY_OPTIONS)
        self.cb_right.setCurrentText(settings.get("key_right", "D"))
        form_ctrl.addRow("Yaw Right (Xoay Phải):", self.cb_right)

        self.cb_sw_l = QComboBox()
        self.cb_sw_l.addItems(KEY_OPTIONS)
        self.cb_sw_l.setCurrentText(settings.get("key_sway_left", "Q"))
        form_ctrl.addRow("Sway Left (Sang Trái):", self.cb_sw_l)

        self.cb_sw_r = QComboBox()
        self.cb_sw_r.addItems(KEY_OPTIONS)
        self.cb_sw_r.setCurrentText(settings.get("key_sway_right", "E"))
        form_ctrl.addRow("Sway Right (Sang Phải):", self.cb_sw_r)

        self.cb_asc = QComboBox()
        self.cb_asc.addItems(KEY_OPTIONS)
        self.cb_asc.setCurrentText(settings.get("key_ascend", "R"))
        form_ctrl.addRow("Heave Up (Nổi lên):", self.cb_asc)

        self.cb_desc = QComboBox()
        self.cb_desc.addItems(KEY_OPTIONS)
        self.cb_desc.setCurrentText(settings.get("key_descend", "F"))
        form_ctrl.addRow("Heave Down (Lặn xuống):", self.cb_desc)

        # Nút gạt Toggle Switch ON/OFF cho Gamepad IMU
        self.sw_imu = QToggleSwitch()
        self.sw_imu.setChecked(settings.get("enable_imu_gamepad", False))
        form_ctrl.addRow("Enable Gamepad IMU Mimic Target:", self.sw_imu)

        # --- TAB 4: CHẾ ĐỘ TỰ ĐỘNG ---
        tab_smart = QWidget()
        form_smart = QFormLayout(tab_smart)

        self.sp_rth = QDoubleSpinBox()
        self.sp_rth.setRange(0.1, 50.0)
        self.sp_rth.setValue(float(settings.get("rth_depth", 2.0)))
        form_smart.addRow("Return to Home Safety Depth (m):", self.sp_rth)

        self.sp_hz = QSpinBox()
        self.sp_hz.setRange(1, 10)
        self.sp_hz.setValue(int(settings.get("heartbeat_hz", 1)))
        form_smart.addRow("MAVLink Heartbeat Rate (Hz):", self.sp_hz)

        self.chk_reset_arm = QCheckBox()
        self.chk_reset_arm.setChecked(settings.get("auto_reset_origin", True))
        form_smart.addRow("Auto Reset SLAM Origin on ARM:", self.chk_reset_arm)

        # --- TAB 5: VIDEO & AR HUD ---
        tab_video = QWidget()
        form_vid = QFormLayout(tab_video)

        self.cb_vid_source = QComboBox()
        self.cb_vid_source.addItems([
            "UDP H.264 (ROV → GCS port 5620)",
            "RTSP (Pi Camera)",
            "Webcam (USB Local)",
            "Video File",
        ])
        src_map = {"udp_h264": 0, "rtsp": 1, "webcam": 2, "file": 3}
        self.cb_vid_source.setCurrentIndex(
            src_map.get(settings.get("video_source", "udp_h264"), 0)
        )
        form_vid.addRow("Video Source:", self.cb_vid_source)

        self.sp_udp_port = QSpinBox()
        self.sp_udp_port.setRange(1024, 65535)
        self.sp_udp_port.setValue(int(settings.get("udp_video_port", 5620)))
        form_vid.addRow("UDP H.264 Port:", self.sp_udp_port)

        self.ed_rtsp_url = QLineEdit(
            settings.get("rtsp_url", "rtsp://192.168.2.2:8554/video")
        )
        self.ed_rtsp_url.setPlaceholderText("rtsp://192.168.2.2:8554/video")
        form_vid.addRow("RTSP URL:", self.ed_rtsp_url)

        self.sp_webcam_idx = QSpinBox()
        self.sp_webcam_idx.setRange(0, 9)
        self.sp_webcam_idx.setValue(int(settings.get("webcam_index", 0)))
        form_vid.addRow("Webcam Index:", self.sp_webcam_idx)

        row_vid_file = QWidget()
        hl_vid = QHBoxLayout(row_vid_file)
        hl_vid.setContentsMargins(0, 0, 0, 0)
        self.ed_vid_file = QLineEdit(settings.get("video_file", ""))
        self.ed_vid_file.setPlaceholderText("D:/test_video.mp4")
        btn_vid_browse = QtWidgets.QPushButton("Browse...")
        btn_vid_browse.clicked.connect(self._browse_video_file)
        hl_vid.addWidget(self.ed_vid_file)
        hl_vid.addWidget(btn_vid_browse)
        form_vid.addRow("Video File Path:", row_vid_file)

        self.sp_vid_fps = QSpinBox()
        self.sp_vid_fps.setRange(5, 60)
        self.sp_vid_fps.setValue(int(settings.get("video_fps", 30)))
        form_vid.addRow("Target FPS:", self.sp_vid_fps)

        self.cb_vid_res = QComboBox()
        self.cb_vid_res.addItems(["1280x720", "Native (Gốc)", "640x480", "1920x1080", "320x240"])
        self.cb_vid_res.setCurrentText(settings.get("video_resolution", "1280x720"))
        form_vid.addRow("Resolution:", self.cb_vid_res)

        self.sw_hud = QToggleSwitch()
        self.sw_hud.setChecked(settings.get("ar_hud_enabled", True))
        form_vid.addRow("Enable AR HUD Overlay:", self.sw_hud)

        self.sw_ai = QToggleSwitch()
        self.sw_ai.setChecked(settings.get("ai_detection_enabled", False))
        form_vid.addRow("Enable AI Detection:", self.sw_ai)

        # ── Đường dẫn lưu ảnh/video ───────────────────────────────
        lbl_media_hdr = QLabel("Lưu trữ Snapshot / Recording")
        lbl_media_hdr.setStyleSheet("color:#00A8FF;font-weight:bold;margin-top:4px;")
        form_vid.addRow(lbl_media_hdr)

        row_media = QWidget()
        hl_media = QHBoxLayout(row_media)
        hl_media.setContentsMargins(0, 0, 0, 0)
        default_media = settings.get("media_save_path", "")
        self.ed_media_path = QLineEdit(default_media)
        self.ed_media_path.setPlaceholderText("Mặc định: D:/GCS_ROV_Media")
        btn_media = QtWidgets.QPushButton("Browse...")
        btn_media.clicked.connect(self._browse_media_folder)
        hl_media.addWidget(self.ed_media_path)
        hl_media.addWidget(btn_media)
        form_vid.addRow("Media Save Path:", row_media)

        # Ghi chú
        lbl_vid = QLabel(
            "UDP H.264: nhận luồng H.264/RTP từ ROV qua UDP (port 5620).\n"
            "RTSP: kết nối camera Pi qua mạng.\n"
            "Webcam: dùng USB camera cắm trực tiếp vào GCS.\n"
            "Video File: phát lại video để test AI."
        )
        lbl_vid.setWordWrap(True)
        lbl_vid.setStyleSheet("color: #5B748E; font-size: 10px;")
        form_vid.addRow("", lbl_vid)

        # --- TAB 6: BẢN QUYỀN (LICENSE) ---
        tab_lic = QWidget()
        form_lic = QFormLayout(tab_lic)

        try:
            from core.licensing import LicenseManager
            lic_mgr = LicenseManager.get_instance()
            info = lic_mgr.get_license_info()
            mid_val = lic_mgr.machine_id
            stat_msg = info.status_message
            is_val = info.is_valid
        except Exception:
            lic_mgr = None
            mid_val = "N/A"
            stat_msg = "Chưa kết nối License Engine"
            is_val = False

        lbl_mid_val = QLabel(mid_val)
        lbl_mid_val.setStyleSheet("color:#00F0FF; font-family:Consolas; font-weight:bold; font-size:12px;")
        
        btn_copy_mid = QtWidgets.QPushButton("📋 Sao chép")
        btn_copy_mid.setStyleSheet("padding:4px 8px; font-size:11px;")
        btn_copy_mid.clicked.connect(lambda: (
            QtWidgets.QApplication.clipboard().setText(mid_val),
            QtWidgets.QMessageBox.information(self, "Đã sao chép", "Đã sao chép Machine ID vào bộ nhớ tạm!")
        ))
        
        hl_mid = QHBoxLayout()
        hl_mid.addWidget(lbl_mid_val)
        hl_mid.addWidget(btn_copy_mid)
        hl_mid.addStretch()
        form_lic.addRow("Mã máy (Machine ID):", hl_mid)

        lbl_lic_status = QLabel(stat_msg)
        lbl_lic_status.setStyleSheet("color:#00FF88; font-weight:bold;" if is_val else "color:#FF4444; font-weight:bold;")
        form_lic.addRow("Trạng thái:", lbl_lic_status)

        self.ed_license_key = QLineEdit()
        self.ed_license_key.setPlaceholderText("Dán mã kích hoạt NEXOS-XXXX-... vào đây")
        
        btn_act_now = QtWidgets.QPushButton("🚀 Kích hoạt")
        btn_act_now.setStyleSheet("padding:4px 10px; font-size:11px; font-weight:bold; background:#0052D4; color:white;")
        
        def _activate_settings_key():
            if not lic_mgr:
                return
            k = self.ed_license_key.text().strip()
            if not k:
                QtWidgets.QMessageBox.warning(self, "Lỗi", "Vui lòng nhập License Key.")
                return
            ok, msg = lic_mgr.activate_key(k)
            if ok:
                QtWidgets.QMessageBox.information(self, "Thành công", msg)
                new_info = lic_mgr.get_license_info()
                lbl_lic_status.setText(new_info.status_message)
                lbl_lic_status.setStyleSheet("color:#00FF88; font-weight:bold;")
                self.ed_license_key.clear()
            else:
                QtWidgets.QMessageBox.critical(self, "Thất bại", msg)

        btn_act_now.clicked.connect(_activate_settings_key)
        hl_act = QHBoxLayout()
        hl_act.addWidget(self.ed_license_key)
        hl_act.addWidget(btn_act_now)
        form_lic.addRow("Kích hoạt Key:", hl_act)

        # Thêm các tab
        self.tabs.addTab(tab_gen, "General")
        self.tabs.addTab(tab_log, "Logging")
        self.tabs.addTab(tab_ctrl, "Controls")
        self.tabs.addTab(tab_smart, "Autopilot")
        self.tabs.addTab(tab_video, "Video & AI")
        self.tabs.addTab(tab_lic, "License")

        # Dialog Buttons
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._save_and_accept)
        btns.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        layout.addWidget(self.tabs)
        layout.addWidget(btns)
        self.setLayout(layout)

        # Style đồng bộ GCS dark theme
        self.setStyleSheet("""
            QDialog { 
                background: #070E18; 
                color: #C2D6EC; 
                font-family: "Segoe UI", sans-serif;
            }
            QTabWidget::pane { 
                border: 1px solid rgba(0, 212, 255, 0.25); 
                background: #0A1424; 
                border-radius: 8px; 
            }
            QTabBar::tab { 
                background: #0D1B2D; 
                color: #7B9BBF; 
                padding: 8px 18px; 
                font-weight: bold; 
                border-top-left-radius: 6px; 
                border-top-right-radius: 6px; 
                margin-right: 3px; 
                border: 1px solid #1E385B;
                border-bottom: none;
            }
            QTabBar::tab:selected { 
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #005580, stop:1 #0D223A);
                color: #FFFFFF; 
                border: 1px solid #00D4FF; 
                border-bottom: 2px solid #00F0FF; 
            }
            QTabBar::tab:hover:!selected { 
                background: #142842; 
                color: #00E5FF; 
            }
            QLabel { 
                color: #C2D6EC; 
                font-weight: 500;
            }
            QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
                background: #0A1626; 
                color: #00E5FF;
                border: 1px solid #1E3D66; 
                border-radius: 6px; 
                padding: 5px 10px; 
                font-weight: bold;
                min-height: 26px;
            }
            QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
                border: 1px solid #00F0FF; 
                background: #102540;
            }
            QComboBox QAbstractItemView {
                background-color: #0A1626;
                color: #00E5FF;
                border: 1px solid #00D4FF;
                border-radius: 6px;
                selection-background-color: #005580;
                selection-color: #FFFFFF;
                padding: 4px;
            }
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #162E4D, stop:1 #0C1D33);
                color: #00E5FF;
                border: 1px solid #244B7A; 
                border-radius: 6px; 
                padding: 6px 16px; 
                font-weight: bold;
                min-height: 28px;
            }
            QPushButton:hover { 
                border-color: #00F0FF; 
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #0077B3, stop:1 #004D73);
                color: #FFFFFF; 
            }
            QCheckBox { 
                color: #DDF0FF; 
                font-weight: 600; 
                spacing: 8px;
            }
            QCheckBox::indicator { 
                width: 16px; 
                height: 16px; 
                border-radius: 4px; 
                border: 1px solid #234770; 
                background: #0D1B2D; 
            }
            QCheckBox::indicator:checked { 
                background: #00D4FF; 
                border: 1px solid #00F0FF; 
            }
        """)

    def _auto_detect_location(self):
        """Cố gắng lấy toạ độ từ IP geolocation (không cần GPS phần cứng)."""
        try:
            import urllib.request, json
            with urllib.request.urlopen("http://ip-api.com/json/?fields=lat,lon,city", timeout=4) as r:
                data = json.loads(r.read())
            lat, lon = data.get('lat', ''), data.get('lon', '')
            city = data.get('city', '')
            if lat and lon:
                self.ed_gcs_lat.setText(str(lat))
                self.ed_gcs_lng.setText(str(lon))
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.information(
                    self, "Vị trí phát hiện",
                    f"Tìm thấy vị trí: {city}\nLat: {lat}  Lon: {lon}\n\n"
                    "Lưu ý: IP geolocation có sai số ~1–10 km.\n"
                    "Hãy kiểm tra và sửa lại nếu cần."
                )
        except Exception as e:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self, "Không thể tự động lấy vị trí",
                f"Lỗi: {e}\n\nVui lòng nhập thủ công tạ độ GCS."
            )

    def _browse_media_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Chọn thư mục lưu Snapshot & Video")
        if path:
            self.ed_media_path.setText(path)

    def _browse_video_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Chọn Video File", "",
            "Video Files (*.mp4 *.avi *.mkv *.mov);;All Files (*)"
        )
        if path:
            self.ed_vid_file.setText(path)

    def _browse_logs_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Chọn thư mục lưu Logs & Blackbox")
        if path:
            self.ed_logs.setText(path)

    def _save_and_accept(self):
        logs_dir  = self.ed_logs.text().strip()
        media_dir = self.ed_media_path.text().strip() or "D:/GCS_ROV_Media"
        src_list  = ["udp_h264", "rtsp", "webcam", "file"]

        # Parse GCS lat/lon
        try:
            gcs_lat = float(self.ed_gcs_lat.text().strip())
        except ValueError:
            gcs_lat = 0.0
        try:
            gcs_lng = float(self.ed_gcs_lng.text().strip())
        except ValueError:
            gcs_lng = 0.0

        self.settings.update({
            "connection":     self.ed_conn.text().strip(),
            "gcs_lat":        gcs_lat,
            "gcs_lng":        gcs_lng,
            "video_source":      src_list[self.cb_vid_source.currentIndex()],
            "udp_video_port":    self.sp_udp_port.value(),
            "rtsp_url":          self.ed_rtsp_url.text().strip(),
            "webcam_index":      self.sp_webcam_idx.value(),
            "video_file":        self.ed_vid_file.text().strip(),
            "video_fps":         self.sp_vid_fps.value(),
            "video_resolution":  self.cb_vid_res.currentText(),
            "ar_hud_enabled":    self.sw_hud.isChecked(),
            "ai_detection_enabled": self.sw_ai.isChecked(),
            "media_save_path":   media_dir,
            "slam_port":  self.sp_slam_port.value(),
            "timezone":   self.cb_tz.currentText(),
            "blackbox_path": logs_dir,
            "csv_log_path":  os.path.join(logs_dir, "rov_activity.csv"),
            "key_forward":    self.cb_fwd.currentText(),
            "key_backward":   self.cb_bwd.currentText(),
            "key_left":       self.cb_left.currentText(),
            "key_right":      self.cb_right.currentText(),
            "key_sway_left":  self.cb_sw_l.currentText(),
            "key_sway_right": self.cb_sw_r.currentText(),
            "key_ascend":     self.cb_asc.currentText(),
            "key_descend":    self.cb_desc.currentText(),
            "enable_imu_gamepad": self.sw_imu.isChecked(),
            "rth_depth":      self.sp_rth.value(),
            "heartbeat_hz":   self.sp_hz.value(),
            "auto_reset_origin": self.chk_reset_arm.isChecked(),
        })
        self.accept()

