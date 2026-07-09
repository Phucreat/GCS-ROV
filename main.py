"""
main.py - GCS ROV Main Application Entry Point
===============================================
Tích hợp tất cả module vào giao diện guirov.py (Ui_MainWindow).

Kiến trúc:
  guirov.Ui_MainWindow  → Layout gốc (KHÔNG sửa)
  ROVMainWindow         → Class con kế thừa QMainWindow + Ui_MainWindow
                          Thêm widget, kết nối signal, vòng lặp 60 FPS

Sơ đồ dữ liệu:
  MAVLink Thread  ──────signal──────→ ROVMainWindow
  SLAM UDP Thread ──────signal──────→ ROVMainWindow
  Physics Engine  ←── step() ←── QTimer 60 FPS
  GUI Widgets     ←── update ←── ROVMainWindow

Cách chạy:
  python main.py
  python main.py --connection udp:0.0.0.0:14550
  python main.py --mock          (chế độ mô phỏng offline)
"""
import sys
import math
import time
import argparse
import numpy as np

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout,
    QWidget, QFileDialog, QDialog, QFormLayout, QLineEdit,
    QDialogButtonBox, QComboBox, QLabel, QSpinBox, QDoubleSpinBox,
    QCheckBox, QTableWidget, QTableWidgetItem, QHeaderView, QSplitter,
    QTabWidget
)

# --- Bản đồ phím bàn phím ---
KEY_MAP = {
    "W": Qt.Key.Key_W, "S": Qt.Key.Key_S, "A": Qt.Key.Key_A, "D": Qt.Key.Key_D,
    "Q": Qt.Key.Key_Q, "E": Qt.Key.Key_E, "R": Qt.Key.Key_R, "F": Qt.Key.Key_F,
    "I": Qt.Key.Key_I, "K": Qt.Key.Key_K, "J": Qt.Key.Key_J, "L": Qt.Key.Key_L,
    "U": Qt.Key.Key_U, "O": Qt.Key.Key_O,
    "Up": Qt.Key.Key_Up, "Down": Qt.Key.Key_Down, "Left": Qt.Key.Key_Left, "Right": Qt.Key.Key_Right
}

# --- Import GUI layout ---
import os, sys
# Thêm thư mục gốc dự án vào path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'GUI'))

from GUI.guirov import Ui_MainWindow

# --- Import các module tự viết ---
from core.models.rov_6thruster import ROV6ThrusterModel
from core.models.rov_3thruster import ROV3ThrusterModel
from core.physics_engine import PhysicsEngine
from GUI.widgets.gl_3d_widget import GLROVWidget
from GUI.widgets.gl_compass_3d_widget import GLCompass3DWidget
from GUI.widgets.power_widget import PowerWidget
from network.mavlink_worker import MAVLinkWorker
from network.slam_udp_receiver import SLAMUDPReceiver

# Thử import input handler nếu có
try:
    from GUI.input_handler import InputHandler
    HAS_INPUT = True
except ImportError:
    HAS_INPUT = False


# ==============================================================
# CÁC MODEL ROV HỖ TRỢ
# ==============================================================
ROV_MODELS = {
    "3DC": ROV3ThrusterModel,
    "6DC": ROV6ThrusterModel,
}


# ==============================================================
# IMPORT SETTINGS DIALOG
# ==============================================================
from GUI.widgets.settings_dialog import SettingsDialog
# MAIN WINDOW
# ==============================================================
class ROVMainWindow(QMainWindow):
    """
    Cửa sổ chính kế thừa QMainWindow và tích hợp Ui_MainWindow.
    Thay thế các QOpenGLWidget placeholder bằng widget thực:
      - opw_motion    → GLROVWidget (3D OpenGL)
      - ogl_powersys  → PowerWidget (đồ thị điện năng)
      - frm_simulate_view_bottom → SLAMRadarWidget
    """

    def __init__(self, settings: dict):
        super().__init__()
        self.settings = settings

        # --- Setup UI ---
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        # --- Trạng thái ---
        self._current_model_name = "6DC"
        self._rov_model   = None
        self._physics     = None
        self._mav_worker  = None
        self._slam_worker = None
        self._input_hdlr  = None
        self._origin_set  = False

        # Dữ liệu telemetry (cập nhật từ MAVLink)
        self._roll    = 0.0   # rad
        self._pitch   = 0.0
        self._yaw     = 0.0
        self._depth   = 0.0   # m
        self._heading = 0.0   # deg
        self._pos_ned = np.zeros(3)
        self._vel_ned = np.zeros(3)
        self._voltage = 16.8
        self._current = 0.0
        self._throttle = 0.0
        self._flight_mode  = "MANUAL"
        self._sys_status   = "ACTIVE"
        self._connected    = False
        self._link_quality = 0

        # Telemetry table data
        self._named_sensors: dict = {}

        # Control inputs (keyboard/gamepad)
        self._ctrl = dict(surge=0., sway=0., heave=0.,
                          roll=0., pitch=0., yaw=0.)
        self._speed_scale = 1.0  # 0.25 / 0.5 / 0.75 / 1.0
        
        # Biến điều khiển làm mượt và phím đang nhấn
        self._smoothed_ctrl = dict(surge=0., sway=0., heave=0., roll=0., pitch=0., yaw=0.)
        self._pressed_keys = set()

        # --- Thay thế placeholder widgets ---
        self._inject_3d_widget()
        self._inject_power_widget()
        self._inject_slam_radar()

        # --- Kết nối signal/slot của UI gốc ---
        # Chặn signal trước để tránh currentTextChanged bắn sớm
        self.ui.cb_mission.blockSignals(True)
        # Set combobox về 6DC (index 1 theo guirov.py: 0="3DC", 1="6DC")
        idx = self.ui.cb_mission.findText("6DC")
        if idx >= 0:
            self.ui.cb_mission.setCurrentIndex(idx)
        self.ui.cb_mission.blockSignals(False)

        self._connect_ui_signals()

        # --- Khởi tạo model ROV ---
        self._switch_model("6DC")

        # --- Clock/Date timer ---
        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._update_clock)
        self._clock_timer.start(1000)
        self._update_clock()

        # --- Physics + Render loop 60 FPS ---
        self._frame_timer = QTimer(self)
        self._frame_timer.timeout.connect(self._on_frame)
        self._frame_timer.start(16)  # ~62.5 FPS

        # --- Khởi động kết nối ---
        self._start_workers()

        # --- Telemetry table (inject QTableWidget thay QTableView) ---
        self._inject_telemetry_table()
        self._setup_telemetry_table()

    # ----------------------------------------------------------
    # INJECT WIDGETS VÀO LAYOUT GỐC
    # ----------------------------------------------------------
    def _inject_3d_widget(self):
        """Thay QOpenGLWidget 'opw_motion' bằng GLROVWidget."""
        parent = self.ui.frm_simulate_motion
        layout = self.ui.verticalLayout_6

        # Ẩn placeholder
        self.ui.opw_motion.hide()
        layout.removeWidget(self.ui.opw_motion)

        # Thêm widget 3D thật
        self.gl_3d = GLROVWidget(parent=parent)
        layout.addWidget(self.gl_3d)
        layout.setStretch(0, 1)   # label
        layout.setStretch(1, 20)  # 3D view

    def _inject_power_widget(self):
        """Thay QOpenGLWidget 'ogl_powersys' bằng PowerWidget."""
        parent = self.ui.frm_power_sys
        layout = self.ui.verticalLayout_19

        self.ui.ogl_powersys.hide()
        layout.removeWidget(self.ui.ogl_powersys)

        self.power_widget = PowerWidget(parent=parent)
        layout.addWidget(self.power_widget)
        layout.setStretch(0, 1)
        layout.setStretch(1, 11)

    def _inject_slam_radar(self):
        """Thêm GLCompass3DWidget vào frm_simulate_view_bottom làm la bàn 3D."""
        parent = self.ui.frm_simulate_view_bottom
        layout = self.ui.verticalLayout_12

        self.compass_3d = GLCompass3DWidget(parent=parent)
        layout.addWidget(self.compass_3d)

    def _inject_telemetry_table(self):
        """
        Thay QTableView 'tabl_data' bằng QTableWidget.
        QTableView chỉ hỗ trợ model-based API (không có setItem/setColumnCount).
        """
        parent = self.ui.frm_telemetry_data
        layout = self.ui.verticalLayout_20

        # Ẩn và xóa placeholder QTableView
        self.ui.tabl_data.hide()
        layout.removeWidget(self.ui.tabl_data)

        # Thay bằng QTableWidget đầy đủ chức năng
        self._telem_table = QTableWidget(parent=parent)
        layout.addWidget(self._telem_table)
        layout.setStretch(0, 1)   # label
        layout.setStretch(1, 20)  # table

    # ----------------------------------------------------------
    # KẾT NỐI SIGNAL/SLOT CỦA UI GỐC
    # ----------------------------------------------------------
    def _gui_press(self, setting_key: str):
        """Bổ sung mã phím cấu hình vào set phím nhấn khi bấm chuột trên GUI."""
        key_name = self.settings.get(setting_key)
        key_code = KEY_MAP.get(key_name)
        if key_code is not None:
            self._pressed_keys.add(key_code)

    def _gui_release(self, setting_key: str):
        """Xóa mã phím ra khỏi set khi nhả nút chuột trên GUI."""
        key_name = self.settings.get(setting_key)
        key_code = KEY_MAP.get(key_name)
        if key_code is not None and key_code in self._pressed_keys:
            self._pressed_keys.remove(key_code)

    def _connect_ui_signals(self):
        # Header: chọn model ROV
        self.ui.cb_mission.currentTextChanged.connect(self._switch_model)

        # Header: nút settings
        self.ui.setup_systeam.clicked.connect(self._open_settings)

        # Các phím bấm trên giao diện GUI - đồng bộ trực tiếp với set phím bấm để điều khiển mượt mà
        self.ui.pbtn_up.pressed.connect(lambda: self._gui_press("key_forward"))
        self.ui.pbtn_up.released.connect(lambda: self._gui_release("key_forward"))
        
        self.ui.pbtn_down.pressed.connect(lambda: self._gui_press("key_backward"))
        self.ui.pbtn_down.released.connect(lambda: self._gui_release("key_backward"))
        
        self.ui.pbtn_left.pressed.connect(lambda: self._gui_press("key_left"))
        self.ui.pbtn_left.released.connect(lambda: self._gui_release("key_left"))
        
        self.ui.pbtn_right.pressed.connect(lambda: self._gui_press("key_right"))
        self.ui.pbtn_right.released.connect(lambda: self._gui_release("key_right"))
        
        self.ui.pbtn_stop.clicked.connect(self._emergency_stop)

        # Điều khiển độ sâu trên GUI
        self.ui.pbtn_control_depth_increase.pressed.connect(lambda: self._gui_press("key_ascend"))
        self.ui.pbtn_control_depth_increase.released.connect(lambda: self._gui_release("key_ascend"))
        
        self.ui.pbtn_control_depth_decrease.pressed.connect(lambda: self._gui_press("key_descend"))
        self.ui.pbtn_control_depth_decrease.released.connect(lambda: self._gui_release("key_descend"))
        
        self.ui.pushButton.clicked.connect(self._emergency_stop)  # Nút STOP khẩn cấp

        # Speed control
        self.ui.pbtn_speed_increase.clicked.connect(self._speed_up)
        self.ui.pbtn_speed_decrease.clicked.connect(self._speed_down)

        # LED / Camera / ARM
        self.ui.pbtn_led_onoff.clicked.connect(self._toggle_led)
        self.ui.pbtn_led_increase.clicked.connect(
            lambda: self._mav_lights(True))
        self.ui.pbtn_led_decrease.clicked.connect(
            lambda: self._mav_lights(False))
        self.ui.pushButton_3.clicked.connect(self._toggle_arm)  # ARM button

    # ----------------------------------------------------------
    # KHỞI TẠO MODEL ROV
    # ----------------------------------------------------------
    def find_cad_file(self, model_name: str) -> str:
        """Tự động tìm kiếm file CAD tương ứng với model trong các thư mục dự án."""
        name_lower = model_name.lower().strip()
        search_dirs = [
            os.path.join(PROJECT_ROOT, "assets"),
            PROJECT_ROOT,
            os.path.join(PROJECT_ROOT, "GUI", "img"),
        ]
        extensions = [".stl", ".STL", ".obj", ".OBJ"]
        patterns = [
            f"rov_{name_lower}",
            f"{name_lower}",
            f"rov_{name_lower}_model",
            f"{name_lower}_model",
        ]
        for d in search_dirs:
            if not os.path.exists(d):
                continue
            for pat in patterns:
                for ext in extensions:
                    p = os.path.join(d, f"{pat}{ext}")
                    if os.path.exists(p):
                        return p
        return ""

    def _switch_model(self, model_name: str):
        """Đổi model ROV (kế thừa → thông số vật lý thay đổi)."""
        model_name = model_name.strip()
        if model_name not in ROV_MODELS:
            return
        self._current_model_name = model_name

        # Tạo model mới
        model_cls = ROV_MODELS[model_name]
        self._rov_model = model_cls()

        # Tạo lại physics engine
        if self._physics is not None:
            self._physics.close()
        self._physics = PhysicsEngine(self._rov_model)

        # Tự động quét tìm file CAD mô hình 3D trong thư mục dự án
        cad_file = self.find_cad_file(model_name) or self.settings.get("cad_file", "") or None

        # Cập nhật các 3D widget
        self.gl_3d.set_model(self._rov_model, cad_file)
        self.compass_3d.set_model(self._rov_model, cad_file)

        # Cập nhật số thruster trên power widget
        self.power_widget.set_n_thrusters(self._rov_model.num_thrusters())

        print(f"[ROV] Model changed -> {self._rov_model.DISPLAY_NAME}")

    # ----------------------------------------------------------
    # KHỞI ĐỘNG THREADS
    # ----------------------------------------------------------
    def _start_workers(self):
        """Khởi động MAVLink và SLAM UDP receiver threads."""
        # MAVLink Worker
        conn = self.settings.get("connection", "udp:0.0.0.0:14550")
        self._mav_worker = MAVLinkWorker(connection_string=conn)
        # Kết nối tất cả signals
        self._mav_worker.sig_connected.connect(self._on_connected)
        self._mav_worker.sig_link_quality.connect(self._on_link_quality)
        self._mav_worker.sig_heartbeat.connect(self._on_heartbeat)
        self._mav_worker.sig_attitude.connect(self._on_attitude)
        self._mav_worker.sig_position_ned.connect(self._on_position_ned)
        self._mav_worker.sig_vfr_hud.connect(self._on_vfr_hud)
        self._mav_worker.sig_sys_status.connect(self._on_sys_status)
        self._mav_worker.sig_vision_pose.connect(self._on_vision_pose)
        self._mav_worker.sig_named_float.connect(self._on_named_float)
        self._mav_worker.sig_cmd_ack.connect(self._on_cmd_ack)
        self._mav_worker.sig_gps_raw.connect(self._on_gps_raw)
        self._mav_worker.start_worker()

        # SLAM UDP Receiver
        slam_port = self.settings.get("slam_port", 5010)
        self._slam_worker = SLAMUDPReceiver(port=slam_port)
        self._slam_worker.sig_slam_points.connect(self._on_slam_points)
        self._slam_worker.start_worker()

    def _stop_workers(self):
        if self._mav_worker:
            self._mav_worker.stop_worker()
        if self._slam_worker:
            self._slam_worker.stop_worker()

    # ----------------------------------------------------------
    # VÒNG LẶP CHÍNH 60 FPS
    # ----------------------------------------------------------
    def _on_frame(self):
        """Gọi mỗi 16ms: bước vật lý + cập nhật tất cả widget."""
        if self._physics is None:
            return

        # 1. Cập nhật các nút nhấn từ bàn phím mượt mà liên tục
        self._update_keyboard_controls()

        # Áp dụng bộ lọc thông thấp (low-pass filter) làm mượt tín hiệu điều khiển tránh giật động cơ
        alpha = 0.22  # Hệ số làm mượt
        for k in self._ctrl:
            self._smoothed_ctrl[k] = self._smoothed_ctrl[k] * (1 - alpha) + self._ctrl[k] * alpha

        # 2. Áp điều khiển đã được làm mượt
        if not self._connected:
            self._physics.set_control(**self._smoothed_ctrl)
        else:
            # Gửi lệnh điều khiển đã được làm mượt qua MAVLink
            self._send_mavlink_control()

        # 3. Bước vật lý (4 sub-steps cho ổn định)
        state = None
        dt = 1 / 240.0
        for _ in range(4):
            state = self._physics.step(dt)

        if state is None:
            return

        pos  = state["position"]
        quat = state["orientation_quat"]  # [qx, qy, qz, qw]

        # 4. Nếu đang kết nối, dùng dữ liệu MAVLink thay cho physics
        if self._connected:
            pos  = self._pos_ned
            # Chuyển Euler → Quaternion
            quat = self._euler_to_quat(self._roll, self._pitch, self._yaw)

        # 5. Cập nhật 3D widget
        self.gl_3d.update_pose(pos, quat)

        # 6. Cập nhật trajectory
        if not self._origin_set and np.any(pos != 0):
            self.gl_3d.set_origin(pos)
            self._origin_set = True
        self.gl_3d.update_trajectory(pos[0], pos[1], pos[2])

        # 7. Cập nhật FOV effect
        self.gl_3d.update_fov_effect(self._heading)

        # 8. Cập nhật la bàn 3D (Compass 3D) và Radar Point Cloud
        vel = self._vel_ned if self._connected else state["linear_velocity"]
        self.compass_3d.update_state(quat, vel)

        # 9. Cập nhật Power widget
        if self._connected:
            loads = [abs(v) for v in state.get("thruster_pct", [])]
            loads_norm = [t / 100.0 for t in loads]
        else:
            loads_norm = [abs(v) for v in self._physics._thruster_inputs]
        self.power_widget.set_thruster_loads(loads_norm)
        self.power_widget.set_battery(self._voltage, self._current)

        # 10. Cập nhật label trên header
        self._update_header_labels()

        # 11. Ghi log hoạt động CSV định kỳ (1 Hz)
        self._log_to_csv()

    # ----------------------------------------------------------
    # MAVLINK SIGNAL HANDLERS
    # ----------------------------------------------------------
    def _on_connected(self, connected: bool):
        self._connected = connected
        if connected and not self._origin_set:
            # Kích hoạt physics inject khi nhận pose đầu tiên
            pass
        color = "#00FF66" if connected else "#FF4040"
        text  = "STRONG" if connected else "DISCONNECTED"
        self.ui.lbl_connection_value.setStyleSheet(f"color:{color};font-weight:bold;")
        self.ui.lbl_connection_value.setText(text)
        # Bật inject external pose nếu kết nối
        if self._physics:
            if not connected:
                self._physics.disable_external_pose()

    def _on_link_quality(self, pct: int):
        self._link_quality = pct

    def _on_heartbeat(self, mode: str, status: str):
        self._flight_mode = mode
        self._sys_status  = status
        self.ui.lbl_mode_value.setText(mode)
        self.ui.lbl_status_value.setText(status)

    def _on_attitude(self, roll: float, pitch: float, yaw: float):
        """Nhận ATTITUDE từ MAVLink (rad)."""
        self._roll  = roll
        self._pitch = pitch
        self._yaw   = yaw
        self._heading = math.degrees(yaw) % 360.0

    def _on_position_ned(self, x, y, z, vx, vy, vz):
        """Nhận LOCAL_POSITION_NED (SLAM fused position)."""
        self._pos_ned = np.array([x, y, z])
        self._vel_ned = np.array([vx, vy, vz])
        # Inject vào physics để đồng bộ
        if self._physics and self._connected:
            quat = self._euler_to_quat(self._roll, self._pitch, self._yaw)
            self._physics.set_external_pose([x, y, z], quat.tolist())
            if not self._origin_set:
                self.gl_3d.set_origin(np.array([x, y, z]))
                self._origin_set = True

    def _on_vfr_hud(self, depth: float, heading: float, throttle: float):
        self._depth    = depth
        self._heading  = heading
        self._throttle = throttle

    def _on_sys_status(self, volt: float, curr: float, remain: int):
        self._voltage = volt
        self._current = curr

    def _on_vision_pose(self, x, y, z, roll, pitch, yaw):
        """Raw SLAM pose — vẽ quỹ đạo riêng nếu muốn."""
        pass  # Có thể vẽ thêm trajectory riêng cho raw SLAM

    def _on_gps_raw(self, lat: float, lon: float):
        """Tự động đồng bộ/hiệu chuẩn vị trí trạm GCS từ tín hiệu GPS thực của ROV."""
        # Ngay khi ROV có GPS hoặc nhận tọa độ xuất phát từ Pixhawk
        # Ta suy ngược vị trí trạm GCS bằng cách trừ đi dịch chuyển SLAM hiện tại
        lat_offset = self._pos_ned[0] / 111111.0
        lng_offset = self._pos_ned[1] / (111111.0 * math.cos(math.radians(lat)))
        
        self.settings["gcs_lat"] = lat - lat_offset
        self.settings["gcs_lng"] = lon - lng_offset

    def _on_named_float(self, name: str, value: float):
        """Cập nhật bảng cảm biến ngoại vi."""
        self._named_sensors[name] = value
        self._update_telemetry_named(name, value)

    def _on_cmd_ack(self, command: int, result: int):
        result_str = {0: "OK", 1: "FAILED", 4: "DENIED"}.get(result, str(result))
        print(f"[MAVLink] CMD ACK: command={command} result={result_str}")

    def _on_slam_points(self, pts: np.ndarray):
        """Nhận point cloud từ SLAM UDP thread."""
        self.gl_3d.update_slam_points(pts)
        self.compass_3d.update_slam_points(pts)

    # ----------------------------------------------------------
    # CONTROL
    # ----------------------------------------------------------
    def _set_ctrl(self, surge=None, sway=None, heave=None,
                  roll=None, pitch=None, yaw=None):
        if surge is not None: self._ctrl["surge"] = surge
        if sway  is not None: self._ctrl["sway"]  = sway
        if heave is not None: self._ctrl["heave"] = heave
        if roll  is not None: self._ctrl["roll"]  = roll
        if pitch is not None: self._ctrl["pitch"] = pitch
        if yaw   is not None: self._ctrl["yaw"]   = yaw
        # Gửi lệnh MAVLink khi kết nối
        if self._connected and self._mav_worker:
            self._send_mavlink_control()

    def _send_mavlink_control(self):
        """Chuyển đổi ctrl [-1,1] → MANUAL_CONTROL [-1000, 1000]."""
        x = int(self._ctrl["surge"] * 1000)
        y = int(self._ctrl["sway"]  * 1000)
        z = int((self._ctrl["heave"] + 1.0) * 500)   # 0-1000, 500=neutral
        r = int(self._ctrl["yaw"]   * 1000)
        self._mav_worker.send_manual_control(x, y, z, r, 0)

    def _emergency_stop(self):
        self._ctrl = dict(surge=0., sway=0., heave=0.,
                          roll=0., pitch=0., yaw=0.)
        if self._connected and self._mav_worker:
            self._mav_worker.send_manual_control(0, 0, 500, 0, 0)

    def _speed_up(self):
        self._speed_scale = min(1.0, self._speed_scale + 0.25)
        self.ui.lbl_control_speed_number.setText(
            str(int(self._speed_scale * 1000)))

    def _speed_down(self):
        self._speed_scale = max(0.25, self._speed_scale - 0.25)
        self.ui.lbl_control_speed_number.setText(
            str(int(self._speed_scale * 1000)))

    def _toggle_led(self):
        pass  # TODO: kết nối với MAVLink send_lights()

    def _mav_lights(self, brighter: bool):
        if self._mav_worker:
            self._mav_worker.send_lights(100 if brighter else 0)

    def _toggle_arm(self):
        """ARM/DISARM toggle."""
        if self._mav_worker and self._connected:
            # TODO: track armed state
            self._mav_worker.send_arm(True)

    # ----------------------------------------------------------
    # SETTINGS DIALOG
    # ----------------------------------------------------------
    def _open_settings(self):
        dlg = SettingsDialog(self.settings, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.settings.update(dlg.settings)
            # Áp dụng cài đặt mới
            self._stop_workers()
            self._start_workers()
            # Cập nhật lại mô hình 3D (tự động load CAD nếu có)
            cad_file = self.find_cad_file(self._current_model_name)
            self.gl_3d.set_model(self._rov_model, cad_file)
            self.compass_3d.set_model(self._rov_model, cad_file)
            print(f"[Settings] Saved: {self.settings}")

    # ----------------------------------------------------------
    # TELEMETRY TABLE
    # ----------------------------------------------------------
    def _setup_telemetry_table(self):
        """Cấu hình bảng TELEMETRY DATA (dùng self._telem_table đã inject)."""
        table = self._telem_table
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(["Sensor", "Value", "Unit"])
        table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        table.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        table.setStyleSheet("""
            QTableWidget { background:#060B14; color:#A0B2C6;
                           alternate-background-color:#0A1422;
                           gridline-color:#1E3550;
                           border: none; }
            QHeaderView::section { background:#0D1726; color:#5B748E;
                                   border:1px solid #1E3550;
                                   font-size:9px; font-weight:bold;
                                   letter-spacing:1px; padding:3px; }
            QTableWidget::item { padding:2px 4px; }
            QTableWidget::item:selected { background:rgba(0,168,255,0.15); }
        """)
        # Các hàng cố định
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
            name_item = QTableWidgetItem(name)
            name_item.setForeground(QtGui.QBrush(QtGui.QColor(91, 116, 142)))
            table.setItem(row, 0, name_item)
            
            if key == "GPS_MAP":
                val_item = QTableWidgetItem("Click to view Map")
                # Vẽ chữ gạch chân màu xanh liên kết
                font = QtGui.QFont()
                font.setUnderline(True)
                val_item.setFont(font)
                val_item.setForeground(QtGui.QBrush(QtGui.QColor(0, 168, 255)))
            else:
                val_item = QTableWidgetItem("—")
                val_item.setForeground(QtGui.QBrush(QtGui.QColor(0, 168, 255)))
                
            table.setItem(row, 1, val_item)
            unit_item = QTableWidgetItem(unit)
            unit_item.setForeground(QtGui.QBrush(QtGui.QColor(91, 116, 142)))
            table.setItem(row, 2, unit_item)
            self._telem_items[key] = val_item

        # Kết nối sự kiện click ô để mở bản đồ
        table.cellClicked.connect(self._on_table_cell_clicked)

    def _on_table_cell_clicked(self, row, column):
        """Mở Google Maps trỏ đúng tọa độ ROV khi click vào hàng tương ứng."""
        table = self._telem_table
        if table.item(row, 0) and table.item(row, 0).text() == "GPS Map Link":
            gcs_lat = float(self.settings.get("gcs_lat", 21.0285))
            gcs_lng = float(self.settings.get("gcs_lng", 105.8542))
            
            # Quy đổi hệ tọa độ NED (m) sang GPS Latitude/Longitude offset
            # 1 độ vĩ độ = ~111,111 mét
            lat_offset = self._pos_ned[0] / 111111.0
            # 1 độ kinh độ = ~111,111 * cos(latitude) mét
            lng_offset = self._pos_ned[1] / (111111.0 * math.cos(math.radians(gcs_lat)))
            
            rov_lat = gcs_lat + lat_offset
            rov_lng = gcs_lng + lng_offset
            
            url = f"https://www.google.com/maps/search/?api=1&query={rov_lat},{rov_lng}"
            QtGui.QDesktopServices.openUrl(QtCore.QUrl(url))

    def _update_telemetry_table(self):
        """Cập nhật giá trị trong bảng telemetry."""
        data = {
            "ROLL":     f"{math.degrees(self._roll):+.1f}",
            "PITCH":    f"{math.degrees(self._pitch):+.1f}",
            "YAW":      f"{math.degrees(self._yaw):+.1f}",
            "DEPTH":    f"{self._depth:.2f}",
            "HEADING":  f"{self._heading:.1f}",
            "VOLTAGE":  f"{self._voltage:.2f}",
            "CURRENT":  f"{self._current:.2f}",
            "VEL_X":    f"{self._vel_ned[0]:.2f}",
            "VEL_Y":    f"{self._vel_ned[1]:.2f}",
            "VEL_Z":    f"{self._vel_ned[2]:.2f}",
            "THROTTLE": f"{self._throttle:.0f}",
        }
        for key, val_str in data.items():
            if key in self._telem_items:
                self._telem_items[key].setText(val_str)

    def _update_telemetry_named(self, name: str, value: float):
        """Thêm cảm biến NAMED_VALUE_FLOAT vào bảng."""
        table = self._telem_table
        # Tìm hàng đã có tên này chưa
        for row in range(table.rowCount()):
            if table.item(row, 0) and table.item(row, 0).text() == name:
                table.item(row, 1).setText(f"{value:.4f}")
                return
        # Thêm hàng mới
        row = table.rowCount()
        table.setRowCount(row + 1)
        name_item = QTableWidgetItem(name)
        name_item.setForeground(QtGui.QBrush(QtGui.QColor(0, 200, 100)))
        table.setItem(row, 0, name_item)
        val_item = QTableWidgetItem(f"{value:.4f}")
        val_item.setForeground(QtGui.QBrush(QtGui.QColor(0, 255, 150)))
        table.setItem(row, 1, val_item)
        table.setItem(row, 2, QTableWidgetItem(""))

    # ----------------------------------------------------------
    # HEADER LABELS CẬP NHẬT
    # ----------------------------------------------------------
    def _update_header_labels(self):
        """Cập nhật các label trên header bar."""
        # Chỉ cập nhật telemetry table mỗi 10 frames (~6 Hz)
        if not hasattr(self, '_telem_update_cnt'):
            self._telem_update_cnt = 0
        self._telem_update_cnt += 1
        if self._telem_update_cnt >= 10:
            self._telem_update_cnt = 0
            self._update_telemetry_table()

        # Link quality bar (thêm vào nhãn connection)
        q = self._link_quality
        if q > 70:
            qcolor = "#00FF66"
        elif q > 40:
            qcolor = "#FFD700"
        else:
            qcolor = "#FF4040"
        if self._connected:
            self.ui.lbl_connection_value.setStyleSheet(
                f"color:{qcolor};font-weight:bold;")
            self.ui.lbl_connection_value.setText(f"ONLINE {q}%")

    def _update_clock(self):
        """Cập nhật đồng hồ và ngày tháng trên header."""
        from datetime import datetime
        try:
            import zoneinfo
            tz_name = self.settings.get("timezone", "Asia/Ho_Chi_Minh")
            tz = zoneinfo.ZoneInfo(tz_name)
            now = datetime.now(tz=tz)
        except Exception:
            now = datetime.now()
        self.ui.lbl_time.setText(now.strftime("%H:%M:%S"))
        self.ui.lbl_date.setText(now.strftime("VN %Y/%m/%d"))

    # ----------------------------------------------------------
    # TIỆN ÍCH
    # ----------------------------------------------------------
    @staticmethod
    def _euler_to_quat(roll: float, pitch: float, yaw: float) -> np.ndarray:
        """Chuyển Euler ZYX (rad) → Quaternion [qx, qy, qz, qw]."""
        cr, cp, cy = math.cos(roll/2),  math.cos(pitch/2), math.cos(yaw/2)
        sr, sp, sy = math.sin(roll/2),  math.sin(pitch/2), math.sin(yaw/2)
        qw = cr*cp*cy + sr*sp*sy
        qx = sr*cp*cy - cr*sp*sy
        qy = cr*sp*cy + sr*cp*sy
        qz = cr*cp*sy - sr*sp*cy
        return np.array([qx, qy, qz, qw])

    # ----------------------------------------------------------
    # KEYBOARD (khi không có InputHandler)
    # ----------------------------------------------------------
    def _update_keyboard_controls(self):
        """Đọc trạng thái các phím đang được giữ liên tục và cập nhật lực đẩy."""
        sp = self._speed_scale
        surge = 0.0
        sway = 0.0
        heave = 0.0
        yaw = 0.0

        # Ánh xạ phím động từ cài đặt
        key_fwd  = KEY_MAP.get(self.settings.get("key_forward", "W"), Qt.Key.Key_W)
        key_bwd  = KEY_MAP.get(self.settings.get("key_backward", "S"), Qt.Key.Key_S)
        key_left = KEY_MAP.get(self.settings.get("key_left", "A"), Qt.Key.Key_A)
        key_right= KEY_MAP.get(self.settings.get("key_right", "D"), Qt.Key.Key_D)
        key_sw_l = KEY_MAP.get(self.settings.get("key_sway_left", "Q"), Qt.Key.Key_Q)
        key_sw_r = KEY_MAP.get(self.settings.get("key_sway_right", "E"), Qt.Key.Key_E)
        key_asc  = KEY_MAP.get(self.settings.get("key_ascend", "R"), Qt.Key.Key_R)
        key_desc = KEY_MAP.get(self.settings.get("key_descend", "F"), Qt.Key.Key_F)

        if key_fwd in self._pressed_keys:   surge += sp
        if key_bwd in self._pressed_keys:   surge -= sp
        if key_sw_l in self._pressed_keys:  sway -= sp
        if key_sw_r in self._pressed_keys:  sway += sp
        if key_asc in self._pressed_keys:   heave += sp
        if key_desc in self._pressed_keys:  heave -= sp
        if key_left in self._pressed_keys:  yaw -= sp
        if key_right in self._pressed_keys: yaw += sp

        self._set_ctrl(surge=surge, sway=sway, heave=heave, yaw=yaw)

    def _log_to_csv(self):
        """Ghi dữ liệu telemetry định kỳ 1Hz vào file CSV được cấu hình."""
        now = time.time()
        if not hasattr(self, '_last_csv_log_time'):
            self._last_csv_log_time = 0.0
        if now - self._last_csv_log_time < 1.0:
            return
        self._last_csv_log_time = now

        csv_path = self.settings.get("csv_log_path", "logs/rov_activity.csv")
        try:
            # Tự động tạo thư mục chứa nếu chưa có
            dir_name = os.path.dirname(os.path.abspath(csv_path))
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)

            import csv
            file_exists = os.path.exists(csv_path)
            with open(csv_path, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow([
                        "Timestamp", "Time", "Flight Mode", "System Status",
                        "Roll (deg)", "Pitch (deg)", "Yaw (deg)", "Depth (m)", "Heading (deg)",
                        "Voltage (V)", "Current (A)", "X (m)", "Y (m)", "Z (m)"
                    ])
                
                from datetime import datetime
                time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                writer.writerow([
                    time.time(), time_str, self._flight_mode, self._sys_status,
                    math.degrees(self._roll), math.degrees(self._pitch), math.degrees(self._yaw),
                    self._depth, self._heading, self._voltage, self._current,
                    self._pos_ned[0], self._pos_ned[1], self._pos_ned[2]
                ])
        except Exception as e:
            # Ghi lỗi ra màn hình debug nếu cần
            pass

    def keyPressEvent(self, event: QtGui.QKeyEvent):
        key = event.key()
        if key == Qt.Key.Key_Space:
            self._emergency_stop()
            self._pressed_keys.clear()
        else:
            self._pressed_keys.add(key)
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QtGui.QKeyEvent):
        key = event.key()
        if key in self._pressed_keys:
            self._pressed_keys.remove(key)
        super().keyReleaseEvent(event)

    # ----------------------------------------------------------
    # ĐÓNG ỨNG DỤNG
    # ----------------------------------------------------------
    def closeEvent(self, event):
        self._frame_timer.stop()
        self._clock_timer.stop()
        self._stop_workers()
        if self._physics:
            self._physics.close()
        event.accept()


# ==============================================================
# ENTRY POINT
# ==============================================================
def parse_args():
    parser = argparse.ArgumentParser(description="GCS ROV Control System")
    parser.add_argument(
        "--connection", default="udp:0.0.0.0:14550",
        help="MAVLink connection string (default: udp:0.0.0.0:14550)"
    )
    parser.add_argument(
        "--slam-port", type=int, default=5010,
        help="SLAM UDP port (default: 5010)"
    )
    parser.add_argument(
        "--cad", default="",
        help="Path to CAD model file (.stl/.obj)"
    )
    parser.add_argument(
        "--mock", action="store_true",
        help="Force mock/offline mode"
    )
    return parser.parse_args()


def main():
    args = parse_args()

    settings = {
        "connection":    args.connection,
        "slam_port":     args.slam_port,
        "cad_file":      args.cad,
        "timezone":      "Asia/Ho_Chi_Minh",
        "blackbox_path": "logs",
        "csv_log_path":  "logs/rov_activity.csv",
        "mock_mode":     args.mock,
        "gcs_lat":       21.0285,
        "gcs_lng":       105.8542,
        "key_forward":   "W",
        "key_backward":  "S",
        "key_left":      "A",
        "key_right":     "D",
        "key_sway_left": "Q",
        "key_sway_right":"E",
        "key_ascend":    "R",
        "key_descend":   "F",
        "enable_imu_gamepad": False,
        "rth_depth":     2.0,
        "heartbeat_hz":  1,
        "auto_reset_origin": True
    }

    app = QApplication(sys.argv)
    app.setApplicationName("E3 LAB ROV GCS")

    # Load stylesheet nếu có
    qss_path = os.path.join(PROJECT_ROOT, "GUI", "style.qss")
    if os.path.exists(qss_path):
        with open(qss_path, 'r', encoding='utf-8') as f:
            app.setStyleSheet(f.read())

    window = ROVMainWindow(settings)
    window.setWindowTitle("E3 LAB — ROV CONTROL SYSTEM v1.0")
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()