"""
mavlink_worker.py - MAVLink Communication Thread  (MAVLink V2)
==============================================================
Chạy trên QThread riêng để không block GUI.
Dùng MAVLink V2 (STX=0xFD, force_mavlink2=True) để hỗ trợ:
  - Message ID > 255 (WATER_DEPTH #299,...)
  - Packet signing (tùy chọn)
  - Tương thích đầy đủ ArduSub >= 4.0

Các message xử lý:
  HEARTBEAT              (#0)   -> connection alive, flight mode
  SYS_STATUS             (#1)   -> battery voltage, current
  SCALED_PRESSURE        (#29)  -> depth from pressure sensor
  ATTITUDE               (#30)  -> roll, pitch, yaw (rad)
  LOCAL_POSITION_NED     (#32)  -> x, y, z, vx, vy, vz  (SLAM/IMU)
  VFR_HUD                (#74)  -> depth, heading, throttle
  COMMAND_ACK            (#77)  -> ARM/DISARM result
  VISION_POSITION_ESTIMATE(#102)-> raw SLAM pose
  NAMED_VALUE_FLOAT      (#251) -> external sensors
  WATER_DEPTH            (#299) -> sonar depth (V2 only)

GPS ROV bi loai bo co chu y:
  ROV hoat dong duoi nuoc -> GPS vo dung (song radio mat sau vai cm nuoc).
  Vi tri tuyet doi tinh bang: GCS_GPS + SLAM NED offset
  Logic nay xu ly hoan toan ben main.py / utils/geo_utils.py.
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

    # Cảm biến ngoại vi
    sig_named_float  = pyqtSignal(str, float)                # (name, value)

    # Kết quả lệnh
    sig_cmd_ack = pyqtSignal(int, int)                  # (command, result)

    # ============================================================
    def __init__(self, connection_string: str = "udpin:0.0.0.0:14550",
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
        # Thống kê gói tin để tính link quality chính xác
        self._pkt_recv_count  = 0
        self._pkt_total_count = 0
        self._quality_timer   = 0.0

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
        """
        Kết nối MAVLink V2.
        Cơ chế: đặt MAVLINK20=1 trước khi import để pymavlink
        load dialect v20 thay vì v10 (cách chính thức của pymavlink).
        Fallback sang Mock nếu lỗi hoặc không có pymavlink.
        """
        try:
            import os
            os.environ['MAVLINK20'] = '1'        # ← buộc dialect v20
            from pymavlink import mavutil
            mav = mavutil.mavlink_connection(
                self.connection_string,
                source_system    = 255,           # GCS system ID
                source_component = 190,           # GCS component
                force_mavlink2   = True,          # flag bổ sung
                dialect          = 'ardupilotmega',
            )
            # Nếu pymavlink vẫn trả về v10 (udpin chưa nhận packet V2),
            # ép trực tiếp dialect v20 để đảm bảo gửi đúng format V2
            if mav.WIRE_PROTOCOL_VERSION != '2.0':
                from pymavlink.dialects.v20 import ardupilotmega as _mav20
                mav.mav = _mav20.MAVLink(mav, srcSystem=255, srcComponent=190)
                mav.mav.robust_parsing = True
                print("[MAVLink] Dialect manually upgraded to v20")

            print(f"[MAVLink] Connected -> {self.connection_string}")
            print(f"[MAVLink] Wire protocol : {mav.WIRE_PROTOCOL_VERSION}  "
                  f"(dialect: {mav.mav.__class__.__module__})")
            # Yêu cầu ROV gửi các stream data ngay sau kết nối
            self._request_data_streams(mav)
            return mav
        except ImportError:
            print("[MAVLink] pymavlink not found. Using Mock transceiver.")
            self._use_mock = True
            return self._create_mock()
        except Exception as e:
            print(f"[MAVLink] Connection error: {e}")
            self._use_mock = True
            return self._create_mock()

    def _request_data_streams(self, mav):
        """
        Gửi MAV_CMD_SET_MESSAGE_INTERVAL để ROV stream đúng tần suất.
        Thay thế REQUEST_DATA_STREAM (deprecated trong V2).

        Mapping message_id → interval_us:
          ATTITUDE (#30)           : 20 000 µs = 50 Hz
          LOCAL_POSITION_NED (#32) : 100 000 µs = 10 Hz
          VFR_HUD (#74)            : 100 000 µs = 10 Hz
          SYS_STATUS (#1)          : 500 000 µs = 2 Hz
          SCALED_PRESSURE (#29)    : 100 000 µs = 10 Hz
          GPS_RAW_INT (#24)        : 200 000 µs = 5 Hz
          GLOBAL_POSITION_INT (#33): 200 000 µs = 5 Hz
          NAMED_VALUE_FLOAT (#251) : 200 000 µs = 5 Hz
          HEARTBEAT (#0)           : 1 000 000 µs = 1 Hz
        """
        from pymavlink import mavutil
        _STREAMS = [
            (0,   1_000_000),   # HEARTBEAT         1 Hz
            (1,     500_000),   # SYS_STATUS        2 Hz
            (29,    100_000),   # SCALED_PRESSURE  10 Hz
            (30,     20_000),   # ATTITUDE         50 Hz
            (32,    100_000),   # LOCAL_POS_NED    10 Hz
            (74,    100_000),   # VFR_HUD          10 Hz
            (251,   200_000),   # NAMED_VALUE_FLOAT 5 Hz
            # ID 24/33/49 (GPS) bi loai bo:
            # ROV duoi nuoc khong co GPS.
            # Vi tri tuyet doi = GCS_GPS + SLAM NED (tinh trong main.py)
        ]
        for msg_id, interval_us in _STREAMS:
            try:
                mav.mav.command_long_send(
                    self.target_system,
                    mavutil.mavlink.MAV_COMP_ID_AUTOPILOT1,
                    511,            # MAV_CMD_SET_MESSAGE_INTERVAL
                    0,              # confirmation
                    float(msg_id),  # param1: message id
                    float(interval_us),  # param2: interval µs (-1=disable)
                    0, 0, 0, 0, 0
                )
            except Exception:
                pass
        print("[MAVLink] Stream rates requested (V2 SET_MESSAGE_INTERVAL)")

    def _create_mock(self):
        """Tạo đối tượng giả MAVLink để test offline."""
        try:
            import sys
            import os
            import importlib.util
            core_dir = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                                    '..', 'core'))
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

        elif t == 'SCALED_PRESSURE':
            # Tính độ sâu từ áp suất: depth = (P_abs - P_atm) / (rho*g)
            # P_atm ≈ 1013.25 hPa, rho_water=1025 kg/m³, g=9.80665
            press_hpa = getattr(msg, 'press_abs', 1013.25)
            depth_m   = max(0.0, (press_hpa - 1013.25) / 98.0665)
            # Emit qua sig_vfr_hud để tương thích (depth, heading=0, thr=0)
            # Chỉ cập nhật depth, giữ heading từ ATTITUDE/VFR_HUD
            self._depth_from_pressure = depth_m

        elif t == 'VFR_HUD':
            # Ưu tiên depth từ SCALED_PRESSURE nếu có, fallback về VFR_HUD.alt
            depth_vfr = abs(getattr(msg, 'alt', 0.0))
            depth     = getattr(self, '_depth_from_pressure', depth_vfr)
            heading   = getattr(msg, 'heading', 0.0)
            thr       = getattr(msg, 'throttle', 0.0)
            self.sig_vfr_hud.emit(depth, float(heading), thr)

        elif t == 'WATER_DEPTH':
            # MAVLink V2 only — message ID #299
            # ArduSub gửi nếu có cảm biến ping sonar
            depth_m = getattr(msg, 'depth', 0.0)
            self._depth_from_pressure = depth_m
            self.sig_vfr_hud.emit(depth_m, 0.0, 0.0)

        elif t == 'VISION_POSITION_ESTIMATE':
            self.sig_vision_pose.emit(
                getattr(msg, 'x', 0.0), getattr(msg, 'y', 0.0),
                getattr(msg, 'z', 0.0), getattr(msg, 'roll',  0.0),
                getattr(msg, 'pitch', 0.0), getattr(msg, 'yaw', 0.0)
            )

        elif t == 'NAMED_VALUE_FLOAT':
            name  = getattr(msg, 'name',  '').strip('\x00')
            value = getattr(msg, 'value', 0.0)
            self.sig_named_float.emit(name, value)

        elif t == 'COMMAND_ACK':
            self.sig_cmd_ack.emit(
                getattr(msg, 'command', 0),
                getattr(msg, 'result',  0)
            )
        # GPS_RAW_INT (#24), GLOBAL_POSITION_INT (#33), GPS_GLOBAL_ORIGIN (#49)
        # da bi loai bo. ROV duoi nuoc khong co GPS.
        # Vi tri tuyet doi = GCS_GPS + SLAM NED - xu ly o main.py.

    # ============================================================
    # HEARTBEAT GỬI ĐI (1 Hz) — MAVLink V2
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
            # V2: heartbeat_send với 5 tham số chuẩn
            self._mav.mav.heartbeat_send(
                mavutil.mavlink.MAV_TYPE_GCS,           # type
                mavutil.mavlink.MAV_AUTOPILOT_INVALID,  # autopilot
                mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED,  # base_mode
                0,                                      # custom_mode
                mavutil.mavlink.MAV_STATE_ACTIVE,       # system_status
            )
        except Exception:
            pass

    # ============================================================
    # KIỂM TRA TIMEOUT + LINK QUALITY
    # ============================================================
    def _check_link_timeout(self):
        elapsed = time.time() - self._last_hb_recv
        if elapsed > 5.0:
            # Mất kết nối hoàn toàn
            self.sig_connected.emit(False)
            self.sig_link_quality.emit(0)
            return

        # Tính link quality từ packet stats của pymavlink (V2 hỗ trợ)
        quality = 100
        if not self._use_mock and self._mav is not None:
            try:
                # pymavlink tự đếm packet_rx_success và packet_rx_drop_count
                rx_ok   = getattr(self._mav, 'mav_count',     None)
                rx_drop = getattr(self._mav, 'mav_loss_count', None)
                if rx_ok is not None and rx_drop is not None:
                    total = rx_ok + rx_drop
                    if total > 0:
                        quality = max(0, min(100, int(rx_ok / total * 100)))
            except Exception:
                pass

        # Giảm quality theo thời gian kể từ heartbeat cuối cùng
        if elapsed > 2.0:
            quality = min(quality, max(0, int((5.0 - elapsed) / 3.0 * 70)))

        self.sig_connected.emit(True)
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
