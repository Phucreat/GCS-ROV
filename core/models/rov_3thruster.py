"""
rov_3thruster.py - Model ROV 3 Động Cơ (Wedge Configuration)
=============================================================
Cấu hình gọn nhẹ:
  - 2 thruster nằm ngang song song: Surge (tiến/lùi) + Yaw (xoay)
  - 1 thruster thẳng đứng ở giữa: Heave (lên/xuống)
  → Không có Sway (sang ngang), Roll, Pitch độc lập

Sơ đồ nhìn từ trên xuống (Top View):
     T1 (Port, 0°)
     ←══════════╗
         ROV    ║  (Wedge shape)
     ←══════════╝
     T2 (Starboard, 0°)

     T3 (Center, Vertical Up ↑)
"""
import numpy as np
from .base_rov import BaseROVModel


class ROV3ThrusterModel(BaseROVModel):

    # ============================================================
    # --- THÔNG SỐ VẬT LÝ ---
    # ============================================================
    DISPLAY_NAME    = "3DC - 3 Thruster (Wedge)"
    MASS            = 7.5           # kg (nhẹ hơn phiên bản 6 thruster)
    HALF_EXTENTS    = [0.20, 0.15, 0.10]    # m (nhỏ hơn)
    CB_OFFSET_Z     = 0.06          # m
    BUOYANCY_FACTOR = 1.015
    MAX_THRUST      = 20.0          # N (thruster nhỏ hơn)

    DRAG_LINEAR     = np.array([18.0, 28.0, 35.0])
    DRAG_QUADRATIC  = np.array([25.0, 38.0, 45.0])
    DRAG_ROT_LINEAR = np.array([4.0, 6.0, 5.0])
    DRAG_ROT_QUAD   = np.array([7.0, 9.0, 8.0])

    # ============================================================
    # --- THRUSTER LAYOUT ---
    # ============================================================
    def _build_thrusters(self) -> list:
        """
        3-Thruster wedge configuration.
        Toạ độ thân tàu: X=Forward, Y=Left, Z=Up
        """
        return [
            # T1: Port Horizontal → đẩy Forward (trái thân tàu)
            {"pos": [0.0, +0.13, 0.0], "dir": [1.0, 0.0, 0.0]},
            # T2: Starboard Horizontal → đẩy Forward (phải thân tàu)
            {"pos": [0.0, -0.13, 0.0], "dir": [1.0, 0.0, 0.0]},
            # T3: Center Vertical → đẩy lên/xuống
            {"pos": [-0.05, 0.0, 0.0], "dir": [0.0, 0.0, 1.0]},
        ]

    # ============================================================
    # --- CẤU HÌNH VẼ 3D ---
    # ============================================================
    def get_visual_config(self) -> dict:
        """
        Trả về dict mô tả cách GLROVWidget dựng mô hình 3D.
        """
        return {
            "version": "3-thruster",
            "chassis": {
                # Hình lăng trụ tam giác (wedge) → GLROVWidget xử lý
                "type": "wedge",
                "length": 0.40,
                "width": 0.30,
                "height": 0.18,
                "color": (0.12, 0.22, 0.32, 0.8),
                "edge_color": (0.0, 0.8, 1.0, 0.5),
            },
            "horizontal_thrusters": [
                {"pos": [0.0, +0.14, 0.0], "angle_deg": 0},
                {"pos": [0.0, -0.14, 0.0], "angle_deg": 0},
            ],
            "vertical_thrusters": [
                {"pos": [-0.05, 0.0, 0.0]},
            ],
            "headlights": [
                {"pos": [0.18, 0.0, 0.0]},    # 1 đèn ở chính giữa mũi
            ],
        }
