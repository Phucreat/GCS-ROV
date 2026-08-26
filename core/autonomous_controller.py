"""
autonomous_controller.py - Closed-Loop Autonomous Trajectory & Pattern Controller
==================================================================================
Bộ điều khiển quỹ đạo vòng lặp kín (Closed-Loop Autonomous Controller) 60Hz:
  1. Điều khiển đến độ sâu chính xác (goto_depth): PID duy trì độ sâu mục tiêu.
  2. Di chuyển tương đối toạ độ thân tàu (relative_move): Tiến/lùi X mét, Dạt trái/phải Y mét.
  3. Quỹ đạo bay tự động thông minh (execute_pattern):
     - 'circle': Lượn vòng tròn bán kính R mét xung quanh tâm khảo sát.
     - 'yaw_scan_360': Xoay quét 360 độ kiểm tra xung quanh.
     - 'lawnmower': Quét đáy hình chữ nhật tìm kiếm vật thể.
     - 'spiral_scan': Lặn xoắn ốc khảo sát trụ giàn khoan/công trình ngầm.
  4. Tự động quay về điểm xuất phát (Return-to-Home / RTH).
"""

from __future__ import annotations

import math
import time
from typing import Dict, List, Optional, Tuple


class AutonomousTaskType:
    NONE = "NONE"
    GOTO_DEPTH = "GOTO_DEPTH"
    RELATIVE_MOVE = "RELATIVE_MOVE"
    CIRCLE_ORBIT = "CIRCLE_ORBIT"
    YAW_SCAN_360 = "YAW_SCAN_360"
    LAWNMOWER = "LAWNMOWER"
    RTH = "RTH"


class AutonomousController:
    """
    Closed-Loop Autopilot running inside GCS main frame loop (60Hz).
    Computes body-frame control signals [surge, sway, heave, yaw] (-1.0 to +1.0).
    """

    def __init__(self):
        self._task_type = AutonomousTaskType.NONE
        self._target_depth = 0.0
        self._target_pos_ned = [0.0, 0.0, 0.0]
        self._target_yaw_deg = 0.0

        # Circle Orbit Parameters
        self._circle_center = [0.0, 0.0]
        self._circle_radius = 3.0
        self._circle_speed = 0.4
        self._circle_angle = 0.0

        # Scan 360 Parameters
        self._scan_start_yaw = 0.0
        self._scan_accum_yaw = 0.0

        # State and completion
        self._is_active = False
        self._status_text = "IDLE"
        self._start_time = 0.0
        self._timeout_s = 60.0

        # PID gains
        self._kp_depth = 0.8
        self._ki_depth = 0.05
        self._depth_integral = 0.0

        self._kp_pos = 0.5
        self._kp_yaw = 0.02

    @property
    def is_active(self) -> bool:
        return self._is_active

    @property
    def task_type(self) -> str:
        return self._task_type

    @property
    def current_mode(self) -> str:
        return self._task_type

    @property
    def status_text(self) -> str:
        return self._status_text

    # ──────────────────────────────────────────────────────────
    # COMMAND TRIGGERS
    # ──────────────────────────────────────────────────────────
    def goto_depth(self, target_depth_m: float) -> str:
        """Kích hoạt tự động lặn/nổi đến độ sâu chính xác (mét)."""
        self._task_type = AutonomousTaskType.GOTO_DEPTH
        self._target_depth = max(0.0, float(target_depth_m))
        self._is_active = True
        self._depth_integral = 0.0
        self._start_time = time.time()
        self._timeout_s = 45.0
        self._status_text = f"AUTO: Lặn tới độ sâu mục tiêu {self._target_depth:.1f}m"
        print(f"[AutoPilot] Started GOTO_DEPTH -> {self._target_depth:.2f}m")
        return self._status_text

    def relative_move(self, surge_m: float, sway_m: float, heave_m: float, current_pos_ned: list, current_heading_deg: float) -> str:
        """
        Di chuyển tương đối theo toạ độ thân tàu (Body-Frame):
          - surge_m: +Tiến / -Lùi (m)
          - sway_m: +Dạt phải / -Dạt trái (m)
          - heave_m: +Nổi lên / -Lặn xuống (m)
        """
        self._task_type = AutonomousTaskType.RELATIVE_MOVE
        self._is_active = True
        self._start_time = time.time()
        self._timeout_s = 40.0

        # Chuyển đổi Body frame sang NED World frame dựa vào heading
        hdg_rad = math.radians(current_heading_deg)
        cos_h = math.cos(hdg_rad)
        sin_h = math.sin(hdg_rad)

        dx_ned = surge_m * cos_h - sway_m * sin_h
        dy_ned = surge_m * sin_h + sway_m * cos_h
        dz_ned = -heave_m  # NED: Z hướng xuống

        curr_x, curr_y, curr_z = current_pos_ned[0], current_pos_ned[1], current_pos_ned[2]
        self._target_pos_ned = [curr_x + dx_ned, curr_y + dy_ned, curr_z + dz_ned]

        dir_desc = []
        if abs(surge_m) > 0.1:
            dir_desc.append(f"{'Tiến' if surge_m > 0 else 'Lùi'} {abs(surge_m):.1f}m")
        if abs(sway_m) > 0.1:
            dir_desc.append(f"{'Dạt phải' if sway_m > 0 else 'Dạt trái'} {abs(sway_m):.1f}m")
        if abs(heave_m) > 0.1:
            dir_desc.append(f"{'Nổi' if heave_m > 0 else 'Lặn'} {abs(heave_m):.1f}m")

        self._status_text = f"AUTO: Di chuyển {' & '.join(dir_desc)}"
        print(f"[AutoPilot] Started RELATIVE_MOVE -> Target NED: {self._target_pos_ned}")
        return self._status_text

    def start_circle_orbit(self, radius_m: float, current_pos_ned: list, speed_mps: float = 0.4) -> str:
        """Kích hoạt bài bay lượn vòng tròn bán kính R mét quanh tâm."""
        self._task_type = AutonomousTaskType.CIRCLE_ORBIT
        self._is_active = True
        self._start_time = time.time()
        self._timeout_s = 120.0
        self._circle_radius = max(1.0, float(radius_m))
        self._circle_speed = speed_mps

        # Tâm vòng tròn đặt ở phía bên phải vị trí hiện tại
        curr_x, curr_y = current_pos_ned[0], current_pos_ned[1]
        self._circle_center = [curr_x, curr_y + self._circle_radius]
        self._circle_angle = -math.pi / 2.0

        self._status_text = f"AUTO: Bay lượn vòng tròn bán kính {self._circle_radius:.1f}m"
        print(f"[AutoPilot] Started CIRCLE_ORBIT -> Center: {self._circle_center}, Radius: {self._circle_radius}m")
        return self._status_text

    def start_yaw_scan_360(self, current_heading_deg: float) -> str:
        """Kích hoạt xoay quét 360 độ kiểm tra xung quanh."""
        self._task_type = AutonomousTaskType.YAW_SCAN_360
        self._is_active = True
        self._start_time = time.time()
        self._timeout_s = 40.0
        self._scan_start_yaw = current_heading_deg
        self._scan_accum_yaw = 0.0

        self._status_text = "AUTO: Xoay tròn 360° quét toàn cảnh xung quanh"
        print(f"[AutoPilot] Started YAW_SCAN_360 from heading: {current_heading_deg:.1f}°")
        return self._status_text

    def start_rth(self, current_pos_ned: list) -> str:
        """Kích hoạt tự động quay về điểm xuất phát (0, 0)."""
        self._task_type = AutonomousTaskType.RTH
        self._is_active = True
        self._start_time = time.time()
        self._timeout_s = 90.0
        self._target_pos_ned = [0.0, 0.0, current_pos_ned[2]]

        self._status_text = "AUTO: Đang tự động quay về gốc xuất phát (RTH)"
        print(f"[AutoPilot] Started RETURN_TO_HOME (RTH)")
        return self._status_text

    def stop_all(self):
        """Hủy toàn bộ chế độ bay tự động và dừng hẳn robot."""
        self._is_active = False
        self._task_type = AutonomousTaskType.NONE
        self._status_text = "STANDBY"
        print("[AutoPilot] Autonomous trajectory stopped.")

    def stop(self):
        """Alias for stop_all."""
        self.stop_all()

    # ──────────────────────────────────────────────────────────
    # 60Hz AUTOPILOT STEP LOOP
    # ──────────────────────────────────────────────────────────
    def update_step(
        self,
        dt: float,
        current_pos_ned: list,
        current_depth_m: float,
        current_heading_deg: float
    ) -> Tuple[bool, Dict[str, float]]:
        """
        Tính toán lệnh điều khiển vòng lặp kín 60Hz.
        Trả về: (is_active, {'surge': float, 'sway': float, 'heave': float, 'yaw': float})
        """
        if not self._is_active:
            return False, {"surge": 0.0, "sway": 0.0, "heave": 0.0, "yaw": 0.0}

        # Check Timeout
        if time.time() - self._start_time > self._timeout_s:
            print(f"[AutoPilot] Task {self._task_type} reached timeout. Auto completing.")
            self.stop_all()
            return False, {"surge": 0.0, "sway": 0.0, "heave": 0.0, "yaw": 0.0}

        ctrl = {"surge": 0.0, "sway": 0.0, "heave": 0.0, "yaw": 0.0}

        # ── 1. GOTO DEPTH ─────────────────────────────────────
        if self._task_type == AutonomousTaskType.GOTO_DEPTH:
            err_depth = self._target_depth - current_depth_m  # +: cần lặn xuống, -: cần nổi lên
            if abs(err_depth) < 0.10:
                print(f"[AutoPilot] Reached target depth {self._target_depth:.2f}m!")
                self.stop_all()
                return False, ctrl

            self._depth_integral += err_depth * dt
            self._depth_integral = max(-1.0, min(1.0, self._depth_integral))

            heave_cmd = self._kp_depth * err_depth + self._ki_depth * self._depth_integral
            # In GCS: heave < 0 là lặn xuống, heave > 0 là nổi lên
            ctrl["heave"] = max(-0.7, min(0.7, -heave_cmd))

        # ── 2. RELATIVE MOVE & RTH ────────────────────────────
        elif self._task_type in (AutonomousTaskType.RELATIVE_MOVE, AutonomousTaskType.RTH):
            dx_ned = self._target_pos_ned[0] - current_pos_ned[0]
            dy_ned = self._target_pos_ned[1] - current_pos_ned[1]
            dist_horiz = math.sqrt(dx_ned**2 + dy_ned**2)

            # Chuyển sai số NED sang Body Frame của tàu
            hdg_rad = math.radians(current_heading_deg)
            surge_err = dx_ned * math.cos(hdg_rad) + dy_ned * math.sin(hdg_rad)
            sway_err = -dx_ned * math.sin(hdg_rad) + dy_ned * math.cos(hdg_rad)

            if dist_horiz < 0.20:
                print(f"[AutoPilot] Reached target position! (dist={dist_horiz:.2f}m)")
                self.stop_all()
                return False, ctrl

            ctrl["surge"] = max(-0.6, min(0.6, self._kp_pos * surge_err))
            ctrl["sway"] = max(-0.5, min(0.5, self._kp_pos * sway_err))

        # ── 3. CIRCLE ORBIT ───────────────────────────────────
        elif self._task_type == AutonomousTaskType.CIRCLE_ORBIT:
            # Tăng góc quay theo vận tốc góc omega = v / R
            omega = self._circle_speed / self._circle_radius
            self._circle_angle += omega * dt

            # Vị trí mục tiêu trên cung tròn
            target_x = self._circle_center[0] + self._circle_radius * math.cos(self._circle_angle)
            target_y = self._circle_center[1] + self._circle_radius * math.sin(self._circle_angle)

            dx = target_x - current_pos_ned[0]
            dy = target_y - current_pos_ned[1]

            hdg_rad = math.radians(current_heading_deg)
            surge_err = dx * math.cos(hdg_rad) + dy * math.sin(hdg_rad)
            sway_err = -dx * math.sin(hdg_rad) + dy * math.cos(hdg_rad)

            ctrl["surge"] = max(0.2, min(0.7, 0.4 + self._kp_pos * surge_err))
            ctrl["sway"] = max(-0.4, min(0.4, self._kp_pos * sway_err))
            # Hướng mũi tàu tiếp tuyến với đường tròn
            desired_yaw_deg = math.degrees(self._circle_angle + math.pi / 2.0) % 360.0
            yaw_err = (desired_yaw_deg - current_heading_deg + 180.0) % 360.0 - 180.0
            ctrl["yaw"] = max(-0.5, min(0.5, self._kp_yaw * yaw_err))

        # ── 4. YAW SCAN 360 ───────────────────────────────────
        elif self._task_type == AutonomousTaskType.YAW_SCAN_360:
            ctrl["yaw"] = 0.45  # Tốc độ quay đều ~20 deg/s
            self._scan_accum_yaw += 20.0 * dt
            if self._scan_accum_yaw >= 360.0:
                print("[AutoPilot] 360-degree scan complete!")
                self.stop_all()
                return False, {"surge": 0.0, "sway": 0.0, "heave": 0.0, "yaw": 0.0}

        return True, ctrl
