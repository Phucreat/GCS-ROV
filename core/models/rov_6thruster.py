"""
rov_6thruster.py - Model ROV 6 Động Cơ (Vectored Configuration)
================================================================
Cấu hình BlueROV2 Heavy cải tiến:
  - 4 thruster nằm ngang, đặt góc 45°: cho phép Surge, Sway, Yaw
  - 2 thruster thẳng đứng: cho phép Heave, Roll, Pitch

Sơ đồ nhìn từ trên xuống (Top View):
    T1 (FR, 45°)    T2 (FL, -45°)
           ┌───────────┐
           │           │
           │    ROV    │
           │           │
           └───────────┘
    T3 (RR,-135°)  T4 (RL, 135°)

    T5 (Vert Right, Up)   T6 (Vert Left, Up)
"""
import numpy as np
from .base_rov import BaseROVModel


class ROV6ThrusterModel(BaseROVModel):

    # ============================================================
    # --- THÔNG SỐ VẬT LÝ ---
    # ============================================================
    DISPLAY_NAME    = "6DC - 6 Thruster (Vectored)"
    MASS            = 11.5          # kg
    HALF_EXTENTS    = [0.225, 0.17, 0.125]  # m
    CB_OFFSET_Z     = 0.08          # m
    BUOYANCY_FACTOR = 1.02
    MAX_THRUST      = 30.0          # N

    DRAG_LINEAR     = np.array([25.0, 35.0, 45.0])
    DRAG_QUADRATIC  = np.array([35.0, 45.0, 55.0])
    DRAG_ROT_LINEAR = np.array([6.0, 8.0, 8.0])
    DRAG_ROT_QUAD   = np.array([10.0, 12.0, 12.0])

    # ============================================================
    # --- THRUSTER LAYOUT ---
    # ============================================================
    def _build_thrusters(self) -> list:
        """
        6-Thruster vectored configuration.
        Toạ độ thân tàu: X=Forward, Y=Left, Z=Up
        """
        s = 0.7071  # sin/cos(45°) = sqrt(2)/2
        return [
            # --- HORIZONTAL THRUSTERS (góc 45°, mặt phẳng XY) ---
            # T1: Front-Right  → đẩy Forward + Port  (vector [+s, +s, 0])
            {"pos": [ 0.15, -0.15, 0.0], "dir": [+s, +s, 0.0]},
            # T2: Front-Left   → đẩy Forward + Starboard ([+s, -s, 0])
            {"pos": [ 0.15, +0.15, 0.0], "dir": [+s, -s, 0.0]},
            # T3: Rear-Right   → đẩy Backward + Port  ([-s, +s, 0])
            {"pos": [-0.15, -0.15, 0.0], "dir": [-s, +s, 0.0]},
            # T4: Rear-Left    → đẩy Backward + Starboard ([-s, -s, 0])
            {"pos": [-0.15, +0.15, 0.0], "dir": [-s, -s, 0.0]},
            # --- VERTICAL THRUSTERS (mặt phẳng Z) ---
            # T5: Vertical Starboard → lên/xuống ở phải
            {"pos": [0.0, -0.12, 0.05], "dir": [0.0, 0.0, 1.0]},
            # T6: Vertical Port      → lên/xuống ở trái
            {"pos": [0.0, +0.12, 0.05], "dir": [0.0, 0.0, 1.0]},
        ]

    # ============================================================
    # --- CẤU HÌNH VẼ 3D ---
    # ============================================================
    def get_visual_config(self) -> dict:
        """
        Trả về dict mô tả cách GLROVWidget dựng mô hình 3D.
        Các key được GLROVWidget xử lý.
        """
        return {
            "version": "6-thruster",
            "chassis": {
                "size": [0.45, 0.34, 0.22],
                "color": (0.10, 0.15, 0.25, 0.85),
                "edge_color": (0.0, 0.8, 1.0, 0.4),
            },
            "foam_block": {
                "size": [0.48, 0.36, 0.05],
                "offset": [0.0, 0.0, 0.13],
                "color": (0.92, 0.92, 0.95, 0.95),
                "edge_color": (0.0, 0.8, 1.0, 0.5),
            },
            "horizontal_thrusters": [
                {"pos": [ 0.15, -0.15, 0.0], "angle_deg": 45},
                {"pos": [ 0.15, +0.15, 0.0], "angle_deg": -45},
                {"pos": [-0.15, -0.15, 0.0], "angle_deg": -135},
                {"pos": [-0.15, +0.15, 0.0], "angle_deg": 135},
            ],
            "vertical_thrusters": [
                {"pos": [0.0, -0.12, 0.05]},
                {"pos": [0.0, +0.12, 0.05]},
            ],
            "headlights": [
                {"pos": [0.21, -0.08, -0.04]},
                {"pos": [0.21, +0.08, -0.04]},
            ],
        }
