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
from GUI.widgets.settings_dialog import SettingsDialog
from network.slam_udp_receiver import SLAMUDPReceiver
from network.mavlink_worker import MAVLinkWorker
from GUI.widgets.power_widget import PowerWidget
from GUI.widgets.gl_compass_3d_widget import GLCompass3DWidget
from GUI.widgets.gl_3d_widget import GLROVWidget
from GUI.widgets.blueos_manager import BlueOSManagerWindow
from database import DatabaseManager, AsyncTelemetryLogger, ReportExporter
from core.physics_engine import PhysicsEngine
from core.models.rov_3thruster import ROV3ThrusterModel
from core.models.rov_6thruster import ROV6ThrusterModel
from GUI.guirov import Ui_MainWindow
import sys
import math
import time
import argparse
import numpy as np
import os
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout,
    QWidget, QFileDialog, QDialog, QFormLayout, QLineEdit,
    QDialogButtonBox, QComboBox, QLabel, QSpinBox, QDoubleSpinBox,
    QCheckBox, QTableWidget, QTableWidgetItem, QHeaderView, QSplitter,
    QTabWidget
)
from PyQt6.QtGui import QIcon, QPixmap

# --- Bản đồ phím bàn phím ---
KEY_MAP = {
    "W": Qt.Key.Key_W, "S": Qt.Key.Key_S, "A": Qt.Key.Key_A, "D": Qt.Key.Key_D,
    "Q": Qt.Key.Key_Q, "E": Qt.Key.Key_E, "R": Qt.Key.Key_R, "F": Qt.Key.Key_F,
    "I": Qt.Key.Key_I, "K": Qt.Key.Key_K, "J": Qt.Key.Key_J, "L": Qt.Key.Key_L,
    "U": Qt.Key.Key_U, "O": Qt.Key.Key_O,
    "Up": Qt.Key.Key_Up, "Down": Qt.Key.Key_Down, "Left": Qt.Key.Key_Left, "Right": Qt.Key.Key_Right
}

# --- Import GUI layout ---
# Thêm thư mục gốc dự án vào path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'GUI'))


# --- Import các module tự viết ---

# Thử import input handler nếu có
try:
    from GUI.input_handler import InputHandler
    HAS_INPUT = True
except ImportError:
    HAS_INPUT = False

# ── Feature 1: AR HUD + Video ────────────────────────────────────
try:
    from GUI.widgets.ar_hud_widget import ARHUDWidget
    from network.video_receiver import VideoReceiver, VideoSource
    HAS_VIDEO = True
except ImportError:
    HAS_VIDEO = False

# ── Feature 2: AI Vision ──────────────────────────────────────────
try:
    from GUI.widgets.ai_vision_processor import AIVisionProcessor
    from GUI.widgets.ai_control_panel import AIControlPanel
    HAS_AI = True
except ImportError:
    HAS_AI = False

# ── Feature 2.5: Offline 100% Voice Co-Pilot Agent ─────────────────
try:
    from AI.ipc_bus import IPCBus
    from AI.cv_engine import SubseaCVEngine, fine_tune_yolov11
    from AI.vad_worker import VADWorker
    from AI.stt_worker import STTWorker
    from AI.agent_brain import ROVAgentBrain
    from AI.tts_worker import TTSWorker
    HAS_VOICE_AGENT = True
except ImportError as _err:
    print(f"[Main] Voice Agent import warning: {_err}")
    HAS_VOICE_AGENT = False

# ── Feature 3: Mission Planner ────────────────────────────────────
try:
    from GUI.widgets.mission_planner import MissionPlanner
    HAS_MISSION = True
except ImportError:
    HAS_MISSION = False

# ── Feature 4: Seafloor Mesh ──────────────────────────────────────
try:
    from core.seafloor_mapper import SeafloorMapper
    from GUI.widgets.seafloor_mesh_widget import SeafloorMeshWidget
    HAS_SEAFLOOR = True
except ImportError:
    HAS_SEAFLOOR = False

# ── Feature 5: Diagnostics Engine ────────────────────────────────
try:
    from core.diagnostics_engine import DiagnosticsEngine
    HAS_DIAG = True
except ImportError:
    HAS_DIAG = False

# ── Notification System ─────────────────────────────────────
try:
    from GUI.widgets.notification_manager import NotificationManager
    HAS_NOTIF = True
except ImportError:
    HAS_NOTIF = False


# ==============================================================
# CÁC MODEL ROV HỖ TRỢ
# ==============================================================
ROV_MODELS = {
    "3DC": ROV3ThrusterModel,
    "6DC": ROV6ThrusterModel,
}


# ==============================================================
class AgentAsyncWorker(QtCore.QThread):
    """Worker QThread running Whisper STT & Agent Brain LLM off the Qt GUI main thread."""
    sig_result_ready = QtCore.pyqtSignal(object, object, str)  # (output, immediate_action, cmd_text)

    def __init__(self, agent_brain, text: str, pcm_audio, stt_worker, telemetry: dict, is_ptt: bool = False, parent=None):
        super().__init__(parent)
        self._brain = agent_brain
        self._text = text
        self._pcm_audio = pcm_audio
        self._stt_worker = stt_worker
        self._telemetry = telemetry
        self._is_ptt = is_ptt

    def run(self):
        try:
            cmd_text = self._text
            if not cmd_text and self._pcm_audio is not None and self._stt_worker:
                print(f"[AgentAsyncWorker] Transcribing audio buffer ({len(self._pcm_audio)} samples)...")
                cmd_text = self._stt_worker.transcribe_audio(self._pcm_audio)
                print(f"[AgentAsyncWorker] Transcribed text: '{cmd_text}'")

            if cmd_text and self._brain:
                output, immediate_action = self._brain.process_pilot_input(cmd_text, self._telemetry, is_ptt=self._is_ptt)
                self.sig_result_ready.emit(output, immediate_action, cmd_text)
            else:
                self.sig_result_ready.emit(None, None, "")
        except Exception as exc:
            print(f"[AgentAsyncWorker] Error during async processing: {exc}")
            self.sig_result_ready.emit(None, None, "")


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
        # Tự động lấy đường dẫn tuyệt đối một cách an toàn
        current_dir = os.path.dirname(os.path.abspath(__file__))
        logo_path = os.path.join(current_dir, "GUI", "img", "logocompany.jpg")

        self.ui.pbtn_iconheader.setIcon(QIcon(logo_path))
        self.ui.pbtn_iconheader.setIconSize(QtCore.QSize(45, 45))
        # Logo Phần mềm thanh Taskbar
        logotaskbar_path = os.path.join(current_dir, "GUI", "img", "logodesktop.png")
        self.setWindowIcon(QIcon(logotaskbar_path))

        self.ui.pbtn_iconheader.setIcon(QIcon(logo_path))
        self.ui.pbtn_iconheader.setIconSize(QtCore.QSize(45, 45))
        # --- Trạng thái ---
        self._current_model_name = "3DC"
        self._rov_model = None
        self._physics = None
        self._mav_worker = None
        self._slam_worker = None
        self._input_hdlr = None
        self._origin_set = False

        # ══════════════════════════════════════════════════════
        # POLLING MODEL: Dữ liệu telemetry được buffer ở đây.
        # Các signal handler từ MAVLink CHỈ ghi vào biến này.
        # _on_frame() là NƠI DUY NHẤT đọc và cập nhật widget.
        # Điều này tách rời hoàn toàn luồng nhận (network)
        # khỏi luồng vẽ (GUI), loại bỏ giật lag.
        # ══════════════════════════════════════════════════════
        self._roll = 0.0   # rad
        self._pitch = 0.0
        self._yaw = 0.0
        self._depth = 0.0   # m
        self._heading = 0.0   # deg
        self._pos_ned = np.zeros(3)
        self._vel_ned = np.zeros(3)
        self._voltage = 16.8
        self._current = 0.0
        self._throttle = 0.0
        self._flight_mode = "MANUAL"
        self._sys_status = "ACTIVE"
        self._connected = False
        self._link_quality = 0

        # Dirty flags — đánh dấu dữ liệu mới từ MAVLink chưa render
        self._dirty_attitude = False
        self._dirty_position = False
        self._dirty_battery = False
        self._dirty_heartbeat = False
        # Frame counter cho throttling các tác vụ nặng
        self._frame_count = 0

        # Telemetry table data
        self._named_sensors: dict = {}

        # Control inputs (keyboard/gamepad)
        self._ctrl = dict(surge=0., sway=0., heave=0.,
                          roll=0., pitch=0., yaw=0.)
        self._speed_scale = 1.0  # 0.25 / 0.5 / 0.75 / 1.0

        # Biến điều khiển làm mượt và phím đang nhấn
        self._smoothed_ctrl = dict(
            surge=0., sway=0., heave=0., roll=0., pitch=0., yaw=0.)
        self._pressed_keys = set()

        # ── Handles cho 5 features nâng cao ──
        self._video_rx:    object = None
        self._ar_hud:      object = None
        self._ai_proc:     object = None
        self._ai_panel:    object = None
        self._ipc_bus:     object = None
        self._agent_brain: object = None
        self._vad_worker:  object = None
        self._stt_worker:  object = None
        self._tts_worker:  object = None
        self._mission_planner: object = None
        self._seafloor_mapper: object = None
        self._seafloor_mesh:   object = None
        self._diagnostics: object = None
        self._auto_track_gain: float = 0.3
        # ── Camera / Recording ──
        self._is_recording:   bool = False
        self._video_writer:   object = None   # cv2.VideoWriter
        self._last_frame:     object = None   # np.ndarray, cập nhật mỗi frame

        # ── SQLite Database & High-Frequency Telemetry Black Box Logger ──
        self.db = DatabaseManager()
        self.active_session_id = self.db.create_dive_session(
            pilot_name="Pilot Operator",
            location_name=self.settings.get("location_name", "Offshore Subsea Facility")
        )
        self.telemetry_logger = AsyncTelemetryLogger(db_manager=self.db)
        self.telemetry_logger.start(session_id=self.active_session_id)

        # --- Thay thế placeholder widgets ---
        self._inject_3d_widget()
        self._inject_power_widget()
        self._inject_slam_radar()
        self._inject_advanced_features()  # ← 5 features nâng cao

        # --- Kết nối signal/slot của UI gốc ---
        # Chặn signal trước để tránh currentTextChanged bắn sớm
        self.ui.cb_mission.blockSignals(True)
        # Set combobox về 3DC (index 0 theo guirov.py: 0="3DC", 1="6DC")
        idx = self.ui.cb_mission.findText("3DC")
        if idx >= 0:
            self.ui.cb_mission.setCurrentIndex(idx)
        self.ui.cb_mission.blockSignals(False)

        self._connect_ui_signals()

        # --- Khởi tạo model ROV ---
        self._switch_model("3DC")

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

        # Tự động mở 100% toàn màn hình khi khởi chạy
        self.showMaximized()

        # ── Toast Notification Manager ──────────────────────────
        if HAS_NOTIF:
            self._notifier = NotificationManager(parent=self)
        else:
            self._notifier = None

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

        # ── Feature 4: Seafloor Mesh (song song với compass) ──
        if HAS_SEAFLOOR:
            self._seafloor_mesh = SeafloorMeshWidget(parent=parent)
            layout.addWidget(self._seafloor_mesh)
            # Splitter để resize 2 widget
            layout.setStretch(0, 1)  # compass_3d
            layout.setStretch(1, 1)  # seafloor_mesh

    def _inject_advanced_features(self):
        """
        Khởi tạo và kết nối 5 tính năng nâng cao.
        Được gọi sau _inject_slam_radar().
        """
        # ── Feature 5: Diagnostics Engine ────────────────────────
        if HAS_DIAG:
            self._diagnostics = DiagnosticsEngine(
                capacity_ah=float(self.settings.get(
                    'battery_capacity_ah', 15.6))
            )
            self._diagnostics.sig_alert.connect(self._on_diagnostic_alert)
            self._diagnostics.sig_dive_time.connect(self._on_dive_time_update)

        # ── Feature 4: Seafloor Mapper ───────────────────────────
        if HAS_SEAFLOOR:
            self._seafloor_mapper = SeafloorMapper(
                grid_resolution=0.5,
                max_points=5000,
                grid_size_m=50.0
            )
            if self._seafloor_mesh:
                self._seafloor_mapper.sig_mesh_updated.connect(
                    self._on_seafloor_mesh_updated
                )

        # ── Feature 3: Mission Planner ───────────────────────────
        if HAS_MISSION:
            # Tạo dock widget bên cạnh hoặc tab
            self._mission_planner = MissionPlanner(parent=None)
            self._mission_planner.setWindowTitle("Mission Planner")
            self._mission_planner.setWindowFlags(
                self._mission_planner.windowFlags() |
                QtCore.Qt.WindowType.Window
            )
            # Kết nối signal waypoint từ 3D widget
            if hasattr(self.gl_3d, 'sig_waypoint_placed'):
                self.gl_3d.sig_waypoint_placed.connect(
                    self._mission_planner.add_waypoint_from_3d
                )
            # Preview waypoint trong 3D viewer
            self._mission_planner.sig_preview_waypoint.connect(
                lambda x, y, z: self.gl_3d.update_trajectory(x, y, z)
            )
        # ── Feature: BlueOS Embedded Manager Window ──────────
        self._blueos_window = None

        def _show_blueos_manager():
            blueos_ip = self.settings.get("blueos_ip", "192.168.2.2")
            if self._blueos_window is None:
                self._blueos_window = BlueOSManagerWindow(default_ip=blueos_ip, parent=None)
            self._blueos_window.show()
            self._blueos_window.raise_()
            self._blueos_window.activateWindow()

        self._show_blueos_manager = _show_blueos_manager

        # Thêm nút mở Mission Planner và BlueOS vào toolbar (nếu có)
        if hasattr(self.ui, 'setup_systeam'):
            btn_mp = QtWidgets.QPushButton("📍 Mission", self)
            btn_mp.setStyleSheet(
                "QPushButton{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #142338,stop:1 #0C1827);"
                "color:#00D4FF;border:1px solid #1D3554;border-radius:6px;padding:4px 10px;font-weight:bold;font-size:11px;}"
                "QPushButton:hover{background:#00A8FF;color:#FFFFFF;border-color:#00F0FF;}"
            )
            btn_mp.clicked.connect(self._mission_planner.show)

            btn_blueos = QtWidgets.QPushButton("🌐 BlueOS", self)
            btn_blueos.setStyleSheet(
                "QPushButton{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #142338,stop:1 #0C1827);"
                "color:#00FF9D;border:1px solid #1D3554;border-radius:6px;padding:4px 10px;font-weight:bold;font-size:11px;}"
                "QPushButton:hover{background:#00A8FF;color:#FFFFFF;border-color:#00F0FF;}"
            )
            btn_blueos.clicked.connect(_show_blueos_manager)

            # Chèn vào layout header nếu có
            hdr_layout = self.ui.setup_systeam.parentWidget().layout()
            if hdr_layout:
                idx = hdr_layout.indexOf(self.ui.setup_systeam)
                hdr_layout.insertWidget(idx, btn_mp)
                hdr_layout.insertWidget(idx, btn_blueos)

        # ── Feature 1 & 2: Video Receiver + AR HUD + AI ──────────
        if HAS_VIDEO:
            self._setup_video_pipeline()

    def _setup_video_pipeline(self):
        """Khởi tạo video pipeline: VideoReceiver → ARHUDWidget → AIVisionProcessor."""
        src = self.settings.get('video_source', 'udp_h264')
        udp_port = int(self.settings.get('udp_video_port', 5620))
        rtsp_url = self.settings.get(
            'rtsp_url', 'rtsp://192.168.2.2:8554/video')
        webcam_idx = int(self.settings.get('webcam_index', 0))
        vid_file = self.settings.get('video_file', '')
        fps = int(self.settings.get('video_fps', 30))
        res_str = self.settings.get('video_resolution', '640x480')
        res_parts = res_str.split('x')
        target_w, target_h = (int(res_parts[0]), int(
            res_parts[1])) if len(res_parts) == 2 else (640, 480)

        # Tạo VideoReceiver theo nguồn
        if src == 'udp_h264':
            self._video_rx = VideoReceiver(
                source_type=VideoSource.UDP_H264,
                url_or_index=udp_port,
                target_fps=fps, target_w=target_w, target_h=target_h
            )
        elif src == 'webcam':
            self._video_rx = VideoReceiver(
                source_type=VideoSource.WEBCAM,
                url_or_index=webcam_idx,
                target_fps=fps, target_w=target_w, target_h=target_h
            )
        elif src == 'file':
            self._video_rx = VideoReceiver(
                source_type=VideoSource.FILE,
                url_or_index=vid_file,
                target_fps=fps, target_w=target_w, target_h=target_h
            )
        else:  # rtsp
            self._video_rx = VideoReceiver(
                source_type=VideoSource.RTSP,
                url_or_index=rtsp_url,
                target_fps=fps, target_w=target_w, target_h=target_h
            )

        # ── Embed AR HUD Widget vào khung LIVE CAMERA FEED của GUI chính ──
        if hasattr(self.ui, 'frm_simulate_camera'):
            if hasattr(self.ui, 'opw_camera'):
                self.ui.opw_camera.hide()
            cam_layout = self.ui.verticalLayout_5
            # Tạo AR HUD Widget nhúng trực tiếp vào main GUI
            self._ar_hud = ARHUDWidget(parent=self.ui.frm_simulate_camera)
            self._ar_hud.set_hud_enabled(
                self.settings.get('ar_hud_enabled', True))
            cam_layout.addWidget(self._ar_hud, 1)

            # Đặt lại stretch cho verticalLayout_5:
            # Item 0 (lbl_simulate_camera) = 0, Item 1 (opw_camera) = 0, Item 2 (_ar_hud) = 1
            cam_layout.setStretch(0, 0)
            if cam_layout.count() > 1:
                cam_layout.setStretch(1, 0)
            cam_layout.setStretch(cam_layout.indexOf(self._ar_hud), 1)
        else:
            # Fallback tạo cửa sổ nổi nếu không tìm thấy frm_simulate_camera
            self._ar_hud = ARHUDWidget(parent=None)
            self._ar_hud.setWindowTitle("📹 Live Video + AR HUD")
            self._ar_hud.resize(target_w + 20, target_h + 60)
            self._ar_hud.set_hud_enabled(
                self.settings.get('ar_hud_enabled', True))

        # Kết nối AR HUD Widget Action signals với main window logic
        if self._ar_hud:
            self._ar_hud.sig_snapshot_requested.connect(self._take_snapshot)
            self._ar_hud.sig_record_requested.connect(self._on_camera_button)
            self._ar_hud.sig_popout_requested.connect(
                self._popout_video_window)

        # Kết nối video → HUD + ghi hình
        def _on_frame_received(frame):
            import numpy as _np
            self._last_frame = frame.copy()
            self._ar_hud.set_frame(frame)
            # Ghi video nếu đang recording
            if self._is_recording and self._video_writer is not None:
                try:
                    self._video_writer.write(frame)
                except Exception:
                    pass

        self._video_rx.sig_frame.connect(_on_frame_received)
        self._video_rx.sig_connected.connect(
            lambda ok: print(
                f"[Video] {'Connected' if ok else 'Disconnected'}")
        )
        self._video_rx.sig_error.connect(
            lambda e: print(f"[Video] Error: {e}")
        )

        # AI Vision Processor & Voice Agent (Feature 2 & 2.5)
        if HAS_AI:
            self._setup_ai_pipeline()

        # Thêm nút "📹 Cửa sổ Video" và "🤖 AI Control" vào header thanh công cụ chính
        if hasattr(self.ui, 'setup_systeam'):
            hdr_layout = self.ui.setup_systeam.parentWidget().layout()
            if hdr_layout:
                idx = hdr_layout.indexOf(self.ui.setup_systeam)

                # Nút 1: Cửa sổ Video
                btn_vid = QtWidgets.QPushButton("📹 Cửa sổ Video", self)
                btn_vid.setStyleSheet(
                    "QPushButton{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #0C3322,stop:1 #072015);"
                    "color:#00FF9D;border:1px solid #00FF9D;border-radius:6px;padding:4px 10px;font-weight:bold;font-size:11px;}"
                    "QPushButton:hover{background:#00FF9D;color:#060B14;border-color:#80FFC9;}"
                )
                btn_vid.clicked.connect(self._popout_video_window)
                hdr_layout.insertWidget(idx, btn_vid)

                # Nút 2: AI Control Panel (Voice Agent + YOLO Vision)
                btn_ai = QtWidgets.QPushButton("🤖 AI Control", self)
                btn_ai.setStyleSheet(
                    "QPushButton{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #142E47,stop:1 #0C1E30);"
                    "color:#00E5FF;border:1px solid #00E5FF;border-radius:6px;padding:4px 10px;font-weight:bold;font-size:11px;}"
                    "QPushButton:hover{background:#00E5FF;color:#060B14;border-color:#80FFFF;}"
                )
                btn_ai.clicked.connect(self._show_ai_control_panel)
                hdr_layout.insertWidget(idx, btn_ai)

        self._video_rx.start()

    def _on_quick_video_source_changed(self, index: int):
        """Đổi nhanh nguồn Video trực tiếp từ ComboBox trên GUI chính."""
        if not self._video_rx:
            return
        src_name = ""
        if index == 0:  # Laptop Webcam
            idx = int(self.settings.get('webcam_index', 0))
            self.settings['video_source'] = 'webcam'
            self._video_rx.set_source(VideoSource.WEBCAM, idx)
            src_name = f"Laptop Webcam (Index {idx})"
        elif index == 1:  # ROV UDP Stream
            port = int(self.settings.get('udp_video_port', 5620))
            self.settings['video_source'] = 'udp_h264'
            self._video_rx.set_source(VideoSource.UDP_H264, port)
            src_name = f"ROV UDP Stream (Port {port})"
        elif index == 2:  # RTSP
            url = self.settings.get(
                'rtsp_url', 'rtsp://192.168.2.2:8554/video')
            self.settings['video_source'] = 'rtsp'
            self._video_rx.set_source(VideoSource.RTSP, url)
            src_name = "RTSP Stream"
        elif index == 3:  # File
            import os
            path = self.settings.get('video_file', '')
            # Nếu chưa có file → mở dialog chọn file
            if not path or not os.path.isfile(path):
                path, _ = QtWidgets.QFileDialog.getOpenFileName(
                    self, "Chọn Video File",
                    os.path.expanduser("~"),
                    "Video Files (*.mp4 *.avi *.mkv *.mov *.wmv *.flv);;All Files (*)"
                )
                if not path:
                    # User cancel → quay lại nguồn cũ
                    old_src = self.settings.get('video_source', 'webcam')
                    map_idx = {'webcam': 0, 'udp_h264': 1,
                               'rtsp': 2, 'file': 3}
                    self.cb_quick_vid_src.blockSignals(True)
                    self.cb_quick_vid_src.setCurrentIndex(
                        map_idx.get(old_src, 0))
                    self.cb_quick_vid_src.blockSignals(False)
                    return
                self.settings['video_file'] = path
            self.settings['video_source'] = 'file'
            self._video_rx.set_source(VideoSource.FILE, path)
            src_name = f"Video File ({os.path.basename(path)})"
        print(f"[Video] Switched to {src_name}")
        if hasattr(self, 'power_widget') and self.power_widget:
            self.power_widget.add_log(f"📹 Đổi nguồn video: {src_name}", "INFO")

    def _popout_video_window(self):
        """Mở video ra một cửa sổ riêng biệt nếu người dùng muốn phóng to."""
        if hasattr(self, '_popout_dialog') and self._popout_dialog:
            self._popout_dialog.raise_()
            self._popout_dialog.activateWindow()
            return
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("📹 Live Camera Feed + AR HUD (Cửa sổ lớn)")
        dlg.resize(960, 600)
        lay = QtWidgets.QVBoxLayout(dlg)

        # Nhúng AR HUD copy / view
        hud_standalone = ARHUDWidget(parent=dlg)
        hud_standalone.set_hud_enabled(
            self.settings.get('ar_hud_enabled', True))
        lay.addWidget(hud_standalone)

        # Kết nối frame
        if self._video_rx:
            self._video_rx.sig_frame.connect(hud_standalone.set_frame)
            if self._ai_proc:
                self._ai_proc.sig_detections.connect(
                    hud_standalone.set_detections)

        def _on_close(event):
            if self._video_rx:
                try:
                    self._video_rx.sig_frame.disconnect(
                        hud_standalone.set_frame)
                except Exception:
                    pass
            self._popout_dialog = None
            event.accept()

        dlg.closeEvent = _on_close
        self._popout_dialog = dlg
        dlg.show()

    def _show_ai_control_panel(self):
        """Mở bảng điều khiển AI Control Panel (Voice Agent + YOLO Vision)."""
        if not HAS_AI:
            QtWidgets.QMessageBox.warning(self, "AI Unavailable", "Thư viện AI chưa được cài đặt.")
            return
        if self._ai_panel is None:
            self._setup_ai_pipeline()

        if self._ai_panel:
            self._ai_panel.show()
            self._ai_panel.raise_()
            self._ai_panel.activateWindow()

    def _setup_ai_pipeline(self):
        """Khởi tạo AI detection processor và control panel."""
        if not HAS_AI:
            return
        if self._ai_proc is not None:
            return  # Tránh tạo trùng lặp và lặp signal connection

        model_path = self.settings.get('ai_model_path', 'yolov8n.pt')
        self._ai_proc = AIVisionProcessor(
            model_path=model_path,
            conf=float(self.settings.get('ai_confidence', 0.5)),
            device='cpu'
        )
        # Kết nối: video frame → AI processor
        if self._video_rx:
            self._video_rx.sig_frame.connect(self._ai_proc.submit_frame)
        # Kết nối: detections → AR HUD
        if self._ar_hud:
            self._ai_proc.sig_detections.connect(self._ar_hud.set_detections)
        # Kết nối: track error → MAVLink yaw/pitch offset
        self._ai_proc.sig_track_error.connect(self._on_track_error)
        # AI control panel (cửa sổ nổi)
        self._ai_panel = AIControlPanel(parent=None)
        self._ai_panel.setWindowTitle("🤖 AI Vision Control")
        self._ai_panel.sig_detection_enabled.connect(
            self._on_ai_detection_toggle)
        self._ai_panel.sig_model_changed.connect(self._ai_proc.set_model_path if hasattr(
            self._ai_proc, 'set_model_path') else lambda x: None)
        self._ai_panel.sig_confidence_changed.connect(
            self._ai_proc.set_confidence)
        self._ai_panel.sig_auto_track_enabled.connect(
            self._ai_proc.set_auto_track)
        self._ai_panel.sig_track_class_changed.connect(
            self._ai_proc.set_tracking_target)
        self._ai_panel.sig_track_gain_changed.connect(
            lambda g: setattr(self, '_auto_track_gain', g)
        )
        self._ai_proc.sig_fps.connect(
            lambda fps: self._ai_panel.update_stats(fps, 0, -1)
        )
        self._ai_proc.sig_model_loaded.connect(self._on_ai_model_loaded)
        self._ai_proc.start()

        # Initialize Voice Co-Pilot Agent if available
        if HAS_VOICE_AGENT:
            self._setup_voice_agent_pipeline()

    def _setup_voice_agent_pipeline(self):
        """Khởi tạo Offline 100% Voice Co-Pilot Agent (VAD + STT + SLM + TTS)."""
        if not HAS_VOICE_AGENT or self._agent_brain is not None:
            return

        print("[Main] Initializing Local-First Voice Co-Pilot Agent...")
        try:
            self._ipc_bus = IPCBus()
            self._agent_brain = ROVAgentBrain(sop_json_path="AI/sop_rules.json")
            self._stt_worker = STTWorker(language="vi")
            self._tts_worker = TTSWorker()
            self._vad_worker = VADWorker()

            self._ptt_active = False
            self._wake_word_enabled = True
            self._is_processing_voice = False
            self._is_tts_speaking = False

            # Connect TTS speech started/finished signals to mute mic during TTS audio playback!
            def _on_tts_speech_start(text):
                self._is_tts_speaking = True
                print(f"[Main] TTS audio playback started. Mic capture muted.")

            def _on_tts_speech_finish():
                def _unmute():
                    self._is_tts_speaking = False
                    print(f"[Main] TTS audio playback finished. Mic capture unmuted.")
                QtCore.QTimer.singleShot(300, _unmute)

            self._tts_worker.sig_speech_started.connect(_on_tts_speech_start)
            self._tts_worker.sig_speech_finished.connect(_on_tts_speech_finish)

            # Connect VAD speech end -> Async STT & Agent Brain Worker
            def _on_speech_captured(pcm_audio):
                if pcm_audio is None or len(pcm_audio) < 2400:
                    return
                if getattr(self, '_is_tts_speaking', False):
                    print("[Main] Suppressing mic capture while VIC is speaking to prevent speaker echo feedback.")
                    return
                if getattr(self, '_is_processing_voice', False):
                    print("[Main] Voice worker busy processing previous command. Suppressing concurrent buffer.")
                    return

                print(f"[Main] Captured audio speech clip ({len(pcm_audio)} samples). Dispatching to STT...")
                self._process_pilot_voice_command(text="", pcm_audio=pcm_audio, is_ptt=True)

            self._vad_worker.sig_speech_end.connect(_on_speech_captured)

            # Connect VAD mic status to AI Panel
            if self._ai_panel:
                def _on_vad_status(is_speaking, energy):
                    if getattr(self, '_ptt_active', False):
                        self._ai_panel.lbl_mic_status.setText(f"Mic PTT: 🟢 ĐANG THU ÂM (NHẤN GIỮ)... ({energy:.2f})")
                        self._ai_panel.lbl_mic_status.setStyleSheet("color: #00FF9D; font-weight: bold;")
                    elif getattr(self, '_wake_word_enabled', True):
                        if is_speaking:
                            self._ai_panel.lbl_mic_status.setText(f"Mic VAD: 🟢 Speech Detected ({energy:.2f})")
                            self._ai_panel.lbl_mic_status.setStyleSheet("color: #00FF9D; font-weight: bold;")
                        else:
                            self._ai_panel.lbl_mic_status.setText("Mic VAD: 🟢 Lắng nghe 'Hey VIC' / 'VIC ơi'")
                            self._ai_panel.lbl_mic_status.setStyleSheet("color: #00D4FF; font-weight: bold;")
                    else:
                        self._ai_panel.lbl_mic_status.setText("Mic PTT: 🔒 MUTED (NHẤN NÚT ĐỂ NÓI)")
                        self._ai_panel.lbl_mic_status.setStyleSheet("color: #94A9C4;")

                self._vad_worker.sig_vad_status.connect(_on_vad_status)

                if hasattr(self._ai_panel, 'sig_wake_word_toggled'):
                    def _on_wake_word_toggle(enabled: bool):
                        self._wake_word_enabled = enabled
                        status_str = "🟢 Lắng nghe 'Hey VIC' / 'VIC ơi'" if enabled else "🔒 MUTED (NHẤN NÚT ĐỂ NÓI)"
                        self._ai_panel.lbl_mic_status.setText(f"Mic VAD: {status_str}")
                    self._ai_panel.sig_wake_word_toggled.connect(_on_wake_word_toggle)

                if hasattr(self._ai_panel, 'sig_language_changed'):
                    def _on_language_changed(lang_code: str):
                        print(f"[Main] Switching Voice Agent language to: '{lang_code}'")
                        if self._tts_worker and hasattr(self._tts_worker, 'set_language'):
                            self._tts_worker.set_language(lang_code)
                        if self._stt_worker and hasattr(self._stt_worker, 'set_language'):
                            self._stt_worker.set_language(lang_code)
                        if self._agent_brain and hasattr(self._agent_brain, 'set_language'):
                            self._agent_brain.set_language(lang_code)

                        lang_name = "Tiếng Việt 🇻🇳" if lang_code == "vi" else "English 🇺🇸" if lang_code == "en" else lang_code.upper()
                        self._ai_panel.lbl_agent_speech.setText(f"Agent: Ready ({lang_name})")

                    self._ai_panel.sig_language_changed.connect(_on_language_changed)
                    # Enforce default: Tiếng Việt ("vi")
                    _on_language_changed("vi")

                # Connect UI Safety confirmation buttons, Text command input & Push-To-Talk
                self._ai_panel.btn_confirm_action.clicked.connect(lambda: self._process_pilot_voice_command("Xác nhận"))
                self._ai_panel.btn_cancel_action.clicked.connect(lambda: self._process_pilot_voice_command("Hủy"))
                if hasattr(self._ai_panel, 'sig_voice_command_submitted'):
                    self._ai_panel.sig_voice_command_submitted.connect(self._process_pilot_voice_command)

                if hasattr(self._ai_panel, 'sig_voice_agent_enabled'):
                    def _on_voice_agent_toggle(enabled: bool):
                        self._voice_agent_enabled = enabled
                        if enabled:
                            if self._vad_worker and not self._vad_worker.isRunning():
                                self._vad_worker.start()
                            if self._tts_worker and not self._tts_worker.isRunning():
                                self._tts_worker.start()
                            self._ai_panel.lbl_mic_status.setText("Mic PTT: 🔒 MUTED (NHẤN NÚT ĐỂ NÓI)")
                            self._ai_panel.lbl_mic_status.setStyleSheet("color: #94A9C4;")
                            self._ai_panel.lbl_agent_speech.setText("Agent: Voice Agent ON (Push-To-Talk Ready)")
                            if hasattr(self, 'power_widget') and self.power_widget:
                                self.power_widget.add_log("🎙 Trợ lý Giọng nói đã BẬT (Push-To-Talk)", "SUCCESS")
                        else:
                            if self._vad_worker:
                                self._vad_worker.stop()
                            if self._tts_worker:
                                # Stop and clear speech queue instantly
                                while not self._tts_worker._speech_queue.empty():
                                    try:
                                        self._tts_worker._speech_queue.get_nowait()
                                    except Exception:
                                        break
                            self._ai_panel.lbl_mic_status.setText("Mic PTT: ⏸ DISABLED (TẮT)")
                            self._ai_panel.lbl_mic_status.setStyleSheet("color: #FF5252; font-weight: bold;")
                            self._ai_panel.lbl_agent_speech.setText("Agent: Voice Agent OFF (TẮT)")
                            if hasattr(self, 'power_widget') and self.power_widget:
                                self.power_widget.add_log("⏸ Trợ lý Giọng nói đã TẮT", "WARNING")

                    self._ai_panel.sig_voice_agent_enabled.connect(_on_voice_agent_toggle)

                if hasattr(self._ai_panel, 'sig_ptt_pressed'):
                    def _on_ptt_pressed():
                        if getattr(self, '_voice_agent_enabled', True):
                            self._ptt_active = True
                            self._ai_panel.lbl_mic_status.setText("Mic PTT: 🟢 ĐANG THU ÂM (NHẤN GIỮ)...")
                            self._ai_panel.lbl_mic_status.setStyleSheet("color: #00FF9D; font-weight: bold;")

                    def _on_ptt_released():
                        if getattr(self, '_voice_agent_enabled', True):
                            self._ptt_active = False
                            self._ai_panel.lbl_mic_status.setText("Mic PTT: 🔒 MUTED (NHẤN NÚT ĐỂ NÓI)")
                            self._ai_panel.lbl_mic_status.setStyleSheet("color: #94A9C4;")

                    self._ai_panel.sig_ptt_pressed.connect(_on_ptt_pressed)
                    self._ai_panel.sig_ptt_released.connect(_on_ptt_released)

            # Connect CV Critical Alerts -> Emergency Voice Announcement
            if self._ai_proc and hasattr(self._ai_proc, 'sig_error'):
                def _on_cv_alert(err_text):
                    if "CV CRITICAL ALERT" in err_text:
                        alert_desc = err_text.replace("⚠️ CV CRITICAL ALERT:", "").strip()
                        if self._agent_brain and self._tts_worker and getattr(self, '_voice_agent_enabled', True):
                            out = self._agent_brain.process_emergency_event("critical_alert", alert_desc)
                            self._tts_worker.speak(out.speech_response, is_emergency=True)

                self._ai_proc.sig_error.connect(_on_cv_alert)

            # Start workers
            self._tts_worker.start()
            self._vad_worker.start()
            self._voice_agent_enabled = True

            # Giới thiệu tự động khi khởi động phần mềm
            welcome_text = "Tôi là CNX VIC, trợ lý ảo chuyên nghiệp sẽ hỗ trợ bạn trong suốt quá trình làm việc."
            self._tts_worker.speak(welcome_text)
            if self._ai_panel:
                self._ai_panel.lbl_agent_speech.setText(f"Agent: {welcome_text}")

            if hasattr(self, 'power_widget') and self.power_widget:
                self.power_widget.add_log("🎙 Trợ lý Giọng nói Offline VIC (VAD+STT+SLM+TTS) đã sẵn sàng", "SUCCESS")

        except Exception as exc:
            print(f"[Main] Error starting Voice Agent: {exc}")

    def _process_pilot_voice_command(self, text: str = "", pcm_audio = None, is_ptt: bool = False):
        """Process transcribed voice command from pilot using async background worker (0% GUI freeze)."""
        if not self._agent_brain:
            return
        if hasattr(self, '_voice_agent_enabled') and not self._voice_agent_enabled:
            print("[Main] Voice Agent is disabled. Ignoring input.")
            return

        self._is_processing_voice = True

        voltage = float(getattr(self, '_voltage', 16.8))
        if voltage >= 14.0 and voltage <= 16.8:
            battery_pct = max(0, min(100, int((voltage - 14.0) / 2.8 * 100)))
        else:
            battery_pct = int(self.settings.get("battery_pct", 85))

        temp_c = float(self._named_sensors.get("TEMP", 28.5)) if hasattr(self, '_named_sensors') and isinstance(self._named_sensors, dict) and "TEMP" in self._named_sensors else 28.5

        telemetry = {
            "depth": round(float(getattr(self, '_depth', 0.0)), 2),
            "depth_m": round(float(getattr(self, '_depth', 0.0)), 2),
            "voltage": round(voltage, 1),
            "voltage_v": round(voltage, 1),
            "heading": round(float(getattr(self, '_heading', 0.0)), 1),
            "heading_deg": round(float(getattr(self, '_heading', 0.0)), 1),
            "battery_pct": battery_pct,
            "internal_temp_c": round(temp_c, 1),
            "temp": round(temp_c, 1),
            "leak_detected": bool(getattr(self, '_leak_detected', False)),
            "ekf3_status": "GOOD",
            "lights_intensity_pct": getattr(self, '_lights_val', 100 if getattr(self, '_lights_on', True) else 0),
            "armed": bool(getattr(self, '_armed', False)),
            "mode": str(getattr(self, '_flight_mode', "ALT_HOLD")),
        }

        # Run STT & LLM off the Qt GUI Main Thread in an async QThread
        worker = AgentAsyncWorker(self._agent_brain, text, pcm_audio, self._stt_worker, telemetry, is_ptt=is_ptt, parent=self)

        def _on_async_completed(output, immediate_action, cmd_text):
            try:
                # Check if voice agent was disabled while worker was processing in background
                if hasattr(self, '_voice_agent_enabled') and not self._voice_agent_enabled:
                    print("[Main] Async worker completed but Voice Agent is disabled. Suppressing response.")
                    return

                if output is None or not output.speech_response:
                    print("[Main] Empty or invalid agent response. Ignoring UI update.")
                    return

                if cmd_text and self._ai_panel and hasattr(self._ai_panel, 'txt_voice_cmd'):
                    self._ai_panel.txt_voice_cmd.setText(cmd_text)

                # 1. Update UI & Speech Output on Main Thread
                if output and output.speech_response:
                    if self._tts_worker:
                        self._tts_worker.speak(output.speech_response)
                    if self._ai_panel:
                        self._ai_panel.lbl_agent_speech.setText(f"Agent: {output.speech_response}")
                    if hasattr(self, 'power_widget') and self.power_widget:
                        self.power_widget.add_log(f"🎙 Agent: {output.speech_response}", "INFO")

                # 2. Update Safety Confirmation Box on UI
                if self._ai_panel:
                    pending = self._agent_brain.safety_guard.get_pending_action()
                    if pending:
                        self._ai_panel.lbl_safety_prompt.setText(f"CẦN XÁC NHẬN: {pending.get('description')}")
                        self._ai_panel.grp_safety.setVisible(True)
                    else:
                        self._ai_panel.grp_safety.setVisible(False)

                # 3. Execute Immediate Action if approved
                if immediate_action:
                    self._dispatch_agent_action(immediate_action.get("action"), immediate_action.get("params", {}))
            finally:
                self._is_processing_voice = False

        worker.sig_result_ready.connect(_on_async_completed)
        worker.start()

    def _dispatch_agent_action(self, action_name: str, params: dict):
        """Execute dispatched MAVLink / UI actions from Agent."""
        print(f"[Main] Dispatching Agent Action: {action_name} ({params})")
        if hasattr(self, 'power_widget') and self.power_widget:
            self.power_widget.add_log(f"⚙️ Thực thi lệnh Agent: {action_name}", "SUCCESS")

        if action_name == "set_lights":
            val = params.get("value", 100)
            self._set_lights(val)
        elif action_name in ("arm_thrusters", "arm"):
            self._arm_disarm(True)
        elif action_name in ("disarm_thrusters", "disarm"):
            self._arm_disarm(False)
        elif action_name in ("emergency_stop", "estop"):
            self._emergency_stop()
        elif action_name == "take_snapshot":
            self._take_snapshot()

    def _on_ai_model_loaded(self, ok: bool, msg: str):
        print(f"[AI] Model status: {msg}")
        if hasattr(self, 'power_widget') and self.power_widget:
            if ok:
                self.power_widget.add_log(f"🧠 {msg}", "SUCCESS")
            else:
                self.power_widget.add_log(f"❌ AI: {msg}", "ERROR")
        if not ok:
            QtWidgets.QMessageBox.warning(
                self, "AI Load Warning",
                f"Không thể chạy YOLOv8 AI: {msg}\n\n"
                "Hãy đảm bảo bạn đã cài đặt ultralytics:\n"
                "pip install ultralytics"
            )

    def _on_ai_detection_toggle(self, enabled: bool):
        if not HAS_AI:
            return
        if enabled:
            if hasattr(self, 'power_widget') and self.power_widget:
                self.power_widget.add_log(
                    "🤖 Đang khởi tạo AI Detection...", "INFO")
            if self._ai_proc is None:
                self._setup_ai_pipeline()
            elif not self._ai_proc.isRunning():
                self._ai_proc.start()
        else:
            if self._ai_proc and self._ai_proc.isRunning():
                self._ai_proc.stop()
            if self._ar_hud:
                self._ar_hud.set_detections([])
            if hasattr(self, 'power_widget') and self.power_widget:
                self.power_widget.add_log("🤖 AI Detection đã tắt", "INFO")

    # ── Diagnostic Alert Handler ──────────────────────────────────
    def _on_diagnostic_alert(self, level: str, message: str):
        """Nhận cảnh báo từ DiagnosticsEngine → hiển thị trong PowerWidget."""
        if hasattr(self, 'power_widget') and self.power_widget:
            self.power_widget.add_log(message, level)
            if level.upper() == 'CRITICAL':
                self.power_widget.set_active_alert(message, level)
        # CRITICAL: cũng hiển thị trên AR HUD nếu đang mở
        if self._ar_hud and level == 'CRITICAL':
            self._ar_hud.set_warning(message, level)

    def _on_dive_time_update(self, minutes: float):
        """Nhận dive time từ DiagnosticsEngine → hiển thị trong PowerWidget."""
        if hasattr(self, 'power_widget') and self.power_widget:
            self.power_widget.set_dive_time(minutes)

    # ── Seafloor Mesh Handler ─────────────────────────────────────
    def _on_seafloor_mesh_updated(self):
        """Cập nhật OpenGL mesh khi SeafloorMapper có dữ liệu mới."""
        if self._seafloor_mapper and self._seafloor_mesh:
            verts, colors, tris = self._seafloor_mapper.get_mesh()
            self._seafloor_mesh.on_mesh_updated(verts, colors, tris)

    # ── AI Track Error → MAVLink ──────────────────────────────────
    def _on_track_error(self, dx: float, dy: float):
        """
        Nhận độ lệch tâm từ AI tracker → bù vào yaw/pitch.
        dx, dy: -1.0 đến +1.0 (normalized offset)
        """
        if not self._connected:
            return
        gain = self._auto_track_gain
        self._ctrl['yaw'] = max(-1.0, min(1.0, dx * gain))
        self._ctrl['pitch'] = max(-1.0, min(1.0, dy * gain))
        self._send_mavlink_control()

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
        self.ui.pbtn_up.released.connect(
            lambda: self._gui_release("key_forward"))

        self.ui.pbtn_down.pressed.connect(
            lambda: self._gui_press("key_backward"))
        self.ui.pbtn_down.released.connect(
            lambda: self._gui_release("key_backward"))

        self.ui.pbtn_left.pressed.connect(lambda: self._gui_press("key_left"))
        self.ui.pbtn_left.released.connect(
            lambda: self._gui_release("key_left"))

        self.ui.pbtn_right.pressed.connect(
            lambda: self._gui_press("key_right"))
        self.ui.pbtn_right.released.connect(
            lambda: self._gui_release("key_right"))

        self.ui.pbtn_stop.clicked.connect(self._emergency_stop)

        # Điều khiển độ sâu trên GUI
        self.ui.pbtn_control_depth_increase.pressed.connect(
            lambda: self._gui_press("key_ascend"))
        self.ui.pbtn_control_depth_increase.released.connect(
            lambda: self._gui_release("key_ascend"))

        self.ui.pbtn_control_depth_decrease.pressed.connect(
            lambda: self._gui_press("key_descend"))
        self.ui.pbtn_control_depth_decrease.released.connect(
            lambda: self._gui_release("key_descend"))

        self.ui.pushButton.clicked.connect(
            self._emergency_stop)  # Nút STOP khẩn cấp

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
        self.ui.pbtn_camera.clicked.connect(
            self._on_camera_button)  # Camera/Record

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
        cad_file = self.find_cad_file(
            model_name) or self.settings.get("cad_file", "") or None

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
        """Khởi động MAVLink, SLAM UDP receiver, và Video threads."""
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
        self._mav_worker.start_worker()

        # SLAM UDP Receiver
        slam_port = self.settings.get("slam_port", 5010)
        self._slam_worker = SLAMUDPReceiver(port=slam_port)
        self._slam_worker.sig_slam_points.connect(self._on_slam_points)
        self._slam_worker.start_worker()

        # ── Gamepad / Joystick Worker ────────────────────────────
        try:
            from GUI.input_handler import GamepadWorker
            self._gamepad_worker = GamepadWorker(
                deadzone=0.15, poll_interval_ms=16, parent=self)
            self._gamepad_worker.sig_gamepad_connected.connect(
                self._on_gamepad_connected)
            self._gamepad_worker.sig_axis_moved.connect(
                self._on_gamepad_axis_moved)
            self._gamepad_worker.sig_button_pressed.connect(
                self._on_gamepad_button_pressed)
            self._gamepad_worker.start()
        except Exception as exc:
            print(f"[Main] Error initializing GamepadWorker: {exc}")
            self._gamepad_worker = None

    def _stop_workers(self):
        if hasattr(self, '_gamepad_worker') and self._gamepad_worker:
            self._gamepad_worker.stop()
        if self._mav_worker:
            self._mav_worker.stop_worker()
        if self._slam_worker:
            self._slam_worker.stop_worker()
        # Dừng video + AI
        if self._video_rx:
            self._video_rx.stop()
        if self._ai_proc and hasattr(self._ai_proc, 'stop'):
            self._ai_proc.stop()

    # ----------------------------------------------------------
    # VÒNG LẶP CHÍNH 60 FPS
    # ----------------------------------------------------------
    def _on_frame(self):
        """
        Vòng lặp chính 60 FPS — NƠI DUY NHẤT cập nhật widget.
        ════════════════════════════════════════════════════════
        Mô hình Polling (Polling Model):
          - MAVLink signal handlers CHỈ ghi dữ liệu vào biến buffer
            (self._roll, self._pos_ned, self._voltage, ...) + đặt dirty flag.
          - _on_frame() đọc buffer, reset dirty flag, cập nhật widget.
          - Loại bỏ hoàn toàn xung đột giữa tần suất nhận MAVLink
            (50Hz attitude, 10Hz position) và tần suất vẽ (60 FPS GUI).

        Tối ưu hóa bổ sung:
          - Trajectory: chỉ cập nhật mỗi 3 frame (~20 Hz)
          - FOV effect: chỉ cập nhật mỗi 4 frame (~15 Hz)
          - Header labels: chỉ cập nhật mỗi 10 frame (~6 Hz)
          - Power widget: chỉ cập nhật mỗi 6 frame (~10 Hz)
          - CSV log: chỉ ghi mỗi 60 frame (~1 Hz)
        """
        if self._physics is None:
            return

        self._frame_count += 1

        # ── 1. Keyboard input + Low-pass filter (mượt mà) ────
        self._update_keyboard_controls()
        alpha = 0.22
        for k in self._ctrl:
            self._smoothed_ctrl[k] = (
                self._smoothed_ctrl[k] * (1 - alpha)
                + self._ctrl[k] * alpha
            )

        # ── 2. Điều khiển ─────────────────────────────────────
        if not self._connected:
            self._physics.set_control(**self._smoothed_ctrl)
        else:
            self._send_mavlink_control()

        # ── 3. Bước vật lý (4 sub-steps ổn định) ─────────────
        state = None
        dt = 1 / 240.0
        for _ in range(4):
            state = self._physics.step(dt)
        if state is None:
            return

        # ── 4. Chọn nguồn dữ liệu: Physics hoặc MAVLink ─────
        if self._connected:
            pos = self._pos_ned
            quat = self._euler_to_quat(self._roll, self._pitch, self._yaw)
            vel = self._vel_ned
        else:
            pos = state["position"]
            quat = state["orientation_quat"]
            vel = np.array(state.get("linear_velocity", [0, 0, 0]))

        spd_now = float(np.linalg.norm(vel))
        roll_deg = math.degrees(self._roll)
        pitch_deg = math.degrees(self._pitch)

        # ── 5. Cập nhật 3D ROV widget (MỖI FRAME) ────────────
        #    update_pose chỉ setData/resetTransform, không tạo GL item mới
        self.gl_3d.update_pose(
            pos, quat,
            heading_deg=self._heading,
            depth_m=self._depth,
            speed_mps=spd_now,
            roll_deg=roll_deg,
            pitch_deg=pitch_deg,
        )

        # ── 6. Trajectory — throttle ~20 Hz (mỗi 3 frame) ───
        if not self._origin_set and np.any(pos != 0):
            self.gl_3d.set_origin(pos)
            self._origin_set = True
        if self._frame_count % 3 == 0:
            self.gl_3d.update_trajectory(pos[0], pos[1], pos[2])

        # ── 7. FOV effect — throttle ~15 Hz (mỗi 4 frame) ───
        if self._frame_count % 4 == 0:
            self.gl_3d.update_fov_effect(self._heading)

        # ── 8. Compass 3D (MỖI FRAME — widget nhỏ, nhẹ) ─────
        self.compass_3d.update_state(quat, vel, depth=self._depth)

        # ── 9. Power widget — throttle ~10 Hz (mỗi 6 frame) ──
        if self._frame_count % 6 == 0:
            if self._connected:
                loads = [abs(v) for v in state.get("thruster_pct", [])]
                loads_norm = [t / 100.0 for t in loads]
            else:
                loads_norm = [abs(v) for v in self._physics._thruster_inputs]
            self.power_widget.set_thruster_loads(loads_norm)
            self.power_widget.set_battery(self._voltage, self._current)

        # ── 10. Header labels — throttle ~6 Hz (mỗi 10 frame) ─
        if self._frame_count % 10 == 0:
            self._update_header_labels()

        # ── 11. CSV log — throttle ~1 Hz (mỗi 60 frame) ──────
        if self._frame_count % 60 == 0:
            self._log_to_csv()

        # Reset counter tránh overflow (mỗi ~18 giờ @ 60fps)
        if self._frame_count >= 3_600_000:
            self._frame_count = 0

    # ----------------------------------------------------------
    # MAVLINK SIGNAL HANDLERS
    # ----------------------------------------------------------
    def _on_connected(self, connected: bool):
        self._connected = connected
        if connected and not self._origin_set:
            # Kích hoạt physics inject khi nhận pose đầu tiên
            pass
        color = "#00FF66" if connected else "#FF4040"
        text = "STRONG" if connected else "DISCONNECTED"
        self.ui.lbl_connection_value.setStyleSheet(
            f"color:{color};font-weight:bold;")
        self.ui.lbl_connection_value.setText(text)
        # Bật inject external pose nếu kết nối
        if self._physics:
            if not connected:
                self._physics.disable_external_pose()
        # ── Log & Active Alert trong PowerWidget ──
        if hasattr(self, 'power_widget') and self.power_widget:
            if connected:
                self.power_widget.add_log("Đã kết nối MAVLink", "SUCCESS")
                self.power_widget.clear_active_alert("Mất kết nối MAVLink")
            else:
                self.power_widget.add_log("Mất kết nối MAVLink", "ERROR")
                self.power_widget.set_active_alert(
                    "Mất kết nối MAVLink", "CRITICAL")

    def _on_link_quality(self, pct: int):
        self._link_quality = pct

    def _on_heartbeat(self, mode: str, status: str):
        self._flight_mode = mode
        self._sys_status = status
        self.ui.lbl_mode_value.setText(mode)
        self.ui.lbl_status_value.setText(status)

    def _on_attitude(self, roll: float, pitch: float, yaw: float):
        """
        Nhận ATTITUDE từ MAVLink (rad).
        POLLING MODEL: Chỉ ghi buffer, KHÔNG gọi widget.update().
        """
        self._roll = roll
        self._pitch = pitch
        self._yaw = yaw
        self._heading = math.degrees(yaw) % 360.0
        self._dirty_attitude = True

    def _on_position_ned(self, x, y, z, vx, vy, vz):
        """
        Nhận LOCAL_POSITION_NED (SLAM fused position).
        POLLING MODEL: Chỉ buffer dữ liệu + inject vào physics engine.
        Widget sẽ được cập nhật trong _on_frame().
        """
        self._pos_ned = np.array([x, y, z])
        self._vel_ned = np.array([vx, vy, vz])
        self._dirty_position = True
        # Physics engine cần pose mới nhất để tính step tiếp theo
        if self._physics and self._connected:
            quat = self._euler_to_quat(self._roll, self._pitch, self._yaw)
            self._physics.set_external_pose([x, y, z], quat.tolist())

    def _on_vfr_hud(self, depth: float, heading: float, throttle: float):
        """POLLING MODEL: Chỉ buffer."""
        self._depth = depth
        self._heading = heading
        self._throttle = throttle

    def _on_sys_status(self, volt: float, curr: float, remain: int):
        """POLLING MODEL: Buffer pin + diagnostics (lightweight computation)."""
        self._voltage = volt
        self._current = curr
        self._dirty_battery = True
        # Diagnostics engine chỉ tính toán số học nhẹ, không gọi widget
        if self._diagnostics:
            self._diagnostics.on_sys_status(volt, curr, remain)
            throttle_norm = abs(self._ctrl.get('surge', 0.0))
            self._diagnostics.on_throttle(throttle_norm)

    def _on_vision_pose(self, x, y, z, roll, pitch, yaw):
        """Raw SLAM pose — ve quy dao rieng neu muon."""
        pass  # Co the ve them trajectory rieng cho raw SLAM

    # _on_gps_raw da bi XOA.
    # ROV o duoi nuoc -> GPS vo dung.
    # Vi tri GPS tuyet doi cua ROV tinh tu:
    #   GCS_GPS (settings["gcs_lat"], settings["gcs_lng"])
    #   + SLAM NED offset (self._pos_ned)
    # Bang ham: utils.geo_utils.ned_to_gps()
    # Xem _on_table_cell_clicked() va _compute_rov_gps()

    def _on_named_float(self, name: str, value: float):
        """Cập nhật bảng cảm biến ngoại vi."""
        self._named_sensors[name] = value
        self._update_telemetry_named(name, value)
        # ── Feature 5: Diagnostics — nhiệt độ nước ───────────────
        if self._diagnostics and name == 'TEMP':
            self._diagnostics.on_water_temp(value)

    def _on_cmd_ack(self, command: int, result: int):
        result_str = {0: "OK", 1: "FAILED",
                      4: "DENIED"}.get(result, str(result))
        print(f"[MAVLink] CMD ACK: command={command} result={result_str}")

    def _on_slam_points(self, pts: np.ndarray):
        """Nhận point cloud từ SLAM UDP thread."""
        self.gl_3d.update_slam_points(pts)
        self.compass_3d.update_slam_points(pts)
        # ── Feature 4: Seafloor Mapper ────────────────────────────
        if self._seafloor_mapper and len(pts) > 0:
            self._seafloor_mapper.add_slam_scan(
                points_ned=pts,
                rov_depth_m=float(self._depth),
                rov_pos_ned=self._pos_ned
            )
            # Cập nhật vị trí ROV trên mesh widget
            if self._seafloor_mesh:
                self._seafloor_mesh.set_rov_position(
                    self._pos_ned[0], self._pos_ned[1], self._depth
                )
        # ── Feature 1: Update AR HUD telemetry ───────────────────
        if self._ar_hud:
            self._ar_hud.update_telemetry(
                roll=self._roll,
                pitch=self._pitch,
                yaw=self._yaw,
                depth=self._depth,
                heading=self._heading,
                speed=float(np.linalg.norm(self._vel_ned)),
                voltage=self._voltage,
                current=self._current,
                pct=int(self._current),
                signal_pct=self._link_quality,
                mode=self._flight_mode,
                armed='ARMED' in self._sys_status.upper()
            )

    # ----------------------------------------------------------
    # CONTROL
    # ----------------------------------------------------------
    def _set_ctrl(self, surge=None, sway=None, heave=None,
                  roll=None, pitch=None, yaw=None):
        if surge is not None:
            self._ctrl["surge"] = surge
        if sway is not None:
            self._ctrl["sway"] = sway
        if heave is not None:
            self._ctrl["heave"] = heave
        if roll is not None:
            self._ctrl["roll"] = roll
        if pitch is not None:
            self._ctrl["pitch"] = pitch
        if yaw is not None:
            self._ctrl["yaw"] = yaw
        # Gửi lệnh MAVLink khi kết nối
        if self._connected and self._mav_worker:
            self._send_mavlink_control()

    # ── Gamepad Event Handlers ────────────────────────────────
    def _on_gamepad_connected(self, connected: bool, name: str):
        """Thông báo kết nối tay cầm Gamepad."""
        if hasattr(self, 'power_widget') and self.power_widget:
            if connected:
                self.power_widget.add_log(
                    f"🎮 Đã kết nối Tay cầm: {name}", "SUCCESS")
            else:
                self.power_widget.add_log(
                    "🎮 Mất kết nối Tay cầm Gamepad", "WARNING")

    def _on_gamepad_axis_moved(self, ctrl: dict):
        """Xử lý tín hiệu cần gạt analog từ tay cầm Gamepad."""
        scale = self._speed_scale
        self._set_ctrl(
            surge=ctrl.get("surge", 0.0) * scale,
            sway=ctrl.get("sway", 0.0) * scale,
            heave=ctrl.get("heave", 0.0) * scale,
            yaw=ctrl.get("yaw", 0.0) * scale,
        )

    def _on_gamepad_button_pressed(self, action: str):
        """Xử lý các phím bấm trên tay cầm Gamepad."""
        if action == "snapshot":
            self._take_snapshot()
        elif action == "record":
            self._on_camera_button()
        elif action == "arm":
            self._toggle_arm()
        elif action == "lights":
            self._mav_lights(True)
        elif action == "speed_up":
            self._speed_up()
        elif action == "speed_down":
            self._speed_down()
        elif action == "emergency_stop":
            self._emergency_stop()

    def _send_mavlink_control(self):
        """Chuyển đổi ctrl [-1,1] → MANUAL_CONTROL [-1000, 1000]."""
        x = int(self._ctrl["surge"] * 1000)
        y = int(self._ctrl["sway"] * 1000)
        z = int((self._ctrl["heave"] + 1.0) * 500)   # 0-1000, 500=neutral
        r = int(self._ctrl["yaw"] * 1000)
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

    def _set_lights(self, val: int):
        """Điều chỉnh độ sáng đèn rọi (0-100%)."""
        if self._mav_worker:
            self._mav_worker.send_lights(int(val))

    def _arm_disarm(self, arm: bool):
        """ARM / DISARM động cơ chân vịt."""
        if self._mav_worker:
            self._mav_worker.send_arm(arm)

    def _toggle_led(self):
        if self._mav_worker:
            self._mav_worker.send_lights(100)

    def _mav_lights(self, brighter: bool):
        if self._mav_worker:
            self._mav_worker.send_lights(100 if brighter else 0)

    def _toggle_arm(self):
        """ARM/DISARM toggle."""
        if self._mav_worker:
            self._mav_worker.send_arm(True)

    # ── Camera Snapshot / Record ───────────────────────────────────────
    def _get_media_dir(self) -> str:
        """Trả về đường dẫn thư mục lưu media, tạo nếu chưa tồn tại."""
        path = self.settings.get('media_save_path', '').strip()
        if not path:
            path = os.path.join(PROJECT_ROOT, 'media')
        os.makedirs(path, exist_ok=True)
        return path

    def _on_camera_button(self):
        """
        Single-click: chụp ảnh snapshot vào thư mục media.
        Double-click (click khi đang recording): dừng recording.
        Logic:
          - Nếu không recording: chụp snapshot và hỏi có muốn bắt đầu record không.
          - Nếu đang recording: dừng và lưu file video.
        """
        if self._is_recording:
            self._stop_recording()
        else:
            # Đầu tiên chụp snapshot
            self._take_snapshot()

    def _take_snapshot(self):
        """Chụp ảnh từ frame hiện tại và lưu file PNG."""
        if self._last_frame is None:
            QtWidgets.QMessageBox.warning(
                self, "Không có video",
                "Chưa có luồng video. Kiểm tra kết nối camera và mở cửa sổ Video."
            )
            return
        try:
            import cv2
            import time as _t
            ts = _t.strftime("%Y%m%d_%H%M%S")
            path = os.path.join(self._get_media_dir(), f"snap_{ts}.png")
            cv2.imwrite(path, self._last_frame)
            print(f"[Camera] Snapshot saved: {path}")
            # Hiển thị thông báo nhỏ
            self.ui.pbtn_camera.setToolTip(
                f"Snapshot: {os.path.basename(path)}")
            # Hỏi có muốn bắt đầu ghi video không
            reply = QtWidgets.QMessageBox.question(
                self, "📸 Snapshot đã lưu",
                f"Snapshot: {path}\n\nBat dau ghi video khong?",
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
                QtWidgets.QMessageBox.StandardButton.No
            )
            if reply == QtWidgets.QMessageBox.StandardButton.Yes:
                self._start_recording()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Lỗi Snapshot", str(e))

    def _start_recording(self):
        """Bắt đầu ghi video vào file MP4."""
        if self._last_frame is None:
            return
        try:
            import cv2
            import time as _t
            ts = _t.strftime("%Y%m%d_%H%M%S")
            path = os.path.join(self._get_media_dir(), f"rec_{ts}.mp4")
            h, w = self._last_frame.shape[:2]
            fps = int(self.settings.get('video_fps', 30))
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            self._video_writer = cv2.VideoWriter(path, fourcc, fps, (w, h))
            self._is_recording = True
            # Thay đổi icon/style nút
            self.ui.pbtn_camera.setStyleSheet(
                "QPushButton { border: 2px solid #FF4040; color: #FF4040; "
                "background: rgba(255,0,0,0.1); border-radius:4px; }"
            )
            self.ui.pbtn_camera.setToolTip(
                f"Recording... Click để dừng. File: {os.path.basename(path)}")
            print(f"[Camera] Recording started: {path}")
            if self._ar_hud:
                self._ar_hud.set_recording_status(True)
            if hasattr(self, 'power_widget') and self.power_widget:
                self.power_widget.add_log(
                    f"🔴 Đang ghi hình: {os.path.basename(path)}", "WARNING")
        except Exception as e:
            self._is_recording = False
            if self._ar_hud:
                self._ar_hud.set_recording_status(False)
            QtWidgets.QMessageBox.critical(self, "Lỗi Recording", str(e))

    def _stop_recording(self):
        """Dừng ghi video và lưu file."""
        self._is_recording = False
        if self._video_writer is not None:
            self._video_writer.release()
            self._video_writer = None
        if self._ar_hud:
            self._ar_hud.set_recording_status(False)
        # Khôi phục style nút
        self.ui.pbtn_camera.setStyleSheet("")
        self.ui.pbtn_camera.setToolTip("Chụp ảnh / Ghi video")
        print("[Camera] Recording stopped.")
        if hasattr(self, 'power_widget') and self.power_widget:
            self.power_widget.add_log(
                "⏹ Ghi hình đã dừng, video đã lưu", "SUCCESS")
        QtWidgets.QMessageBox.information(
            self, "📹 Recording dừng",
            f"Video đã lưu vào thư mục:\n{self._get_media_dir()}"
        )

    # ----------------------------------------------------------
    # SETTINGS DIALOG
    # ----------------------------------------------------------
    def _open_settings(self):
        dlg = SettingsDialog(self.settings, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.settings.update(dlg.settings)
            self._apply_updated_settings()
            print(f"[Settings] Saved & applied dynamically: {self.settings}")
            if hasattr(self, 'power_widget') and self.power_widget:
                self.power_widget.add_log(
                    "⚙️ Cài đặt đã lưu và áp dụng", "SUCCESS")

    def _apply_updated_settings(self):
        """
        Áp dụng cài đặt mới động trực tiếp mà KHÔNG reset vị trí,
        KHÔNG dừng các worker đang chạy và KHÔNG gián đoạn hoạt động.
        """
        # 1. Cập nhật Video Receiver nếu có
        if self._video_rx:
            src = self.settings.get('video_source', 'udp_h264')
            if src == 'udp_h264':
                port = int(self.settings.get('udp_video_port', 5620))
                self._video_rx.set_source(VideoSource.UDP_H264, port)
            elif src == 'webcam':
                idx = int(self.settings.get('webcam_index', 0))
                self._video_rx.set_source(VideoSource.WEBCAM, idx)
            elif src == 'rtsp':
                url = self.settings.get(
                    'rtsp_url', 'rtsp://192.168.2.2:8554/video')
                self._video_rx.set_source(VideoSource.RTSP, url)
            elif src == 'file':
                path = self.settings.get('video_file', '')
                self._video_rx.set_source(VideoSource.FILE, path)

            # Đồng bộ lại ComboBox chọn nhanh nguồn video
            if hasattr(self, 'cb_quick_vid_src'):
                map_idx = {'webcam': 0, 'udp_h264': 1, 'rtsp': 2, 'file': 3}
                self.cb_quick_vid_src.blockSignals(True)
                self.cb_quick_vid_src.setCurrentIndex(map_idx.get(src, 0))
                self.cb_quick_vid_src.blockSignals(False)

        # 2. Cập nhật AR HUD Overlay
        if self._ar_hud:
            self._ar_hud.set_hud_enabled(
                self.settings.get('ar_hud_enabled', True))

        # 3. Cập nhật AI Vision Processor
        ai_enabled = self.settings.get('ai_detection_enabled', False)
        if HAS_AI:
            if ai_enabled and not self._ai_proc:
                self._setup_ai_pipeline()
            elif self._ai_proc:
                self._on_ai_detection_toggle(ai_enabled)

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
                letter-spacing: 1.2px;
                padding: 4px 6px;
                text-transform: uppercase;
            }
            QTableWidget::item {
                padding: 3px 6px;
                border-bottom: 1px solid rgba(27, 47, 74, 0.4);
            }
            QTableWidget::item:selected {
                background-color: rgba(0, 240, 255, 0.18);
                color: #FFFFFF;
            }
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

    def _compute_rov_gps(self):
        """
        Tính toạ độ GPS tuyệt đối của ROV.
        ROV_GPS = GCS_GPS + SLAM_NED_offset
        """
        from utils.geo_utils import rov_google_maps_url
        gcs_lat = float(self.settings.get("gcs_lat", 0.0))
        gcs_lng = float(self.settings.get("gcs_lng", 0.0))
        if gcs_lat == 0.0 and gcs_lng == 0.0:
            return None   # Chưa cài đặt GCS GPS
        ned_x, ned_y, ned_z = (
            self._pos_ned[0], self._pos_ned[1], self._pos_ned[2]
        )
        url, rov_lat, rov_lon, depth_m = rov_google_maps_url(
            gcs_lat, gcs_lng, ned_x, ned_y, ned_z
        )
        return rov_lat, rov_lon, depth_m, url

    def _on_table_cell_clicked(self, row, column):
        """Mo Google Maps tro dung toa do ROV khi click vao hang GPS Map Link."""
        table = self._telem_table
        if not (table.item(row, 0)
                and table.item(row, 0).text() == "GPS Map Link"):
            return
        result = self._compute_rov_gps()
        if result is None:
            QtWidgets.QMessageBox.warning(
                self, "GCS GPS chua dat",
                "Vui long nhap toa do GCS (lat/lon) trong Settings truoc."
            )
            return
        rov_lat, rov_lon, depth_m, url = result
        # Cap nhat gia tri hien thi trong bang
        if table.item(row, 1):
            table.item(row, 1).setText(
                f"{rov_lat:.6f}, {rov_lon:.6f}  (depth={depth_m:.1f}m)"
            )
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
        """Cập nhật các label trên header bar. Được gọi ~6 Hz từ _on_frame."""
        # Cập nhật telemetry table (đã throttle bởi _on_frame)
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
        if not self._pressed_keys:
            return  # Không có phím bàn phím nào được bấm -> giữ nguyên trạng thái từ Gamepad / GUI

        sp = self._speed_scale
        surge = 0.0
        sway = 0.0
        heave = 0.0
        yaw = 0.0

        # Ánh xạ phím động từ cài đặt
        key_fwd = KEY_MAP.get(self.settings.get(
            "key_forward", "W"), Qt.Key.Key_W)
        key_bwd = KEY_MAP.get(self.settings.get(
            "key_backward", "S"), Qt.Key.Key_S)
        key_left = KEY_MAP.get(self.settings.get(
            "key_left", "A"), Qt.Key.Key_A)
        key_right = KEY_MAP.get(self.settings.get(
            "key_right", "D"), Qt.Key.Key_D)
        key_sw_l = KEY_MAP.get(self.settings.get(
            "key_sway_left", "Q"), Qt.Key.Key_Q)
        key_sw_r = KEY_MAP.get(self.settings.get(
            "key_sway_right", "E"), Qt.Key.Key_E)
        key_asc = KEY_MAP.get(self.settings.get(
            "key_ascend", "R"), Qt.Key.Key_R)
        key_desc = KEY_MAP.get(self.settings.get(
            "key_descend", "F"), Qt.Key.Key_F)

        if key_fwd in self._pressed_keys:
            surge += sp
        if key_bwd in self._pressed_keys:
            surge -= sp
        if key_sw_l in self._pressed_keys:
            sway -= sp
        if key_sw_r in self._pressed_keys:
            sway += sp
        if key_asc in self._pressed_keys:
            heave -= sp
        if key_desc in self._pressed_keys:
            heave += sp
        if key_left in self._pressed_keys:
            yaw -= sp
        if key_right in self._pressed_keys:
            yaw += sp

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
                    math.degrees(self._roll), math.degrees(
                        self._pitch), math.degrees(self._yaw),
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
        if hasattr(self, 'telemetry_logger') and self.telemetry_logger:
            try:
                self.telemetry_logger.stop()
            except Exception:
                pass
        if hasattr(self, 'db') and self.db and hasattr(self, 'active_session_id') and self.active_session_id:
            try:
                self.db.end_dive_session(self.active_session_id, status="COMPLETED")
            except Exception:
                pass
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
        # GCS location — BUộC nhập trong Settings → General
        # (dùng "📍 Lấy vị trí hiện tại" hoặc Google Maps cần sao chép thủ công)
        "gcs_lat":       0.0,
        "gcs_lng":       0.0,
        # Video
        "video_source":  "udp_h264",
        "udp_video_port": 5620,
        "rtsp_url":      "rtsp://192.168.2.2:8554/video",
        "video_fps":     30,
        "video_resolution": "640x480",
        "ar_hud_enabled": True,
        "media_save_path": os.path.join(PROJECT_ROOT, "media"),
        # Controls
        "key_forward":   "W",
        "key_backward":  "S",
        "key_left":      "A",
        "key_right":     "D",
        "key_sway_left": "Q",
        "key_sway_right": "E",
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
    window.setWindowTitle("CNC NExora — ROV CONTROL SYSTEM")
    window.showMaximized()  # Tự động mở 100% toàn màn hình

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
