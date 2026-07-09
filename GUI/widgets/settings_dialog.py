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

        # Thêm các tab
        self.tabs.addTab(tab_gen, "General")
        self.tabs.addTab(tab_log, "Logging")
        self.tabs.addTab(tab_ctrl, "Controls")
        self.tabs.addTab(tab_smart, "Autopilot")

        # Dialog Buttons
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._save_and_accept)
        btns.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addWidget(self.tabs)
        layout.addWidget(btns)
        self.setLayout(layout)

        # Style đồng bộ GCS dark theme
        self.setStyleSheet("""
            QDialog { background:#0D1726; color:#A0B2C6; }
            QTabWidget::pane { border: 1px solid #1E3550; background: #0D1726; }
            QTabBar::tab { background: #060B14; color: #5B748E; padding: 6px 12px; border-top-left-radius: 4px; border-top-right-radius: 4px; }
            QTabBar::tab:selected { background: #0D1726; color: #00A8FF; font-weight: bold; border: 1px solid #1E3550; border-bottom: none; }
            QLabel { color:#A0B2C6; }
            QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
                background:#060B14; color:#00A8FF;
                border:1px solid #1E3550; border-radius:3px; padding:3px;
            }
            QComboBox QAbstractItemView {
                background-color: #060B14;
                color: #00A8FF;
                selection-background-color: #00A8FF;
                selection-color: #060B14;
            }
            QPushButton {
                background:#0D1726; color:#00A8FF;
                border:1px solid #1E3550; border-radius:4px; padding:4px 10px;
            }
            QPushButton:hover { border-color:#00A8FF; background: rgba(0, 168, 255, 0.1); }
            QCheckBox { color:#A0B2C6; }
        """)

    def _browse_logs_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Chọn thư mục lưu Logs & Blackbox")
        if path:
            self.ed_logs.setText(path)

    def _save_and_accept(self):
        logs_dir = self.ed_logs.text().strip()
        self.settings.update({
            "connection": self.ed_conn.text().strip(),
            "slam_port": self.sp_slam_port.value(),
            "timezone": self.cb_tz.currentText(),
            "blackbox_path": logs_dir,
            "csv_log_path": os.path.join(logs_dir, "rov_activity.csv"),
            "key_forward": self.cb_fwd.currentText(),
            "key_backward": self.cb_bwd.currentText(),
            "key_left": self.cb_left.currentText(),
            "key_right": self.cb_right.currentText(),
            "key_sway_left": self.cb_sw_l.currentText(),
            "key_sway_right": self.cb_sw_r.currentText(),
            "key_ascend": self.cb_asc.currentText(),
            "key_descend": self.cb_desc.currentText(),
            "enable_imu_gamepad": self.sw_imu.isChecked(),
            "rth_depth": self.sp_rth.value(),
            "heartbeat_hz": self.sp_hz.value(),
            "auto_reset_origin": self.chk_reset_arm.isChecked(),
        })
        self.accept()
