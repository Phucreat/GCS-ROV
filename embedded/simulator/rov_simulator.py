"""
rov_simulator.py - Bo mo phong ROV hoan chinh
=============================================
Chay tren PC hoac Raspberry Pi khi chua co phan cung.
Gui MAVLink V2 len GCS qua UDP, nhan lenh dieu khien tu GCS.

Tinh nang:
  - Mo phong vat ly ROV (dong luc hoc 6DOF don gian hoa)
  - Sinh du lieu cam bien voi noise thuc te (IMU/Pressure/Battery)
  - Phan hoi lenh MANUAL_CONTROL (ROV di chuyen dung theo lenh)
  - ARM/DISARM/MODE support
  - SLAM gia: sinh quy dao co nhieu
  - Hien thi trang thai real-time tren console

Cach dung:
  python rov_simulator.py --gcs 192.168.2.1 --port 14550

Neu chay tren cung may voi GCS:
  python rov_simulator.py --gcs 127.0.0.1 --port 14550
"""
import os
import sys
import math
import time
import random
import socket
import struct
import argparse
import threading
import numpy as np
from dataclasses import dataclass, field
from typing import Optional, List

# QUAN TRONG: dat truoc khi import pymavlink
os.environ['MAVLINK20'] = '1'
from pymavlink import mavutil

# Import model tu cung thu muc
sys.path.insert(0, os.path.dirname(__file__))
from sensor_models import IMUModel, PressureSensorModel, BatteryModel, \
                          WaterTempModel, LeakSensorModel
from thruster_model import ThrusterMatrix6DOF, total_current_from_pwms


# ═══════════════════════════════════════════════════════
# CAU HINH
# ═══════════════════════════════════════════════════════
@dataclass
class SimConfig:
    gcs_ip:        str   = "127.0.0.1"
    gcs_mav_port:  int   = 14550
    gcs_slam_port: int   = 5010
    sim_hz:        float = 200.0      # Tan so vong lap chinh (Hz)
    # Moi truong
    water_surface_temp: float = 27.0   # °C


# ═══════════════════════════════════════════════════════
# TRANG THAI ROV
# ═══════════════════════════════════════════════════════
@dataclass
class ROVState:
    # Toa do NED (m)
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0      # Down duong = xuong sau

    # Van toc NED (m/s)
    vx: float = 0.0
    vy: float = 0.0
    vz: float = 0.0

    # Tu the (rad)
    roll:  float = 0.0
    pitch: float = 0.0
    yaw:   float = 0.0

    # Toc do goc (rad/s)
    p: float = 0.0   # roll rate
    q: float = 0.0   # pitch rate
    r: float = 0.0   # yaw rate

    # Trang thai he thong
    armed:       bool = False
    mode:        int  = 19     # MANUAL
    pwm_values:  list = field(default_factory=lambda: [1500.0]*6)
    flight_mode_str: str = "MANUAL"

    # Muc tieu dieu khien (tu GCS)
    cmd_x: int = 0      # surge  -1000~+1000
    cmd_y: int = 0      # sway
    cmd_z: int = 500    # heave  0~1000
    cmd_r: int = 0      # yaw

    # Khoi luong va quy tinh (BlueROV2 Heavy ~11kg)
    mass_kg:    float = 11.0
    Ixx:        float = 0.40   # kg·m²
    Iyy:        float = 0.40
    Izz:        float = 0.60

    # Damping tuyen tinh (nuoc)
    Dx: float = 40.0
    Dy: float = 40.0
    Dz: float = 50.0
    Dr: float = 20.0

    # Tinh noi (buoyancy) thang du
    buoyancy_excess_n: float = 2.0   # N (duong = luc day len)


# ═══════════════════════════════════════════════════════
# SIMULATOR CHINH
# ═══════════════════════════════════════════════════════
class ROVSimulator:

    def __init__(self, cfg: SimConfig):
        self.cfg   = cfg
        self.state = ROVState()
        self._running = False

        # Mo hinh cam bien
        self._imu     = IMUModel()
        self._pres    = PressureSensorModel()
        self._battery = BatteryModel()
        self._temp    = WaterTempModel(cfg.water_surface_temp)
        self._leak    = LeakSensorModel(leak_probability=0.0)
        self._thruster_matrix = ThrusterMatrix6DOF()

        # Ket noi MAVLink
        mav_url = f"udpout:{cfg.gcs_ip}:{cfg.gcs_mav_port}"
        self._mav = mavutil.mavlink_connection(
            mav_url,
            source_system    = 1,
            source_component = 1,
            force_mavlink2   = True,
        )
        print(f"[SIM] MAVLink V2 -> {mav_url}")

        # Socket SLAM point cloud
        self._slam_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._slam_lock = threading.Lock()

        # Timer
        self._t_boot   = time.monotonic()
        self._t_hb     = 0.0
        self._t_att    = 0.0
        self._t_pos    = 0.0
        self._t_sys    = 0.0
        self._t_hud    = 0.0
        self._t_sens   = 0.0
        self._t_slam   = 0.0
        self._t_print  = 0.0

        # Trajectory history cho SLAM gia
        self._traj: List[np.ndarray] = []

    # ─────────────────────────────────────────
    # CHAY CHINH
    # ─────────────────────────────────────────
    def run(self):
        """Vong lap chinh: ~200Hz."""
        self._running = True
        print("[SIM] ROV Simulator started. Press Ctrl+C to stop.")
        print(f"[SIM] GCS: {self.cfg.gcs_ip}:{self.cfg.gcs_mav_port}")
        print(f"[SIM] SLAM point cloud -> port {self.cfg.gcs_slam_port}")
        print("[SIM] Waiting for GCS heartbeat...")

        dt = 1.0 / self.cfg.sim_hz
        while self._running:
            loop_start = time.monotonic()
            now = loop_start

            # Nhan lenh tu GCS
            self._receive_gcs()

            # Cap nhat vat ly ROV
            self._update_physics(dt)

            # Gui telemetry theo dung tan suat
            self._send_scheduled(now)

            # In trang thai
            if now - self._t_print >= 0.5:
                self._print_status()
                self._t_print = now

            # Giu dung tan suat vong lap
            elapsed = time.monotonic() - loop_start
            sleep_t = max(0, dt - elapsed)
            time.sleep(sleep_t)

    def stop(self):
        self._running = False

    # ─────────────────────────────────────────
    # NHAN LENH TU GCS
    # ─────────────────────────────────────────
    def _receive_gcs(self):
        """Nhan va xu ly message tu GCS (non-blocking)."""
        for _ in range(10):   # Xu ly toi da 10 msg/loop
            msg = self._mav.recv_match(blocking=False)
            if msg is None:
                break
            t = msg.get_type()

            if t == 'MANUAL_CONTROL':
                if self.state.armed:
                    self.state.cmd_x = getattr(msg, 'x', 0)
                    self.state.cmd_y = getattr(msg, 'y', 0)
                    self.state.cmd_z = getattr(msg, 'z', 500)
                    self.state.cmd_r = getattr(msg, 'r', 0)

            elif t == 'COMMAND_LONG':
                self._handle_command(msg)

            elif t == 'HEARTBEAT':
                pass   # GCS van song

    def _handle_command(self, msg):
        cmd = msg.command

        if cmd == 400:   # ARM/DISARM
            armed = (msg.param1 == 1.0)
            self.state.armed = armed
            if not armed:
                # Disarm: dat tat ca thruster ve neutral
                self.state.cmd_x = 0
                self.state.cmd_y = 0
                self.state.cmd_z = 500
                self.state.cmd_r = 0
            print(f"[SIM] {'ARMED' if armed else 'DISARMED'}")
            self._send_cmd_ack(400, 0)

        elif cmd == 176:  # SET_MODE
            mode = int(msg.param2)
            self.state.mode = mode
            modes = {0:"STABILIZE",2:"ALT_HOLD",9:"SURFACE",19:"MANUAL"}
            self.state.flight_mode_str = modes.get(mode, f"MODE_{mode}")
            print(f"[SIM] Mode -> {self.state.flight_mode_str}")
            self._send_cmd_ack(176, 0)

        elif cmd == 20:   # RTH
            print("[SIM] Return to Home!")
            self._send_cmd_ack(20, 0)
            self.state.armed = False

        elif cmd == 511:  # SET_MESSAGE_INTERVAL
            self._send_cmd_ack(511, 0)   # Chap nhan

    # ─────────────────────────────────────────
    # CAP NHAT VAT LY 6DOF (don gian hoa)
    # ─────────────────────────────────────────
    def _update_physics(self, dt: float):
        s = self.state
        if not s.armed:
            # Khong arm: tat thrust, ROV noi len tu tu
            s.vz = max(0.0, s.vz - 0.5 * dt)  # Buoyancy nhe
            s.z  = max(0.0, s.z + s.vz * dt)
            # Damping
            s.vx *= math.exp(-5.0 * dt)
            s.vy *= math.exp(-5.0 * dt)
            return

        # Tinh PWM tu lenh
        pwms = self._thruster_matrix.manual_control_to_pwm(
            s.cmd_x, s.cmd_y, s.cmd_z, s.cmd_r
        )
        s.pwm_values = pwms

        # Luc tu thruster (N) - don gian hoa theo huong dieu khien
        from thruster_model import T200Model
        max_f_xy = 4 * 50.0 * math.cos(math.radians(45))   # 4 thruster ngang
        max_f_z  = 2 * 50.0                                  # 2 thruster doc

        Fx = (s.cmd_x / 1000.0) * max_f_xy * math.cos(s.yaw) \
           - (s.cmd_y / 1000.0) * max_f_xy * math.sin(s.yaw)
        Fy = (s.cmd_x / 1000.0) * max_f_xy * math.sin(s.yaw) \
           + (s.cmd_y / 1000.0) * max_f_xy * math.cos(s.yaw)
        Fz = ((s.cmd_z - 500) / 500.0) * max_f_z - s.buoyancy_excess_n
        Mz = (s.cmd_r / 1000.0) * 30.0   # N·m yaw torque

        # Damping (tuyen tinh don gian)
        Fx -= s.Dx * s.vx
        Fy -= s.Dy * s.vy
        Fz -= s.Dz * s.vz
        Mz -= s.Dr * s.r

        # Tich phan gia toc
        ax = Fx / s.mass_kg
        ay = Fy / s.mass_kg
        az = Fz / s.mass_kg
        ar = Mz / s.Izz

        s.vx += ax * dt
        s.vy += ay * dt
        s.vz += az * dt
        s.r  += ar * dt

        # Clamp van toc (ROV khong di nhanh)
        v_max = 1.5   # m/s
        speed = math.sqrt(s.vx**2 + s.vy**2 + s.vz**2)
        if speed > v_max:
            scale = v_max / speed
            s.vx *= scale; s.vy *= scale; s.vz *= scale

        # Cap nhat vi tri
        s.x += s.vx * dt
        s.y += s.vy * dt
        s.z  = max(0.0, s.z + s.vz * dt)   # Khong noi len qua mat nuoc

        # Cap nhat goc
        s.yaw = (s.yaw + s.r * dt) % (2 * math.pi)

        # Roll/Pitch: tinh noi tu nhung ROV ve 0
        s.roll  *= math.exp(-2.0 * dt)
        s.pitch *= math.exp(-2.0 * dt)
        # Them nhieu nho tu nuoc
        s.roll  += random.gauss(0, 0.001)
        s.pitch += random.gauss(0, 0.001)

        # Luu quy dao cho SLAM
        self._traj.append(np.array([s.x, s.y, s.z]))
        if len(self._traj) > 2000:
            self._traj.pop(0)

    # ─────────────────────────────────────────
    # GUI TELEMETRY THEO TAN SUAT
    # ─────────────────────────────────────────
    def _send_scheduled(self, now: float):
        s = self.state

        # 1 Hz — HEARTBEAT
        if now - self._t_hb >= 1.0:
            self._send_heartbeat()
            self._t_hb = now

        # 50 Hz — ATTITUDE + SCALED_PRESSURE
        if now - self._t_att >= 0.02:
            self._send_attitude()
            depth = max(0.0, s.z)
            temp = self._temp.measure(depth)
            press, temp_m = self._pres.measure(depth, temp)
            self._send_pressure(press, temp_m)
            self._t_att = now

        # 10 Hz — LOCAL_POSITION_NED + VFR_HUD
        if now - self._t_hud >= 0.1:
            self._send_position_ned()
            self._send_vfr_hud()
            self._t_hud = now

        # 2 Hz — SYS_STATUS (battery)
        if now - self._t_sys >= 0.5:
            # Tinh dong dien tu thruster
            total_I = total_current_from_pwms(s.pwm_values)
            if not s.armed:
                total_I = 0.8   # Idle khi disarmed
            volt, curr, pct = self._battery.update(total_I)
            self._send_sys_status(volt, curr, pct)
            self._t_sys = now

        # 5 Hz — Cam bien ngoai vi
        if now - self._t_sens >= 0.2:
            depth = max(0.0, s.z)
            self._send_named("TEMP",  self._temp.measure(depth))
            self._send_named("LEAK",  self._leak.measure())
            self._send_named("PH",    random.gauss(7.8, 0.05))
            self._t_sens = now

        # 5 Hz — SLAM point cloud (UDP)
        if now - self._t_slam >= 0.2:
            self._send_slam_pointcloud()
            self._t_slam = now

    # ─────────────────────────────────────────
    # CAC HAM GUI MAVLINK
    # ─────────────────────────────────────────
    def _tms(self) -> int:
        return int((time.monotonic() - self._t_boot) * 1000) & 0xFFFFFFFF

    def _send_heartbeat(self):
        from pymavlink import mavutil as mu
        mode_map = {0:0x01, 2:0x01, 9:0x01, 19:0x01}
        base_mode = (0x81 if self.state.armed else 0x01)
        self._mav.mav.heartbeat_send(
            type=12, autopilot=3,
            base_mode=base_mode,
            custom_mode=self.state.mode,
            mavlink_version=3,
        )

    def _send_attitude(self):
        s = self.state
        # Lay do tu IMU voi noise
        gx, gy, gz = self._imu.measure_gyro((s.p, s.q, s.r))
        self._mav.mav.attitude_send(
            time_boot_ms = self._tms(),
            roll         = s.roll  + random.gauss(0, 0.003),
            pitch        = s.pitch + random.gauss(0, 0.003),
            yaw          = s.yaw   + random.gauss(0, 0.005),
            rollspeed    = gx,
            pitchspeed   = gy,
            yawspeed     = gz,
        )

    def _send_pressure(self, press_hpa: float, temp_c: float):
        self._mav.mav.scaled_pressure_send(
            time_boot_ms = self._tms(),
            press_abs    = press_hpa,
            press_diff   = 0.0,
            temperature  = int(temp_c * 100),
        )

    def _send_position_ned(self):
        s = self.state
        # Them noise SLAM nho
        nx = random.gauss(0, 0.01)
        ny = random.gauss(0, 0.01)
        nz = random.gauss(0, 0.005)
        self._mav.mav.local_position_ned_send(
            time_boot_ms = self._tms(),
            x  = s.x  + nx,
            y  = s.y  + ny,
            z  = s.z  + nz,
            vx = s.vx + random.gauss(0, 0.02),
            vy = s.vy + random.gauss(0, 0.02),
            vz = s.vz + random.gauss(0, 0.01),
        )

    def _send_vfr_hud(self):
        s = self.state
        speed = math.sqrt(s.vx**2 + s.vy**2 + s.vz**2)
        heading_deg = math.degrees(s.yaw) % 360.0
        throttle_pct = abs(s.cmd_x) / 10   # rough estimate
        self._mav.mav.vfr_hud_send(
            airspeed    = speed,
            groundspeed = speed,
            heading     = int(heading_deg),
            throttle    = int(throttle_pct),
            alt         = -max(0.0, s.z),   # depth -> negative alt
            climb       = -s.vz,
        )

    def _send_sys_status(self, volt: float, curr: float, pct: int):
        self._mav.mav.sys_status_send(
            onboard_control_sensors_present=0,
            onboard_control_sensors_enabled=0,
            onboard_control_sensors_health=0,
            load              = 200,
            voltage_battery   = int(volt * 1000),
            current_battery   = int(curr * 100),
            battery_remaining = pct,
            drop_rate_comm=0, errors_comm=0,
            errors_count1=0, errors_count2=0,
            errors_count3=0, errors_count4=0,
        )

    def _send_named(self, name: str, value: float):
        nb = name[:10].encode('ascii').ljust(10, b'\x00')
        self._mav.mav.named_value_float_send(
            time_boot_ms = self._tms(),
            name  = nb,
            value = float(value),
        )

    def _send_cmd_ack(self, command: int, result: int):
        self._mav.mav.command_ack_send(command=command, result=result)

    # ─────────────────────────────────────────
    # SLAM POINT CLOUD GIA (UDP)
    # ─────────────────────────────────────────
    def _send_slam_pointcloud(self):
        """
        Sinh point cloud gia xung quanh vi tri ROV.
        Mo phong cac diem dac trung moi truong duoi nuoc.
        """
        s = self.state
        n_points = 80   # So diem moi lan gui

        points = []
        for _ in range(n_points):
            # Tao diem ngau nhien trong khong gian xung quanh
            r_h = random.uniform(0.5, 8.0)   # khoang cach ngang (m)
            theta = random.uniform(0, 2 * math.pi)
            r_v = random.uniform(-2.0, 2.0)  # khoang cach doc

            px = s.x + r_h * math.cos(theta + s.yaw)
            py = s.y + r_h * math.sin(theta + s.yaw)
            pz = s.z + r_v

            # Chi lay diem o duoi nuoc va tren day bien (gia su day = 30m)
            if 0.0 <= pz <= 30.0:
                # Them noise do camera
                px += random.gauss(0, 0.05)
                py += random.gauss(0, 0.05)
                pz += random.gauss(0, 0.02)
                points.append([px, py, pz])

        if not points:
            return

        pts_arr = np.array(points, dtype=np.float32)
        n = len(pts_arr)
        header = struct.pack('<II', 0x534C414D, n)
        data   = pts_arr.tobytes()
        try:
            self._slam_sock.sendto(
                header + data,
                (self.cfg.gcs_ip, self.cfg.gcs_slam_port)
            )
        except Exception:
            pass

    # ─────────────────────────────────────────
    # IN TRANG THAI CONSOLE
    # ─────────────────────────────────────────
    def _print_status(self):
        s = self.state
        arm_str = "\033[92mARMED\033[0m" if s.armed else "\033[91mDISARMED\033[0m"
        depth = max(0.0, s.z)
        speed = math.sqrt(s.vx**2 + s.vy**2)
        hdg   = math.degrees(s.yaw) % 360
        print(
            f"\r[SIM] {arm_str} | Mode:{s.flight_mode_str:10s} | "
            f"Pos:({s.x:+6.2f},{s.y:+6.2f}) m | "
            f"Depth:{depth:5.2f}m | "
            f"Hdg:{hdg:5.1f}° | "
            f"Spd:{speed:.2f}m/s | "
            f"Cmd:({s.cmd_x:+4d},{s.cmd_y:+4d},{s.cmd_z:4d},{s.cmd_r:+4d})",
            end='', flush=True
        )


# ═══════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(
        description='ROV MAVLink Simulator — dung khi chua co phan cung'
    )
    parser.add_argument('--gcs',   default='127.0.0.1',
                        help='GCS IP (default: 127.0.0.1)')
    parser.add_argument('--port',  default=14550, type=int,
                        help='GCS MAVLink UDP port (default: 14550)')
    parser.add_argument('--slam-port', default=5010, type=int,
                        help='GCS SLAM UDP port (default: 5010)')
    parser.add_argument('--hz',    default=200.0, type=float,
                        help='Simulation loop rate Hz (default: 200)')
    args = parser.parse_args()

    cfg = SimConfig(
        gcs_ip        = args.gcs,
        gcs_mav_port  = args.port,
        gcs_slam_port = args.slam_port,
        sim_hz        = args.hz,
    )

    sim = ROVSimulator(cfg)
    try:
        sim.run()
    except KeyboardInterrupt:
        print("\n[SIM] Stopped by user.")
        sim.stop()


if __name__ == '__main__':
    main()
