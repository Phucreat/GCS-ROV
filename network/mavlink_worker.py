"""
mavlink_worker.py - MAVLink Communication Thread
=================================================
Chạy trên QThread riêng để không block GUI.
Nhận/gửi MAVLink, emit signal mỗi khi có dữ liệu mới.

Các message xử lý:
  HEARTBEAT (0)            → connection alive, flight mode
  SYS_STATUS (1)           → battery voltage, current
  ATTITUDE (30)            → roll, pitch, yaw (rad)
  LOCAL_POSITION_NED (32)  → x, y, z, vx, vy, vz (SLAM fused)
  VFR_HUD (74)             → depth(alt), heading, throttle
  COMMAND_ACK (77)         → kết quả lệnh ARM/DISARM
  VISION_POSITION_ESTIMATE (102) → raw SLAM pose
  NAMED_VALUE_FLOAT (251)  → cảm biến ngoại vi (nhiệt, pH,...)
"""
import time
import threading
from PyQt6.QtCore import QThread, pyqtSignal, QMutex


class MAVLinkWorker(QThread):
    """
    Thread nhận MAVLink và emit các signal về GUI thread.
    Dùng pymavlink nếu cài được, fallback về MockTransceiver.
    """

    # ============================================================
    # SIGNALS (GUI lắng nghe)
    # ============================================================
    # Kết nối
    sig_connected = pyqtSignal(bool)           # True/False
    sig_link_quality = pyqtSignal(int)            # 0–100%

    # Trạng thái hệ thống
    sig_heartbeat = pyqtSignal(str, str)       # (mode_str, status_str)

    # Cảm biến chính
    # roll, pitch, yaw (rad)
    sig_attitude = pyqtSignal(float, float, float)
    sig_position_ned = pyqtSignal(float, float, float,
                                  float, float, float)       # x,y,z, vx,vy,vz
    # depth_m, heading_deg, throttle_pct
    sig_vfr_hud = pyqtSignal(float, float, float)
    # volt_v, curr_a, remain_pct
    sig_sys_status = pyqtSignal(float, float, int)

    # SLAM raw
    sig_vision_pose  = pyqtSignal(float, float, float,
                                  float, float, float)       # x,y,z, roll,pitch,yaw

    # GPS Raw / Global Position (để định vị thật)
    sig_gps_raw      = pyqtSignal(float, float)              # (lat, lon)

    # Cảm biến ngoại vi
    sig_named_float  = pyqtSignal(str, float)                # (name, value)

    # Kết quả lệnh
    sig_cmd_ack = pyqtSignal(int, int)                  # (command, result)

    # ============================================================
    def __init__(self, connection_string: str = "udp:0.0.0.0:14550",
                 target_system: int = 1, parent=None):
        super().__init__(parent)
        self.connection_string = connection_string
        self.target_system = target_system
        self._running = False
        self._mav = None
        self._mutex = QMutex()
        self._heartbeat_timer = 0.0
        self._last_hb_recv = 0.0
        self._use_mock = False

    # ============================================================
    # CONTROL
    # ============================================================
    def start_worker(self):
        self._running = True
        self.start()

    def stop_worker(self):
        self._running = False
        self.quit()
        self.wait(2000)

    # ============================================================
    # THREAD MAIN LOOP
    # ============================================================
    def run(self):
        """Vòng lặp chính: kết nối → nhận gói tin → emit signal."""
        self._mav = self._connect()
        if self._mav is None:
            self.sig_connected.emit(False)
            return
        self.sig_connected.emit(True)
        self._last_hb_recv = time.time()

        while self._running:
            self._send_heartbeat()
            self._recv_messages()
            self._check_link_timeout()
            time.sleep(0.005)   # ~200Hz poll, không block

    def _connect(self):
        """Kết nối MAVLink. Fallback sang Mock nếu lỗi."""
        try:
            from pymavlink import mavutil
            mav = mavutil.mavlink_connection(self.connection_string)
            return mav
        except ImportError:
            print("[MAVLink] pymavlink not found. Using Mock transceiver.")
            self._use_mock = True
            return self._create_mock()
        except Exception as e:
            print(f"[MAVLink] Connection error: {e}")
            self._use_mock = True
            return self._create_mock()

    def _create_mock(self):
        """Tạo đối tượng giả MAVLink để test offline."""
        try:
            import sys
            import os
            import importlib.util
            core_dir = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                                    '..', '..', 'core'))
            mock_path = os.path.join(core_dir, 'mock_transceiver.py')
            spec = importlib.util.spec_from_file_location(
                'mock_transceiver', mock_path)
            if spec is None or spec.loader is None:
                raise ImportError(
                    f"Không tìm thấy mock_transceiver tại {mock_path}")
            mock_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mock_module)
            return mock_module.MockTransceiver()
        except Exception as e:
            print(f"[MAVLink] Mock creation error: {e}")
            return None

    # ============================================================
    # GỬI LỆNH
    # ============================================================
    def send_manual_control(self, x: int, y: int, z: int, r: int,
                            buttons: int = 0):
        """
        Gửi MANUAL_CONTROL.
        x, y, z, r : -1000 đến 1000
        buttons     : bitmask (đèn, gripper,...)
        """
        if self._mav is None or self._use_mock:
            return
        try:
            self._mav.mav.manual_control_send(
                self.target_system, x, y, z, r, buttons
            )
        except Exception as e:
            print(f"[MAVLink] Error send MANUAL_CONTROL: {e}")

    def send_arm(self, arm: bool = True):
        """ARM (True) hoặc DISARM (False) động cơ."""
        if self._mav is None or self._use_mock:
            return
        try:
            from pymavlink import mavutil
            self._mav.mav.command_long_send(
                self.target_system,
                self._mav.target_component,
                mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
                0,
                1 if arm else 0,
                0, 0, 0, 0, 0, 0
            )
        except Exception as e:
            print(f"[MAVLink] Error ARM/DISARM: {e}")

    def send_attitude_target(self, q_wxyz: list, thrust: float = 0.5):
        """
        Gửi SET_ATTITUDE_TARGET (ID 82) — Chế độ Mimic tư thế.
        q_wxyz : [w, x, y, z] quaternion
        thrust : 0.0–1.0
        """
        if self._mav is None or self._use_mock:
            return
        try:
            self._mav.mav.set_attitude_target_send(
                int(time.time() * 1000) & 0xFFFFFFFF,
                self.target_system,
                self._mav.target_component,
                0b00000000,     # type_mask: tất cả enabled
                q_wxyz,         # [w, x, y, z]
                0, 0, 0,        # body_roll_rate, pitch_rate, yaw_rate
                thrust
            )
        except Exception as e:
            print(f"[MAVLink] Error SET_ATTITUDE_TARGET: {e}")

    def send_lights(self, brightness: int):
        """Điều khiển độ sáng đèn (0–100) qua MANUAL_CONTROL buttons."""
        if brightness > 0:
            buttons = (1 << 0)  # bit 0 = Đèn sáng hơn
        else:
            buttons = (1 << 1)  # bit 1 = Đèn tối đi
        self.send_manual_control(0, 0, 500, 0, buttons)

    # ============================================================
    # NHẬN VÀ PARSE GÓI TIN
    # ============================================================
    def _recv_messages(self):
        if self._mav is None:
            return
        # Nhận không chặn (blocking=False)
        try:
            if self._use_mock:
                msgs = self._mav.get_messages()
                for msg in msgs:
                    self._parse_msg(msg)
            else:
                msg = self._mav.recv_match(blocking=False)
                if msg:
                    self._last_hb_recv = time.time()
                    self._parse_msg(msg)
        except Exception as e:
            if self._running:
                print(f"[MAVLink] Receive error: {e}")

    def _parse_msg(self, msg):
        """Phân tích gói tin và emit signal tương ứng."""
        if msg is None:
            return
        t = msg.get_type() if hasattr(msg, 'get_type') else type(msg).__name__

        if t == 'HEARTBEAT':
            self._last_hb_recv = time.time()
            mode_str = self._decode_mode(getattr(msg, 'custom_mode', 0))
            status_str = self._decode_system_status(
                getattr(msg, 'system_status', 0))
            self.sig_heartbeat.emit(mode_str, status_str)

        elif t == 'SYS_STATUS':
            volt_v = getattr(msg, 'voltage_battery', 0) / 1000.0
            curr_a = getattr(msg, 'current_battery', 0) / 100.0
            remain = getattr(msg, 'battery_remaining', -1)
            self.sig_sys_status.emit(volt_v, curr_a, remain)

        elif t == 'ATTITUDE':
            self.sig_attitude.emit(
                getattr(msg, 'roll',  0.0),
                getattr(msg, 'pitch', 0.0),
                getattr(msg, 'yaw',   0.0)
            )

        elif t == 'LOCAL_POSITION_NED':
            self.sig_position_ned.emit(
                getattr(msg, 'x',  0.0), getattr(msg, 'y',  0.0),
                getattr(msg, 'z',  0.0), getattr(msg, 'vx', 0.0),
                getattr(msg, 'vy', 0.0), getattr(msg, 'vz', 0.0)
            )

        elif t == 'VFR_HUD':
            # ArduSub: alt là độ sâu (âm = xuống), dùng abs
            depth = abs(getattr(msg, 'alt', 0.0))
            heading = getattr(msg, 'heading', 0.0)
            thr = getattr(msg, 'throttle', 0.0)
            self.sig_vfr_hud.emit(depth, heading, thr)

        elif t == 'VISION_POSITION_ESTIMATE':
            self.sig_vision_pose.emit(
                getattr(msg, 'x', 0.0), getattr(msg, 'y', 0.0),
                getattr(msg, 'z', 0.0), getattr(msg, 'roll',  0.0),
                getattr(msg, 'pitch', 0.0), getattr(msg, 'yaw', 0.0)
            )

        elif t == 'NAMED_VALUE_FLOAT':
            name = getattr(msg, 'name',  '').strip('\x00')
            value = getattr(msg, 'value', 0.0)
            self.sig_named_float.emit(name, value)

        elif t == 'GPS_RAW_INT':
            lat = getattr(msg, 'lat', 0) / 1e7
            lon = getattr(msg, 'lon', 0) / 1e7
            if lat != 0 and lon != 0:
                self.sig_gps_raw.emit(lat, lon)

        elif t == 'GLOBAL_POSITION_INT':
            lat = getattr(msg, 'lat', 0) / 1e7
            lon = getattr(msg, 'lon', 0) / 1e7
            if lat != 0 and lon != 0:
                self.sig_gps_raw.emit(lat, lon)

        elif t == 'GPS_GLOBAL_ORIGIN':
            lat = getattr(msg, 'latitude', 0) / 1e7
            lon = getattr(msg, 'longitude', 0) / 1e7
            if lat != 0 and lon != 0:
                self.sig_gps_raw.emit(lat, lon)

        elif t == 'COMMAND_ACK':
            self.sig_cmd_ack.emit(
                getattr(msg, 'command', 0),
                getattr(msg, 'result',  0)
            )

    # ============================================================
    # HEARTBEAT GỬI ĐI (1 Hz)
    # ============================================================
    def _send_heartbeat(self):
        now = time.time()
        if now - self._heartbeat_timer < 1.0:
            return
        self._heartbeat_timer = now
        if self._mav is None or self._use_mock:
            return
        try:
            from pymavlink import mavutil
            self._mav.mav.heartbeat_send(
                mavutil.mavlink.MAV_TYPE_GCS,
                mavutil.mavlink.MAV_AUTOPILOT_INVALID,
                0, 0, 0
            )
        except Exception:
            pass

    # ============================================================
    # KIỂM TRA TIMEOUT KẾT NỐI
    # ============================================================
    def _check_link_timeout(self):
        elapsed = time.time() - self._last_hb_recv
        if elapsed > 5.0:
            self.sig_connected.emit(False)
            self.sig_link_quality.emit(0)
        elif elapsed > 2.0:
            quality = max(0, int((5.0 - elapsed) / 3.0 * 60))
            self.sig_link_quality.emit(quality)
        else:
            # Tính chất lượng từ packet loss (giản lược: theo thời gian)
            quality = min(100, int(100 - elapsed * 10))
            self.sig_link_quality.emit(quality)

    # ============================================================
    # GIẢI MÃ ENUM ARDUSUB
    # ============================================================
    @staticmethod
    def _decode_mode(custom_mode: int) -> str:
        # ArduSub flight modes
        MODES = {
            0:  "STABILIZE", 1:  "ACRO",    2: "ALT_HOLD",
            3:  "AUTO",       4:  "GUIDED",  5: "VELHOLD",
            6:  "RESERVED",   7:  "CIRCLE",  9: "SURFACE",
            16: "POSHOLD",    19: "MANUAL",
        }
        return MODES.get(custom_mode, f"MODE_{custom_mode}")

    @staticmethod
    def _decode_system_status(status: int) -> str:
        STATUS = {
            0: "UNINIT", 1: "BOOT", 2: "CALIBRATING",
            3: "STANDBY", 4: "ACTIVE", 5: "CRITICAL",
            6: "EMERGENCY", 7: "POWEROFF",
        }
        return STATUS.get(status, "UNKNOWN")
