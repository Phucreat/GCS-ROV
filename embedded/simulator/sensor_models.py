"""
sensor_models.py - Mo hinh vat ly cam bien ROV
================================================
Sinh du lieu cam bien thuc te voi:
  - Noise Gaussian
  - Drift theo thoi gian (IMU bias)
  - Hieu ung nhiet do
  - Dead-band, saturation
"""
import math
import random
import time
from dataclasses import dataclass, field
from typing import Tuple


# ─────────────────────────────────────────
# IMU MODEL — MPU6050 / ICM-42688-P
# ─────────────────────────────────────────
@dataclass
class IMUModel:
    """
    Mo hinh IMU 6-DOF voi noise + drift.
    Thong so tuong duong ICM-42688-P tren STM32F7.
    """
    # Gyro: noise ±0.01 rad/s, bias drift 0.0001 rad/s/s
    gyro_noise_std:  float = 0.005        # rad/s
    gyro_bias_drift: float = 0.0001       # rad/s per second (Allan deviation)

    # Accel: noise ±0.02 m/s², bias drift 0.001 m/s²/s
    accel_noise_std:  float = 0.02        # m/s²
    accel_bias_drift: float = 0.001       # m/s² per second

    # Trang thai bias hien tai
    _gyro_bias:  list = field(default_factory=lambda: [0.0, 0.0, 0.0])
    _accel_bias: list = field(default_factory=lambda: [0.0, 0.0, 0.0])
    _last_t: float = field(default_factory=time.monotonic)

    def update_bias(self):
        """Cap nhat bias drift theo thoi gian."""
        now = time.monotonic()
        dt = now - self._last_t
        self._last_t = now
        for i in range(3):
            self._gyro_bias[i]  += random.gauss(0, self.gyro_bias_drift * dt)
            self._accel_bias[i] += random.gauss(0, self.accel_bias_drift * dt)
            # Clamp bias de khong drift vo han
            self._gyro_bias[i]  = max(-0.05, min(0.05, self._gyro_bias[i]))
            self._accel_bias[i] = max(-0.5,  min(0.5,  self._accel_bias[i]))

    def measure_gyro(self, true_rates: Tuple[float,float,float]) -> Tuple[float,float,float]:
        """
        Tra ve do do gyro voi noise + bias.
        true_rates: (p, q, r) rad/s thuc te
        Returns: (p, q, r) do duoc (rad/s)
        """
        self.update_bias()
        return tuple(
            true_rates[i]
            + self._gyro_bias[i]
            + random.gauss(0, self.gyro_noise_std)
            for i in range(3)
        )

    def measure_accel(self, true_accel: Tuple[float,float,float],
                      roll: float, pitch: float) -> Tuple[float,float,float]:
        """
        Tra ve do do accel voi gravity + noise + bias.
        true_accel: gia toc thuc (khuyet gravity), (ax, ay, az) m/s²
        roll, pitch: rad — can de tinh huong gravity
        """
        self.update_bias()
        g = 9.80665
        # Gravity trong body frame
        gx = -g * math.sin(pitch)
        gy =  g * math.cos(pitch) * math.sin(roll)
        gz =  g * math.cos(pitch) * math.cos(roll)

        return tuple(
            true_accel[i]
            + [gx, gy, gz][i]
            + self._accel_bias[i]
            + random.gauss(0, self.accel_noise_std)
            for i in range(3)
        )


# ─────────────────────────────────────────
# PRESSURE / DEPTH SENSOR — Bar30 / MS5837
# ─────────────────────────────────────────
@dataclass
class PressureSensorModel:
    """
    Mo hinh cam bien ap suat nuoc Blue Robotics Bar30.
    Do chinh xac: ±2 mm nuoc, noise ~0.01 hPa.
    """
    noise_std:     float = 0.02      # hPa noise
    temp_coeff:    float = 0.001     # hPa/°C thay doi theo nhiet do
    p_atm:         float = 1013.25   # hPa ap suat khi quyen
    rho_water:     float = 1025.0    # kg/m³ nuoc bien
    g:             float = 9.80665   # m/s²

    def depth_to_pressure(self, depth_m: float, temp_c: float = 25.0) -> float:
        """
        Tinh ap suat tuyet doi tu do sau.
        depth_m: do sau (m, duong = xuong sau)
        Returns: press_abs (hPa)
        """
        p_hydro = self.rho_water * self.g * depth_m / 100.0  # Pa → hPa
        temp_effect = (temp_c - 25.0) * self.temp_coeff
        noise = random.gauss(0, self.noise_std)
        return self.p_atm + p_hydro + temp_effect + noise

    def measure(self, depth_m: float, temp_c: float = 25.0) -> Tuple[float, float]:
        """
        Returns: (press_abs_hpa, temperature_c) voi noise
        """
        press = self.depth_to_pressure(depth_m, temp_c)
        temp_measured = temp_c + random.gauss(0, 0.1)  # ±0.1°C noise
        return press, temp_measured


# ─────────────────────────────────────────
# BATTERY MODEL — Lithium Ion 4S
# ─────────────────────────────────────────
@dataclass
class BatteryModel:
    """
    Mo hinh pin Li-Ion 4S (14.8V nominal).
    Dung luong 15.6Ah, dung cho Blue Robotics 4S.
    """
    capacity_ah:   float = 15.6      # Ah
    v_full:        float = 16.8      # V (100%)
    v_empty:       float = 12.0      # V (0%)
    v_nominal:     float = 14.8      # V

    _charge_ah:    float = field(default=15.6)  # Ah hien tai
    _last_t:       float = field(default_factory=time.monotonic)

    def update(self, current_a: float) -> Tuple[float, float, int]:
        """
        Cap nhat trang thai pin.
        current_a: dong dien tieu thu (A)
        Returns: (voltage_v, current_a, percent)
        """
        now = time.monotonic()
        dt = now - self._last_t
        self._last_t = now

        # Xa pin
        self._charge_ah = max(0.0, self._charge_ah - current_a * dt / 3600.0)
        soc = self._charge_ah / self.capacity_ah  # 0.0–1.0

        # Mo hinh dien ap phi tuyen (xap xi OCV curve Li-Ion)
        if soc > 0.8:
            v = self.v_full - (1 - soc) * 1.0
        elif soc > 0.2:
            v = self.v_nominal + (soc - 0.5) * 3.0
        else:
            v = self.v_empty + soc * 10.0

        # Voltage sag khi tai cao
        v -= current_a * 0.05   # 50mΩ internal resistance

        # Noise nho
        v += random.gauss(0, 0.01)

        percent = max(0, min(100, int(soc * 100)))
        return max(self.v_empty, v), current_a + random.gauss(0, 0.05), percent

    def reset(self):
        """Sac day pin."""
        self._charge_ah = self.capacity_ah
        self._last_t = time.monotonic()


# ─────────────────────────────────────────
# WATER TEMPERATURE MODEL
# ─────────────────────────────────────────
class WaterTempModel:
    """
    Mo hinh nhiet do nuoc bien theo do sau.
    Thermocline: 20°C mat nuoc → 10°C o 50m.
    """
    def __init__(self, surface_temp_c: float = 27.0):
        self.surface_temp = surface_temp_c

    def measure(self, depth_m: float) -> float:
        """Tra ve nhiet do nuoc (°C) theo do sau."""
        # Giam ~0.2°C/m trong 20m dau
        temp = self.surface_temp - min(depth_m * 0.2, 10.0)
        return temp + random.gauss(0, 0.05)


# ─────────────────────────────────────────
# LEAK SENSOR MODEL
# ─────────────────────────────────────────
class LeakSensorModel:
    """Cam bien ro nuoc Blue Robotics."""
    def __init__(self, leak_probability: float = 0.0):
        self.leak_prob = leak_probability  # 0.0 = khong ro

    def measure(self) -> float:
        """Returns: 0.0=OK, 1.0=RO NUOC!"""
        return 1.0 if random.random() < self.leak_prob else 0.0
