"""
thruster_model.py - Mo hinh luc day Blue Robotics T200
=======================================================
Mô phỏng đặc tính lực đẩy thực tế của T200 thruster.

Thong so thuc te T200:
  - Luc day toi da thuan: 5.1 kgf (~50N) tai 20V, 20.7A
  - Luc day toi da nghich: 3.7 kgf (~36N) tai 20V, 15.9A
  - Dead-band: ~5% duty cycle
  - Time constant: ~100ms (motor inertia)
"""
import math
import time
from dataclasses import dataclass, field
from typing import List, Tuple


# ─────────────────────────────────────────
# MÔ HÌNH MỘT THRUSTER T200
# ─────────────────────────────────────────
@dataclass
class T200Model:
    """
    Mot thruster Blue Robotics T200.
    PWM input: 1100-1900 µs (1500 = stop)
    Thrust: -36N ~ +50N
    """
    # Vi tri trong body frame (m)
    pos_x: float = 0.0
    pos_y: float = 0.0
    pos_z: float = 0.0
    # Huong luc day (unit vector)
    dir_x: float = 0.0
    dir_y: float = 0.0
    dir_z: float = -1.0   # mac dinh huong xuong (vertical)
    # Canh tay don xoay (m)
    arm_x: float = 0.0
    arm_y: float = 0.0

    # Trang thai
    _pwm: float = 1500.0         # µs hien tai
    _thrust_n: float = 0.0       # N hien tai
    _time_const: float = 0.08    # s (motor time constant ~80ms)
    _last_t: float = field(default_factory=time.monotonic)

    def set_pwm(self, pwm_us: float):
        """Dat PWM (1100–1900 µs, 1500=stop)."""
        self._pwm = max(1100.0, min(1900.0, pwm_us))

    def update(self) -> Tuple[float, float]:
        """
        Cap nhat trang thai thruster.
        Returns: (thrust_n, current_a)
        """
        now = time.monotonic()
        dt = now - self._last_t
        self._last_t = now

        # Chuyen PWM -> thrust target (N)
        target = self._pwm_to_thrust(self._pwm)

        # Loc first-order (dong co co quan tinh)
        alpha = 1.0 - math.exp(-dt / self._time_const)
        self._thrust_n += alpha * (target - self._thrust_n)

        # Tinh dong dien tu luc day
        current_a = self._thrust_to_current(self._thrust_n)
        return self._thrust_n, current_a

    @staticmethod
    def _pwm_to_thrust(pwm_us: float) -> float:
        """
        Chuyen PWM sang luc day (N).
        Dua tren du lieu thu nghiem T200 cua Blue Robotics.
        Dead-band: 1460-1540 µs
        """
        if 1460 <= pwm_us <= 1540:
            return 0.0   # dead-band

        if pwm_us > 1540:
            # Chieu thuan: 1540→1900 µs = 0→50N
            t = (pwm_us - 1540) / 360.0
            return t * 50.0 * (2 - t)   # curve phi tuyen

        else:
            # Chieu nghich: 1460→1100 µs = 0→-36N
            t = (1460 - pwm_us) / 360.0
            return -t * 36.0 * (2 - t)

    @staticmethod
    def _thrust_to_current(thrust_n: float) -> float:
        """
        Uoc tinh dong dien tu luc day.
        Xap xi tuyen tinh: 0N→1A (khong tai), 50N→20.7A.
        """
        if thrust_n >= 0:
            return max(0.8, 1.0 + thrust_n * 0.39)
        else:
            return max(0.8, 1.0 + abs(thrust_n) * 0.42)


# ─────────────────────────────────────────
# MA TRẬN THRUSTER — BlueROV2 Heavy (6T)
# ─────────────────────────────────────────
class ThrusterMatrix6DOF:
    """
    6-thruster configuration: BlueROV2 Heavy / ROV 6DC Vectored.

    Layout (nhin tu tren xuong):
       T1(FL) ↖  T2(FR) ↗
                ·
       T3(RL) ↙  T4(RR) ↘
          T5(↓)    T6(↓)   ← vertical

    T1-T4: horizontal, goc 45° → Surge+Sway+Yaw
    T5-T6: vertical             → Heave
    """
    def __init__(self):
        # Goc 45 do
        a = math.cos(math.radians(45))
        b = math.sin(math.radians(45))

        # [Fx, Fy, Fz, Mx, My, Mz] per thruster
        # Convention: X=Bac(tien), Y=Dong(phai), Z=Xuong
        self.tcm = [
            # T1 Front-Left  (huong 45° = phai-truoc)
            [ a,  b, 0,  0.18*b, -0.18*a, -0.20],
            # T2 Front-Right (huong -45° = phai-lui)
            [ a, -b, 0, -0.18*b, -0.18*a,  0.20],
            # T3 Rear-Left   (huong -45° = trai-truoc)
            [-a,  b, 0,  0.18*b,  0.18*a,  0.20],
            # T4 Rear-Right  (huong 45° = trai-lui)
            [-a, -b, 0, -0.18*b,  0.18*a, -0.20],
            # T5 Vertical Left
            [0, 0, -1, -0.15, 0, 0],
            # T6 Vertical Right
            [0, 0, -1,  0.15, 0, 0],
        ]
        # Pseudo-inverse de giai nguoc
        import numpy as np
        M = np.array(self.tcm).T   # shape (6,6)
        self._inv = np.linalg.pinv(M)

    def control_to_pwm(self, surge: float, sway: float, heave: float,
                       roll: float, pitch: float, yaw: float) -> List[float]:
        """
        Chuyen vector dieu khien sang PWM 6 thruster.
        Inputs: -1.0 to +1.0 (normalized)
        Returns: list 6 gia tri PWM µs [1100–1900]
        """
        import numpy as np
        desire = np.array([surge, sway, heave, roll, pitch, yaw])
        # Giai he phuong trinh: TCM * T = desire
        thrusts = self._inv @ desire   # N (normalized)
        # Clamp [-1, +1]
        thrusts = np.clip(thrusts, -1.0, 1.0)
        # Chuyen sang PWM
        pwms = []
        for t in thrusts:
            if t >= 0:
                pwm = 1540 + t * 360
            else:
                pwm = 1460 + t * 360
            pwms.append(float(pwm))
        return pwms

    def manual_control_to_pwm(self, x: int, y: int, z: int, r: int) -> List[float]:
        """
        Tu MANUAL_CONTROL MAVLink (-1000~1000, z: 0~1000)
        Returns: 6 gia tri PWM
        """
        surge  =  x / 1000.0
        sway   =  y / 1000.0
        heave  = (z - 500) / 500.0   # 500 = neutral
        yaw    =  r / 1000.0
        return self.control_to_pwm(surge, sway, heave, 0, 0, yaw)


# ─────────────────────────────────────────
# MOT DUNG CU TINH DONG DIEN TONG
# ─────────────────────────────────────────
def total_current_from_pwms(pwms: List[float]) -> float:
    """Tinh tong dong dien 6 thruster tu list PWM."""
    total = 0.0
    for pwm in pwms:
        t = T200Model._pwm_to_thrust(pwm)
        total += T200Model._thrust_to_current(t)
    return total
