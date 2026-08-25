"""
pyvista_3d_widget.py - Physically-Based Rendering (PBR) 3D Subsea Digital Twin Widget
=====================================================================================
Built with PyVista and pyvistaqt (VTK 9.6 backend) for PyQt6.

Nâng cấp đồ hoạ Sáng Rõ & Trực Quan:
  - Ánh sáng 4 điểm (Key, Fill, Rim, Ambient) + Đèn pha LED công suất cao rọi sáng rõ nét mọi góc cạnh của ROV.
  - Phối màu đại dương Luminous Oceanic Blue chuyển sắc sâu thẳm, tương phản cao, cực kỳ dễ quan sát.
  - Vật liệu PBR Subsea Safety Yellow & Carbon siêu mịn (Smooth Shading, không sọc lưới, ánh kim loại chân thực).
  - Tối ưu 100% không gian hiển thị (bỏ thanh toolbar theo yêu cầu, điều khiển hoàn toàn qua chuột phải).
  - 4 Chế độ Camera mượt mà: ISOMETRIC (Bao quát 360° thấy rõ quay), CHASE (Bám đuôi), MAP (Top-down), MANUAL (Tự do).
"""

from __future__ import annotations

import math
import os
from typing import Optional

import numpy as np
import pyvista as pv
from pyvistaqt import QtInteractor
import vtk

from PyQt6 import QtCore, QtGui, QtWidgets


# ═══════════════════════════════════════════════════════════════
# CAMERA MODES
# ═══════════════════════════════════════════════════════════════
class CameraMode:
    ISOMETRIC = 0  # Góc nhìn 3D bao quát (thấy rõ xoay Yaw trái/phải)
    CHASE     = 1  # Bám sau đuôi với độ trễ mượt mà
    ORBIT     = 2  # Tự động xoay quanh tàu
    MAP       = 3  # Nhìn thẳng từ trên xuống
    MANUAL    = 4  # Tự do điều khiển bằng chuột
    LABELS = {
        ISOMETRIC: "ISOMETRIC",
        CHASE: "CHASE CAM",
        ORBIT: "ORBIT",
        MAP: "MAP",
        MANUAL: "MANUAL"
    }


# ═══════════════════════════════════════════════════════════════
# HUD OVERLAY WIDGET (QPainter HUD on top of PyVista canvas)
# ═══════════════════════════════════════════════════════════════
class _HUDOverlay(QtWidgets.QWidget):
    """QPainter HUD tinh gọn, trong suốt phủ lên 3D canvas."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAutoFillBackground(False)

        self._depth     = 0.0
        self._heading   = 0.0
        self._pos       = [0.0, 0.0, 0.0]
        self._speed     = 0.0
        self._cam_mode  = "ISOMETRIC"
        self._roll      = 0.0
        self._pitch     = 0.0
        self._dist_home = 0.0
        self._map_name  = "RESERVOIR"
        self._thrust    = 0.0
        self._user_ctrl = False

        self._font_xs = QtGui.QFont("Consolas", 8)
        self._font_sm = QtGui.QFont("Consolas", 9)
        self._font_md = QtGui.QFont("Consolas", 10, QtGui.QFont.Weight.Bold)
        self._font_lg = QtGui.QFont("Consolas", 13, QtGui.QFont.Weight.Bold)

    def update_data(self, **kw):
        for k, v in kw.items():
            attr = f"_{k}"
            if hasattr(self, attr):
                setattr(self, attr, v)
        self.update()

    def paintEvent(self, event):
        if self.width() < 10 or self.height() < 10:
            return
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()

        # ── 1. Thước đo độ sâu (Depth bar bên trái) ──────────────
        bx, by = 10, 14
        bw, bh = 12, H - 70
        max_d  = 50.0

        p.setPen(QtCore.Qt.PenStyle.NoPen)
        p.setBrush(QtGui.QColor(0, 15, 30, 130))
        p.drawRoundedRect(bx - 3, by - 10, bw + 42, bh + 32, 6, 6)

        p.setBrush(QtGui.QColor(4, 28, 52, 160))
        p.drawRoundedRect(bx, by, bw, bh, 3, 3)

        grad = QtGui.QLinearGradient(bx, by, bx, by + bh)
        grad.setColorAt(0.0, QtGui.QColor(0, 240, 255, 240))
        grad.setColorAt(0.5, QtGui.QColor(0, 150, 230, 220))
        grad.setColorAt(1.0, QtGui.QColor(0, 60, 140, 200))
        p.setBrush(QtGui.QBrush(grad))
        ratio = min(abs(self._depth) / max_d, 1.0)
        fill  = int(bh * ratio)
        if fill > 0:
            p.drawRoundedRect(bx, by + bh - fill, bw, fill, 3, 3)

        p.setFont(self._font_xs)
        for dm in range(0, int(max_d) + 1, 10):
            ty = by + int(bh * dm / max_d)
            p.setPen(QtGui.QPen(QtGui.QColor(0, 200, 255, 140), 1))
            p.drawLine(bx + bw, ty, bx + bw + 4, ty)
            p.setPen(QtGui.QColor(120, 220, 255, 160))
            p.drawText(bx + bw + 6, ty + 4, f"{dm}m")

        p.setPen(QtGui.QColor(0, 245, 255, 250))
        p.setFont(self._font_md)
        p.drawText(bx - 2, by + bh + 16, f"{abs(self._depth):.1f}m")

        # ── 2. Panel thông số viễn trắc (Trái trên) ──────────────
        px, py_ = 54, 14
        pw, ph  = 185, 108

        p.setPen(QtCore.Qt.PenStyle.NoPen)
        p.setBrush(QtGui.QColor(3, 16, 32, 140))
        p.drawRoundedRect(px, py_, pw, ph, 8, 8)
        p.setPen(QtGui.QPen(QtGui.QColor(0, 180, 240, 110), 1))
        p.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(px, py_, pw, ph, 8, 8)

        p.setPen(QtGui.QColor(0, 240, 255, 250))
        p.setFont(self._font_md)
        p.drawText(px + 10, py_ + 20, f"HDG  {self._heading:05.1f}°")

        p.setFont(self._font_sm)
        p.setPen(QtGui.QColor(70, 250, 220, 230))
        p.drawText(px + 10, py_ + 38, f"X  {self._pos[0]:+7.2f} m")
        p.drawText(px + 10, py_ + 54, f"Y  {self._pos[1]:+7.2f} m")
        p.drawText(px + 10, py_ + 70, f"Z  {self._pos[2]:+7.2f} m")

        p.setFont(self._font_xs)
        p.setPen(QtGui.QColor(170, 225, 250, 200))
        p.drawText(px + 10, py_ + 86, f"R {self._roll:+5.1f}°  P {self._pitch:+5.1f}°")

        dh_color = (QtGui.QColor(255, 100, 100) if self._dist_home > 20 else QtGui.QColor(100, 255, 210))
        p.setPen(dh_color)
        p.drawText(px + 10, py_ + 100, f"HOME {self._dist_home:4.1f}m | THRUST {int(self._thrust*100)}%")

        # ── 3. Compass Heading Tape (Chính giữa trên đỉnh) ────────
        cw, ch = 200, 26
        cx = (W - cw) // 2
        cy = 12
        p.setPen(QtCore.Qt.PenStyle.NoPen)
        p.setBrush(QtGui.QColor(3, 14, 28, 140))
        p.drawRoundedRect(cx, cy, cw, ch, 6, 6)
        p.setPen(QtGui.QPen(QtGui.QColor(0, 180, 240, 90), 1))
        p.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(cx, cy, cw, ch, 6, 6)

        p.setPen(QtGui.QPen(QtGui.QColor(0, 240, 255, 230), 2))
        p.drawLine(cx + cw // 2, cy + 2, cx + cw // 2, cy + ch - 2)

        p.setFont(self._font_xs)
        hdg_center = self._heading
        for offset in range(-60, 61, 15):
            deg = (hdg_center + offset) % 360
            x_pos = cx + cw // 2 + int(offset * (cw / 120))
            if cx + 5 <= x_pos <= cx + cw - 5:
                cardinal = ""
                if abs(deg - 0) < 5 or abs(deg - 360) < 5: cardinal = "N"
                elif abs(deg - 90) < 5: cardinal = "E"
                elif abs(deg - 180) < 5: cardinal = "S"
                elif abs(deg - 270) < 5: cardinal = "W"

                if cardinal:
                    p.setPen(QtGui.QColor(255, 215, 0, 240))
                    p.drawText(x_pos - 4, cy + 17, cardinal)
                else:
                    p.setPen(QtGui.QColor(150, 215, 245, 170))
                    p.drawLine(x_pos, cy + 3, x_pos, cy + 8)
                    p.drawText(x_pos - 8, cy + 20, f"{int(deg)}")

        # ── 4. Speed badge (Phải dưới) ────────────────────────────
        spd = self._speed
        sc  = (QtGui.QColor(0, 240, 255) if spd < 0.5
               else QtGui.QColor(255, 210, 0) if spd < 1.5
               else QtGui.QColor(255, 80, 80))
        sw, sh = 90, 48
        sx, sy_ = W - sw - 12, H - sh - 12

        p.setPen(QtCore.Qt.PenStyle.NoPen)
        p.setBrush(QtGui.QColor(3, 14, 30, 140))
        p.drawRoundedRect(sx, sy_, sw, sh, 8, 8)
        p.setPen(QtGui.QPen(sc.darker(130), 1))
        p.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(sx, sy_, sw, sh, 8, 8)

        p.setPen(sc)
        p.setFont(self._font_lg)
        p.drawText(sx + 8, sy_ + 28, f"{spd:.2f}")
        p.setFont(self._font_xs)
        p.setPen(QtGui.QColor(160, 215, 240, 180))
        p.drawText(sx + 8, sy_ + 42, "m/s SPEED")

        # ── 5. Camera & Map Info Badge (Phải trên) ────────────────
        cam_col = (QtGui.QColor(255, 180, 0, 240) if self._user_ctrl else QtGui.QColor(0, 230, 150, 230))
        p.setFont(self._font_xs)
        p.setPen(cam_col)
        cam_text = f"CAM: MANUAL" if self._user_ctrl else f"CAM: {self._cam_mode}"
        p.drawText(W - 130, 22, cam_text)

        p.setPen(QtGui.QColor(0, 210, 255, 200))
        p.drawText(W - 130, 36, f"MAP: {self._map_name}")

        p.setPen(QtGui.QColor(120, 170, 200, 160))
        p.drawText(W - 150, 50, "[R-Click: Menu & Map]")

        p.end()


# ═══════════════════════════════════════════════════════════════
# PYVISTA PBR 3D WIDGET (PyVistaQt + VTK Backend)
# ═══════════════════════════════════════════════════════════════
class PyVista3DWidget(QtWidgets.QWidget):
    """
    Subsea 3D Digital Twin Render Widget powered by PyVista (VTK 9.6 backend).
    Implements Physically-Based Rendering (PBR), 4-point studio lighting,
    high-clarity oceanic ocean gradient, 6-DoF attitude transform,
    marine snow particles, and real-time telemetry HUD.
    """

    sig_waypoint_placed = QtCore.pyqtSignal(float, float, float)

    def __init__(self, parent=None, default_map: str = "RESERVOIR"):
        super().__init__(parent=parent)

        # ── ROV State ─────────────────────────────────────────
        self._current_pos  = np.zeros(3, np.float32)
        self._current_quat = np.array([0.0, 0.0, 0.0, 1.0], np.float32)
        self._origin       = None
        self._heading      = 0.0
        self._depth        = 0.0
        self._speed        = 0.0
        self._roll         = 0.0
        self._pitch        = 0.0
        self._thrust_level = 0.0
        self._prop_spin    = 0.0

        self._current_map_name = default_map.upper()
        self._cam_mode         = CameraMode.ISOMETRIC
        self._user_ctrl        = False
        self._orbit_yaw        = 45.0
        self._cam_damped_yaw   = 0.0
        self._cam_lerp_pos     = np.zeros(3, np.float32)

        self._traj_pts         = []
        self._traj_actor       = None
        self._traj_update_cnt  = 0

        self._rov_actors       = []
        self._propeller_actors = []
        self._particle_actor   = None
        self._env_actors       = []
        self._model_config     = None
        self._cad_file         = None

        # ── Main Layout (Full Screen Canvas, No Toolbar) ──────
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── QtInteractor manages VTK render window inside Qt ──
        self.plotter = QtInteractor(self)
        main_layout.addWidget(self.plotter.interactor)

        # ── HUD Overlay (drawn on top of 3D canvas) ───────────
        self._hud = _HUDOverlay(self)
        self._hud.setGeometry(self.rect())

        # ── Resume Camera Timer ──────────────────────────────
        self._cam_resume_timer = QtCore.QTimer(self)
        self._cam_resume_timer.setSingleShot(True)
        self._cam_resume_timer.timeout.connect(self._on_cam_resume)

        # ── Animation Timer for Propellers & Particles (30 FPS) ──
        self._anim_timer = QtCore.QTimer(self)
        self._anim_timer.timeout.connect(self._animate_tick)
        self._anim_timer.start(33)

        # ── Build Initial 3D Scene ───────────────────────────
        self._setup_scene()

        # ── Mouse Interaction Handling ───────────────────────
        self.plotter.interactor.AddObserver(vtk.vtkCommand.LeftButtonPressEvent, self._on_vtk_left_press)
        self.plotter.interactor.AddObserver(vtk.vtkCommand.LeftButtonReleaseEvent, self._on_vtk_left_release)
        self.plotter.interactor.AddObserver(vtk.vtkCommand.RightButtonPressEvent, self._on_vtk_right_press)

    # ──────────────────────────────────────────────────────────
    # SCENE SETUP & ENVIRONMENT
    # ──────────────────────────────────────────────────────────
    def _setup_scene(self):
        """Khởi tạo toàn bộ cảnh 3D PBR, ánh sáng biển sâu, và địa hình."""
        self.plotter.remove_all_lights()

        # 1. Depth Peeling & Eye Dome Lighting
        try:
            self.plotter.enable_depth_peeling()
        except Exception:
            pass
        try:
            self.plotter.enable_eye_dome_lighting()
        except Exception:
            pass

        # 2. Gradient Background & High-Clarity Studio Lighting
        self._apply_environment_preset(self._current_map_name)

        # 3. World Coordinate Axes (Compass Reference at Origin)
        self._build_world_axes()

        # 4. Marine Snow / Plankton Particle Field (200 particles)
        self._build_particle_field()

        # 5. Default Procedural Model (sẽ được thay bởi set_model)
        self._build_default_proc_model()

        # 6. Camera Initial Position
        self._reset_camera_view()
        self.plotter.render()

    def _apply_environment_preset(self, map_name: str):
        """Cấu hình màu nước, ánh sáng và địa hình đáy biển sáng rõ, sắc nét."""
        map_name = map_name.upper()
        self._current_map_name = map_name

        # Xóa các actor môi trường cũ
        for act in self._env_actors:
            try:
                self.plotter.remove_actor(act)
            except Exception:
                pass
        self._env_actors.clear()
        self.plotter.remove_all_lights()

        if map_name == "POOL":
            bg_bot = "#082a45"
            bg_top = "#145682"
            terrain_depth = -5.0
            roughness = 0.05
            terrain_color = "#3d6d8d"
            sun_color = "#e0f7ff"
            sun_intensity = 1.4
            headlight_intensity = 2.0
        elif map_name == "OFFSHORE":
            bg_bot = "#051829"
            bg_top = "#0e4166"
            terrain_depth = -18.0
            roughness = 1.6
            terrain_color = "#1a3b56"
            sun_color = "#c8f0ff"
            sun_intensity = 1.3
            headlight_intensity = 2.5
        elif map_name == "SHIPWRECK":
            bg_bot = "#031422"
            bg_top = "#0a3350"
            terrain_depth = -22.0
            roughness = 2.0
            terrain_color = "#152c3e"
            sun_color = "#b0e0f8"
            sun_intensity = 1.1
            headlight_intensity = 2.8
        else:  # RESERVOIR (default - Sáng rõ, xanh biếc đại dương)
            bg_bot = "#062035"
            bg_top = "#0f4770"
            terrain_depth = -14.0
            roughness = 0.8
            terrain_color = "#183e58"
            sun_color = "#e6f8ff"
            sun_intensity = 1.35
            headlight_intensity = 2.2

        # Gradient màu nước biển sáng rõ, tương phản cao
        self.plotter.set_background(bg_bot, top=bg_top)

        # ── 1. Key Sun Light (Ánh sáng mặt trời chiếu từ trên cao xuống) ──
        sun = pv.Light(
            position=(2.0, 2.0, 30.0),
            focal_point=(0.0, 0.0, 0.0),
            color=sun_color,
            intensity=sun_intensity,
            light_type="scene light"
        )
        self.plotter.add_light(sun)

        # ── 2. Front Fill Light (Rọi sáng mặt trước và hông ROV) ─────────
        fill = pv.Light(
            position=(12.0, -8.0, 10.0),
            focal_point=(0.0, 0.0, 0.0),
            color="#d8f4ff",
            intensity=0.85,
            light_type="scene light"
        )
        self.plotter.add_light(fill)

        # ── 3. Back Rim Light (Viền sáng cyan làm nổi bật đường nét thân tàu) ──
        rim = pv.Light(
            position=(-10.0, 10.0, 8.0),
            focal_point=(0.0, 0.0, 0.0),
            color="#00e5ff",
            intensity=0.75,
            light_type="scene light"
        )
        self.plotter.add_light(rim)

        # ── 4. Ambient Fill Light (Tán xạ ánh sáng môi trường nước biển) ──
        ambient = pv.Light(
            position=(0.0, 0.0, -20.0),
            focal_point=(0.0, 0.0, 0.0),
            color="#3388aa",
            intensity=0.60,
            light_type="scene light"
        )
        self.plotter.add_light(ambient)

        # ── 5. Subsea LED Headlights (2 Đèn pha LED gắn trước mũi ROV) ──
        self._headlight_left = pv.Light(
            position=(0.35, 0.14, 0.0),
            focal_point=(6.0, 0.14, -0.4),
            color="#ffffff",
            intensity=headlight_intensity,
            positional=True,
            cone_angle=40.0,
            exponent=10.0
        )
        self.plotter.add_light(self._headlight_left)

        self._headlight_right = pv.Light(
            position=(0.35, -0.14, 0.0),
            focal_point=(6.0, -0.14, -0.4),
            color="#ffffff",
            intensity=headlight_intensity,
            positional=True,
            cone_angle=40.0,
            exponent=10.0
        )
        self.plotter.add_light(self._headlight_right)

        # ── Bathymetry Seafloor Terrain (Địa hình đáy biển mượt mà, không sọc lưới) ──
        grid_size = 140.0
        res = 40
        plane = pv.Plane(
            center=(0.0, 0.0, terrain_depth),
            direction=(0.0, 0.0, 1.0),
            i_size=grid_size,
            j_size=grid_size,
            i_resolution=res,
            j_resolution=res
        )
        pts = plane.points
        pts[:, 2] += (
            np.sin(pts[:, 0] * 0.18) * 1.0 * roughness +
            np.cos(pts[:, 1] * 0.15) * 0.85 * roughness +
            np.sin((pts[:, 0] + pts[:, 1]) * 0.08) * 0.75 * roughness
        )
        plane.compute_normals(inplace=True)

        terrain_actor = self.plotter.add_mesh(
            plane,
            color=terrain_color,
            pbr=True,
            metallic=0.10,
            roughness=0.90,
            ambient=0.25,
            smooth_shading=True,
            show_edges=False,
            pickable=False
        )
        self._env_actors.append(terrain_actor)

        # ── Water Surface (Mặt nước bán trong suốt) ───────────
        water = pv.Plane(
            center=(0.0, 0.0, 0.0),
            direction=(0.0, 0.0, 1.0),
            i_size=grid_size * 0.85,
            j_size=grid_size * 0.85,
            i_resolution=20,
            j_resolution=20
        )
        water_actor = self.plotter.add_mesh(
            water,
            color="#00a8e8",
            pbr=True,
            metallic=0.40,
            roughness=0.10,
            opacity=0.14,
            smooth_shading=True,
            show_edges=False,
            pickable=False
        )
        self._env_actors.append(water_actor)

        if hasattr(self, "_hud"):
            self._hud.update_data(map_name=self._current_map_name)

    def _build_world_axes(self):
        """
        Tạo Gốc Toạ Độ Thế Giới 3D & Trạm Gốc (Home Base / Origin Platform) nổi bật:
          - Bộ 3 mũi tên 3D RGB Luminous phát sáng (X=Đỏ Bắc, Y=Xanh Lá Tây, Z=Xanh Dương Lên).
          - Quả cầu Beacon Sonar phát sáng neon tại tâm (0,0,0).
          - Vòng tròn sân hạ thủy (Home Launch Pad) với la bàn toạ độ đáy biển.
          - Cột sáng định vị thẳng đứng (Vertical Light Beacon Column) nhìn thấy từ xa.
        """
        self._origin_actors = []

        # ── 1. Cột sáng định vị thẳng đứng (Vertical Light Beacon Pillar) ──
        beacon_col = pv.Cylinder(center=(0.0, 0.0, 0.0), direction=(0.0, 0.0, 1.0), radius=0.08, height=35.0)
        act_col = self.plotter.add_mesh(
            beacon_col,
            color="#00f0ff",
            opacity=0.35,
            smooth_shading=True,
            show_edges=False,
            pickable=False
        )
        self._origin_actors.append(act_col)

        # ── 2. Quả cầu Beacon Sonar tại tâm gốc (0, 0, 0) ──
        center_sphere = pv.Sphere(radius=0.28, center=(0.0, 0.0, 0.0))
        act_sphere = self.plotter.add_mesh(
            center_sphere,
            color="#00ffff",
            pbr=True,
            metallic=0.2,
            roughness=0.1,
            ambient=0.90,
            smooth_shading=True,
            show_edges=False,
            pickable=False
        )
        self._origin_actors.append(act_sphere)

        # ── 3. Vòng tròn sân đỗ Home Launch Pad (Sàn hạ thủy tròn) ──
        ring_outer = pv.Disc(center=(0.0, 0.0, 0.0), inner=2.2, outer=2.5, normal=(0.0, 0.0, 1.0), r_res=2, c_res=48)
        act_ro = self.plotter.add_mesh(
            ring_outer,
            color="#00d4ff",
            opacity=0.75,
            smooth_shading=True,
            show_edges=False,
            pickable=False
        )
        self._origin_actors.append(act_ro)

        ring_inner = pv.Disc(center=(0.0, 0.0, 0.0), inner=0.9, outer=1.1, normal=(0.0, 0.0, 1.0), r_res=2, c_res=48)
        act_ri = self.plotter.add_mesh(
            ring_inner,
            color="#00f0ff",
            opacity=0.80,
            smooth_shading=True,
            show_edges=False,
            pickable=False
        )
        self._origin_actors.append(act_ri)

        # Nan hoa định hướng (4 tia X, -X, Y, -Y)
        spoke_len = 2.4
        spoke_r = 0.03
        spk_x = pv.Cylinder(center=(0.0, 0.0, 0.0), direction=(1.0, 0.0, 0.0), radius=spoke_r, height=spoke_len * 2)
        spk_y = pv.Cylinder(center=(0.0, 0.0, 0.0), direction=(0.0, 1.0, 0.0), radius=spoke_r, height=spoke_len * 2)
        act_sx = self.plotter.add_mesh(spk_x, color="#0088cc", opacity=0.6, smooth_shading=True, pickable=False)
        act_sy = self.plotter.add_mesh(spk_y, color="#0088cc", opacity=0.6, smooth_shading=True, pickable=False)
        self._origin_actors.extend([act_sx, act_sy])

        # ── 4. Bộ 3 Mũi Tên Trục Toạ Độ 3D (Thick Luminous 3D RGB Navigation Arrows) ──
        axis_len = 3.2
        cyl_r = 0.065
        cone_r = 0.18
        cone_h = 0.55

        # ── Trục X (North - Đỏ Neon rực rỡ) ──
        ax_x_cyl = pv.Cylinder(center=(axis_len / 2, 0.0, 0.0), direction=(1.0, 0.0, 0.0), radius=cyl_r, height=axis_len)
        ax_x_cone = pv.Cone(center=(axis_len + cone_h / 2, 0.0, 0.0), direction=(1.0, 0.0, 0.0), radius=cone_r, height=cone_h, resolution=20)
        act_xc = self.plotter.add_mesh(ax_x_cyl, color="#ff1e42", pbr=True, metallic=0.3, roughness=0.2, ambient=0.85, smooth_shading=True, pickable=False)
        act_xhead = self.plotter.add_mesh(ax_x_cone, color="#ff1e42", pbr=True, metallic=0.3, roughness=0.2, ambient=0.95, smooth_shading=True, pickable=False)
        self._origin_actors.extend([act_xc, act_xhead])

        # ── Trục Y (West - Xanh Lá Neon) ──
        ax_y_cyl = pv.Cylinder(center=(0.0, axis_len / 2, 0.0), direction=(0.0, 1.0, 0.0), radius=cyl_r, height=axis_len)
        ax_y_cone = pv.Cone(center=(0.0, axis_len + cone_h / 2, 0.0), direction=(0.0, 1.0, 0.0), radius=cone_r, height=cone_h, resolution=20)
        act_yc = self.plotter.add_mesh(ax_y_cyl, color="#00ff66", pbr=True, metallic=0.3, roughness=0.2, ambient=0.85, smooth_shading=True, pickable=False)
        act_yhead = self.plotter.add_mesh(ax_y_cone, color="#00ff66", pbr=True, metallic=0.3, roughness=0.2, ambient=0.95, smooth_shading=True, pickable=False)
        self._origin_actors.extend([act_yc, act_yhead])

        # ── Trục Z (Up - Xanh Dương Neon) ──
        ax_z_cyl = pv.Cylinder(center=(0.0, 0.0, axis_len / 2), direction=(0.0, 0.0, 1.0), radius=cyl_r, height=axis_len)
        ax_z_cone = pv.Cone(center=(0.0, 0.0, axis_len + cone_h / 2), direction=(0.0, 0.0, 1.0), radius=cone_r, height=cone_h, resolution=20)
        act_zc = self.plotter.add_mesh(ax_z_cyl, color="#00c8ff", pbr=True, metallic=0.3, roughness=0.2, ambient=0.85, smooth_shading=True, pickable=False)
        act_zhead = self.plotter.add_mesh(ax_z_cone, color="#00c8ff", pbr=True, metallic=0.3, roughness=0.2, ambient=0.95, smooth_shading=True, pickable=False)
        self._origin_actors.extend([act_zc, act_zhead])

    def _build_particle_field(self):
        """Tạo trường hạt bụi biển (Marine Snow / Plankton) lơ lửng."""
        n_pts = 200
        self._part_coords = np.random.uniform(-10, 10, (n_pts, 3)).astype(np.float32)
        self._part_poly = pv.PolyData(self._part_coords)
        self._particle_actor = self.plotter.add_mesh(
            self._part_poly,
            color="#80e5ff",
            point_size=3.0,
            render_points_as_spheres=True,
            opacity=0.40,
            pickable=False
        )

    # ──────────────────────────────────────────────────────────
    # MODEL ROV LOADING & PBR SHADING
    # ──────────────────────────────────────────────────────────
    def set_model(self, model, cad_file: Optional[str] = None):
        """
        Tải mô hình ROV từ CAD file (.obj / .stl / .gltf) hoặc dựng mô hình procedural PBR.
        Gán các thông số vật lý PBR Safety Yellow sáng rõ, mượt mà.
        """
        self._model_config = model.get_visual_config() if hasattr(model, "get_visual_config") else None
        self._cad_file = cad_file

        # Xóa các actor ROV và chân vịt cũ
        for act in self._rov_actors:
            try:
                self.plotter.remove_actor(act)
            except Exception:
                pass
        self._rov_actors.clear()

        for act in self._propeller_actors:
            try:
                self.plotter.remove_actor(act)
            except Exception:
                pass
        self._propeller_actors.clear()

        loaded_ok = False
        if cad_file and os.path.exists(cad_file):
            try:
                loaded_ok = self._load_cad_model(cad_file)
            except Exception as e:
                print(f"[PyVista3D] Error loading CAD file {cad_file}: {e}")
                loaded_ok = False

        if not loaded_ok:
            self._build_default_proc_model()

        # Dựng các cụm chân vịt 3D (Thruster Propellers)
        self._build_thruster_propellers()

        # Cập nhật toạ độ & tư thế
        self._apply_pose_transform(self._current_pos, self._current_quat)
        self.plotter.render()

    def _load_cad_model(self, filepath: str) -> bool:
        """Đọc file 3D (.obj / .stl / .gltf) bằng PyVista và gán PBR shader sáng mịn tuyệt đối."""
        mesh = pv.read(filepath)
        if mesh is None or mesh.n_points == 0:
            return False

        # Chuẩn hoá kích thước về ~0.68m và căn giữa trọng tâm
        bounds = mesh.bounds
        center = mesh.center
        mesh.points -= center
        max_dim = max(bounds[1] - bounds[0], bounds[3] - bounds[2], bounds[5] - bounds[4])
        if max_dim > 1e-5:
            mesh.points = (mesh.points / max_dim) * 0.68

        # Tính toán pháp tuyến bề mặt mượt mà (Normals)
        mesh.compute_normals(cell_normals=True, point_normals=True, inplace=True)

        # Gán PBR Shader: Vàng Cứu Hộ Subsea (Signal Safety Yellow) sáng bóng, KHÔNG vẽ sọc lưới
        actor = self.plotter.add_mesh(
            mesh,
            color="#ffc300",
            pbr=True,
            metallic=0.25,
            roughness=0.22,
            ambient=0.35,
            smooth_shading=True,
            show_edges=False,
            pickable=True
        )
        self._rov_actors.append(actor)
        return True

    def _build_default_proc_model(self):
        """Dựng mô hình ROV đa khối chất lượng cao PBR khi không có file CAD."""
        # 1. Main Chassis Frame (Khung thân chính - Carbon Graphite)
        body = pv.Cube(center=(0, 0, 0), x_length=0.45, y_length=0.32, z_length=0.20)
        body.compute_normals(inplace=True)
        act_body = self.plotter.add_mesh(
            body,
            color="#1e2d3d",
            pbr=True,
            metallic=0.75,
            roughness=0.30,
            ambient=0.30,
            smooth_shading=True,
            show_edges=False
        )
        self._rov_actors.append(act_body)

        # 2. Buoyancy Foam Block (Khối bọt nổi trên nóc - Vàng sáng PBR)
        foam = pv.Cube(center=(0, 0, 0.12), x_length=0.48, y_length=0.34, z_length=0.06)
        foam.compute_normals(inplace=True)
        act_foam = self.plotter.add_mesh(
            foam,
            color="#ffb703",
            pbr=True,
            metallic=0.20,
            roughness=0.20,
            ambient=0.40,
            smooth_shading=True,
            show_edges=False
        )
        self._rov_actors.append(act_foam)

        # 3. Electronics Tube (Ống kín nước acrylic trong suốt ở giữa)
        tube = pv.Cylinder(center=(0, 0, 0), direction=(1, 0, 0), radius=0.07, height=0.36)
        tube.compute_normals(inplace=True)
        act_tube = self.plotter.add_mesh(
            tube,
            color="#00e5ff",
            pbr=True,
            metallic=0.85,
            roughness=0.12,
            opacity=0.90,
            smooth_shading=True,
            show_edges=False
        )
        self._rov_actors.append(act_tube)

    def _build_thruster_propellers(self):
        """Tạo các cánh quạt chân vịt PBR 3D gắn vào vị trí thrusters."""
        cfg = self._model_config
        thrusters_info = []

        if cfg:
            for idx, ht in enumerate(cfg.get("horizontal_thrusters", [])):
                thrusters_info.append({
                    "pos": np.array(ht.get("pos", [0, 0, 0]), np.float32),
                    "angle": float(ht.get("angle_deg", 0.0)),
                    "is_vert": False,
                    "dir": 1.0 if idx % 2 == 0 else -1.0
                })
            for idx, vt in enumerate(cfg.get("vertical_thrusters", [])):
                thrusters_info.append({
                    "pos": np.array(vt.get("pos", [0, 0, 0]), np.float32),
                    "angle": 0.0,
                    "is_vert": True,
                    "dir": 1.0 if idx % 2 == 0 else -1.0
                })
        else:
            # Mặc định 6 thrusters
            thrusters_info = [
                {"pos": np.array([0.15, -0.15, 0.0]), "angle": 45.0, "is_vert": False, "dir": 1.0},
                {"pos": np.array([0.15, 0.15, 0.0]), "angle": -45.0, "is_vert": False, "dir": -1.0},
                {"pos": np.array([-0.15, -0.15, 0.0]), "angle": -135.0, "is_vert": False, "dir": 1.0},
                {"pos": np.array([-0.15, 0.15, 0.0]), "angle": 135.0, "is_vert": False, "dir": -1.0},
                {"pos": np.array([0.0, -0.12, 0.05]), "angle": 0.0, "is_vert": True, "dir": 1.0},
                {"pos": np.array([0.0, 0.12, 0.05]), "angle": 0.0, "is_vert": True, "dir": -1.0},
            ]

        self._prop_metadata = []
        for t in thrusters_info:
            # 1. Ống che chân vịt (Nozzle Duct)
            duct = pv.Cylinder(center=(0, 0, 0), direction=(1, 0, 0), radius=0.045, height=0.06)
            act_duct = self.plotter.add_mesh(
                duct,
                color="#00a8cc",
                pbr=True,
                metallic=0.85,
                roughness=0.22,
                ambient=0.30,
                smooth_shading=True,
                show_edges=False
            )
            self._rov_actors.append(act_duct)

            # 2. Cánh quạt 3 lá (3-Blade Propeller)
            prop = pv.Cone(center=(0, 0, 0), direction=(1, 0, 0), radius=0.038, height=0.022, resolution=12)
            act_prop = self.plotter.add_mesh(
                prop,
                color="#00ffcc",
                pbr=True,
                metallic=0.90,
                roughness=0.15,
                ambient=0.40,
                smooth_shading=True,
                show_edges=False
            )
            self._propeller_actors.append(act_prop)

            self._prop_metadata.append({
                "duct_actor": act_duct,
                "prop_actor": act_prop,
                "pos": t["pos"],
                "angle": t["angle"],
                "is_vert": t["is_vert"],
                "dir": t["dir"],
                "spin": 0.0
            })

    # ──────────────────────────────────────────────────────────
    # REAL-TIME TELEMETRY & POSE UPDATES (60 FPS)
    # ──────────────────────────────────────────────────────────
    def update_pose(
        self,
        position: np.ndarray,
        quat_xyzw: np.ndarray,
        heading_deg: float = 0.0,
        depth_m: float = 0.0,
        speed_mps: float = 0.0,
        roll_deg: float = 0.0,
        pitch_deg: float = 0.0
    ):
        """Cập nhật vị trí và tư thế ROV từ dữ liệu viễn trắc."""
        if self._origin is not None:
            pos = position - self._origin
        else:
            pos = position.copy()

        # Chuyển đổi hệ toạ độ NED sang VTK World (X_vtk=North, Y_vtk=-East, Z_vtk=-Down)
        gl_pos = np.array([pos[0], -pos[1], -pos[2]], np.float32)
        self._current_pos  = gl_pos
        self._current_quat = quat_xyzw.copy()
        self._heading      = heading_deg
        self._depth        = depth_m
        self._speed        = speed_mps
        self._roll         = roll_deg
        self._pitch        = pitch_deg

        # Áp dụng ma trận biến đổi 6-DoF
        self._apply_pose_transform(gl_pos, quat_xyzw)

        # Cập nhật HUD
        dist_home = float(np.linalg.norm(gl_pos))
        self._hud.update_data(
            depth=depth_m,
            heading=heading_deg,
            pos=[pos[0], pos[1], pos[2]],
            speed=speed_mps,
            roll=roll_deg,
            pitch=pitch_deg,
            dist_home=dist_home,
            thrust=self._thrust_level,
            cam_mode=CameraMode.LABELS.get(self._cam_mode, "?")
        )

        # Điều khiển Camera theo dõi
        self._update_camera_tracking(gl_pos, heading_deg)
        self.plotter.render()

    def _apply_pose_transform(self, pos: np.ndarray, quat_xyzw: np.ndarray):
        """Tạo ma trận biến đổi 4x4 từ Quaternion (NED -> VTK) và áp dụng trực tiếp lên GPU."""
        qx, qy, qz, qw = quat_xyzw
        norm = math.sqrt(qx * qx + qy * qy + qz * qz + qw * qw)
        if norm > 1e-6:
            qx, qy, qz, qw = qx / norm, qy / norm, qz / norm, qw / norm

        # Quaternion to standard rotation matrix elements
        r00 = 1.0 - 2.0 * (qy * qy + qz * qz)
        r01 = 2.0 * (qx * qy - qz * qw)
        r02 = 2.0 * (qx * qz + qy * qw)

        r10 = 2.0 * (qx * qy + qz * qw)
        r11 = 1.0 - 2.0 * (qx * qx + qz * qz)
        r12 = 2.0 * (qy * qz - qx * qw)

        r20 = 2.0 * (qx * qz - qy * qw)
        r21 = 2.0 * (qy * qz + qx * qw)
        r22 = 1.0 - 2.0 * (qx * qx + qy * qy)

        # NED -> VTK World matrix: [X, -Y, -Z]
        mat = vtk.vtkMatrix4x4()
        mat.SetElement(0, 0, r00)
        mat.SetElement(0, 1, -r01)
        mat.SetElement(0, 2, -r02)
        mat.SetElement(0, 3, float(pos[0]))

        mat.SetElement(1, 0, -r10)
        mat.SetElement(1, 1, r11)
        mat.SetElement(1, 2, r12)
        mat.SetElement(1, 3, float(pos[1]))

        mat.SetElement(2, 0, -r20)
        mat.SetElement(2, 1, r21)
        mat.SetElement(2, 2, r22)
        mat.SetElement(2, 3, float(pos[2]))

        mat.SetElement(3, 0, 0.0)
        mat.SetElement(3, 1, 0.0)
        mat.SetElement(3, 2, 0.0)
        mat.SetElement(3, 3, 1.0)

        trans_body = vtk.vtkTransform()
        trans_body.SetMatrix(mat)

        # 1. Áp dụng cho thân ROV chính
        for act in self._rov_actors:
            act.SetUserTransform(trans_body)

        # 2. Biến đổi từng cụm thruster và chân vịt
        for meta in getattr(self, "_prop_metadata", []):
            p_pos = meta["pos"]
            trans_duct = vtk.vtkTransform()
            trans_duct.Concatenate(trans_body)
            trans_duct.Translate(float(p_pos[0]), float(p_pos[1]), float(p_pos[2]))
            if meta["is_vert"]:
                trans_duct.RotateY(90.0)
            elif meta["angle"] != 0.0:
                trans_duct.RotateZ(float(meta["angle"]))
            meta["duct_actor"].SetUserTransform(trans_duct)

            trans_prop = vtk.vtkTransform()
            trans_prop.Concatenate(trans_duct)
            trans_prop.RotateX(float(meta["spin"]))
            meta["prop_actor"].SetUserTransform(trans_prop)

        # 3. Biến đổi vị trí và chùm sáng đèn pha Subsea LED
        if hasattr(self, "_headlight_left") and hasattr(self, "_headlight_right"):
            fwd_x = mat.GetElement(0, 0)
            fwd_y = mat.GetElement(1, 0)
            fwd_z = mat.GetElement(2, 0)

            # Left headlight world pos
            hl_local = np.array([0.35, 0.14, 0.0, 1.0], np.float64)
            hl_world = np.zeros(4, np.float64)
            mat.MultiplyPoint(hl_local, hl_world)

            self._headlight_left.position = (float(hl_world[0]), float(hl_world[1]), float(hl_world[2]))
            self._headlight_left.focal_point = (
                float(hl_world[0] + fwd_x * 6.5),
                float(hl_world[1] + fwd_y * 6.5),
                float(hl_world[2] + fwd_z * 6.5)
            )

            # Right headlight world pos
            hr_local = np.array([0.35, -0.14, 0.0, 1.0], np.float64)
            hr_world = np.zeros(4, np.float64)
            mat.MultiplyPoint(hr_local, hr_world)

            self._headlight_right.position = (float(hr_world[0]), float(hr_world[1]), float(hr_world[2]))
            self._headlight_right.focal_point = (
                float(hr_world[0] + fwd_x * 6.5),
                float(hr_world[1] + fwd_y * 6.5),
                float(hr_world[2] + fwd_z * 6.5)
            )

    def set_thrust(self, level: float):
        """Cập nhật công suất lực đẩy (0.0 đến 1.0) điều khiển tốc độ quay chân vịt."""
        self._thrust_level = max(0.0, min(1.0, float(level)))

    def _animate_tick(self):
        """Hoạt hoạ chân vịt quay và trôi dạt bụi biển (Marine Snow)."""
        dt = 0.033
        spin_step = (15.0 + self._thrust_level * 160.0) * (dt / 0.033)
        for meta in getattr(self, "_prop_metadata", []):
            meta["spin"] = (meta["spin"] + spin_step * meta["dir"]) % 360.0

        # Trôi dạt bụi biển
        if hasattr(self, "_part_coords") and self._particle_actor is not None:
            self._part_coords[:, 0] += 0.008
            self._part_coords[:, 1] += 0.005
            self._part_coords[:, 2] += 0.002
            mask_x = self._part_coords[:, 0] > 10.0
            self._part_coords[mask_x, 0] = -10.0
            mask_y = self._part_coords[:, 1] > 10.0
            self._part_coords[mask_y, 1] = -10.0
            self._part_poly.points = self._part_coords

        if self._cam_mode == CameraMode.ORBIT and not self._user_ctrl:
            self._orbit_yaw = (self._orbit_yaw + 0.45) % 360.0
            self._update_camera_tracking(self._current_pos, self._heading)
            self.plotter.render()

    # ──────────────────────────────────────────────────────────
    # CAMERA TRACKING MODES
    # ──────────────────────────────────────────────────────────
    def _set_camera_mode(self, mode: int):
        """Chuyển đổi chế độ Camera."""
        self._cam_mode = mode
        self._user_ctrl = False

        if mode == CameraMode.MANUAL:
            self._cam_resume_timer.stop()
        else:
            self._update_camera_tracking(self._current_pos, self._heading)
    def set_camera_mode_by_name(self, name: str):
        """Chuyển đổi góc nhìn camera theo tên ('isometric', 'chase', 'orbit', 'map', 'manual')."""
        mapping = {
            "isometric": CameraMode.ISOMETRIC,
            "chase": CameraMode.CHASE,
            "orbit": CameraMode.ORBIT,
            "map": CameraMode.MAP,
            "manual": CameraMode.MANUAL,
        }
        mode = mapping.get(str(name).lower(), CameraMode.ISOMETRIC)
        self._set_camera_mode(mode)

    def _reset_camera_view(self):
        """Khôi phục vị trí camera ban đầu."""
        self._cam_lerp_pos = self._current_pos.copy()
        cx, cy, cz = self._current_pos
        dist = 3.6
        elev = 1.6
        self.plotter.camera.position = (float(cx + dist * 0.707), float(cy + dist * 0.707), float(cz + elev))
        self.plotter.camera.focal_point = (float(cx), float(cy), float(cz))
        self.plotter.camera.view_up = (0.0, 0.0, 1.0)
        self._set_camera_mode(CameraMode.ISOMETRIC)
        self.plotter.render()

    def _update_camera_tracking(self, gl_pos: np.ndarray, heading_deg: float):
        """Cập nhật góc nhìn camera mượt mà theo toạ độ ROV."""
        if self._user_ctrl or self._cam_mode == CameraMode.MANUAL:
            return

        alpha = 0.10
        self._cam_lerp_pos = (self._cam_lerp_pos * (1.0 - alpha) + gl_pos * alpha).astype(np.float32)
        cx, cy, cz = self._cam_lerp_pos

        if self._cam_mode == CameraMode.ISOMETRIC:
            # Góc nhìn 3D bao quát cố định (Azimuth 45 độ, Elevation 24 độ)
            dist = 3.6
            elev = 1.5
            rad = math.radians(45.0)
            cam_x = cx + dist * math.cos(rad)
            cam_y = cy + dist * math.sin(rad)
            cam_z = cz + elev
            self.plotter.camera.position = (float(cam_x), float(cam_y), float(cam_z))
            self.plotter.camera.focal_point = (float(cx), float(cy), float(cz))
            self.plotter.camera.view_up = (0.0, 0.0, 1.0)

        elif self._cam_mode == CameraMode.CHASE:
            # Camera bám sau đuôi tàu có độ trễ mượt mà
            target_yaw = -heading_deg + 180.0
            diff = (target_yaw - self._cam_damped_yaw + 180.0) % 360.0 - 180.0
            self._cam_damped_yaw += diff * 0.12

            dist = 3.8
            elev = 1.4
            rad = math.radians(self._cam_damped_yaw)
            cam_x = cx + dist * math.cos(rad)
            cam_y = cy + dist * math.sin(rad)
            cam_z = cz + elev
            self.plotter.camera.position = (float(cam_x), float(cam_y), float(cam_z))
            self.plotter.camera.focal_point = (float(cx), float(cy), float(cz))
            self.plotter.camera.view_up = (0.0, 0.0, 1.0)

        elif self._cam_mode == CameraMode.ORBIT:
            dist = 4.2
            elev = 1.8
            rad = math.radians(self._orbit_yaw)
            cam_x = cx + dist * math.cos(rad)
            cam_y = cy + dist * math.sin(rad)
            cam_z = cz + elev
            self.plotter.camera.position = (float(cam_x), float(cam_y), float(cam_z))
            self.plotter.camera.focal_point = (float(cx), float(cy), float(cz))
            self.plotter.camera.view_up = (0.0, 0.0, 1.0)

        elif self._cam_mode == CameraMode.MAP:
            self.plotter.camera.position = (float(cx), float(cy), float(cz + 8.5))
            self.plotter.camera.focal_point = (float(cx), float(cy), float(cz))
            self.plotter.camera.view_up = (1.0, 0.0, 0.0)

    # ──────────────────────────────────────────────────────────
    # TRAJECTORY TRAIL
    # ──────────────────────────────────────────────────────────
    def update_trajectory(self, x: float, y: float, z: float):
        """Vẽ đường vệt quỹ đạo di chuyển của ROV trong không gian 3D."""
        self._traj_pts.append([x, -y, -z])
        if len(self._traj_pts) > 2000:
            self._traj_pts.pop(0)

        self._traj_update_cnt += 1
        if self._traj_update_cnt % 3 != 0:
            return

        pts = np.array(self._traj_pts, np.float32)
        if len(pts) < 2:
            return

        poly = pv.lines_from_points(pts)
        if self._traj_actor is not None:
            try:
                self.plotter.remove_actor(self._traj_actor)
            except Exception:
                pass

        self._traj_actor = self.plotter.add_mesh(
            poly,
            color="#00ffff",
            line_width=3.5,
            opacity=0.85,
            pickable=False
        )

    def _reset_trajectory(self):
        self._traj_pts.clear()
        if self._traj_actor is not None:
            try:
                self.plotter.remove_actor(self._traj_actor)
            except Exception:
                pass
            self._traj_actor = None

    def update_fov_effect(self, heading_deg: float):
        pass

    def update_slam_points(self, points: np.ndarray):
        pass

    # ──────────────────────────────────────────────────────────
    # CONTEXT MENU & MAP SWITCHING
    # ──────────────────────────────────────────────────────────
    def switch_map(self, map_name: str):
        """Chuyển đổi môi trường nước biển."""
        self._apply_environment_preset(map_name)
        self.plotter.render()

    def set_origin(self, pos: np.ndarray):
        self._origin = pos.copy()

    def reset_origin(self):
        self._origin = None
        self._reset_trajectory()

    def clear_waypoints(self):
        pass

    def _show_context_menu(self, global_pos: QtCore.QPoint):
        menu = QtWidgets.QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #081d30, stop:1 #04101c);
                color: #A0D8F0;
                border: 1px solid #0099cc;
                border-radius: 6px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 26px 6px 14px;
                font-family: Consolas, Arial;
                font-size: 11px;
                font-weight: bold;
            }
            QMenu::item:selected {
                background: #006699;
                color: #ffffff;
            }
        """)

        # 1. Chuyển Camera
        cam_menu = menu.addMenu("📹  Góc Nhìn Camera (Camera Mode)")
        a_iso    = cam_menu.addAction("📐  ISOMETRIC — Góc 3D Bao Quát (Mặc định)")
        a_chase  = cam_menu.addAction("🎬  CHASE CAM — Bám Sau Đuôi Mượt Mà")
        a_orbit  = cam_menu.addAction("🔄  ORBIT     — Tự Động Xoay Quanh")
        a_map    = cam_menu.addAction("🗺   MAP       — Nhìn Từ Trên Xuống")
        a_manual = cam_menu.addAction("🖐  MANUAL    — Tự Do Chuột")

        for a, m in [
            (a_iso,    CameraMode.ISOMETRIC),
            (a_chase,  CameraMode.CHASE),
            (a_orbit,  CameraMode.ORBIT),
            (a_map,    CameraMode.MAP),
            (a_manual, CameraMode.MANUAL)
        ]:
            a.setCheckable(True)
            a.setChecked(self._cam_mode == m)

        # 2. Chuyển Map
        map_menu = menu.addMenu("🗺  Môi Trường Nước Biển (Environment Map)")
        map_actions = {}
        for dname, mname in [
            ("🏞  Hồ Thủy Điện (Reservoir)", "RESERVOIR"),
            ("🏊  Bể Bơi Thử Nghiệm (Pool)", "POOL"),
            ("🌊  Biển Khơi Sâu (Offshore Ocean)", "OFFSHORE"),
            ("🚢  Xác Tàu Đắm (Shipwreck)", "SHIPWRECK")
        ]:
            act = map_menu.addAction(dname)
            act.setCheckable(True)
            if mname == self._current_map_name:
                act.setChecked(True)
            map_actions[act] = mname

        menu.addSeparator()
        a_reset_view = menu.addAction("🎯  Reset Góc Nhìn Camera (Default View)")
        a_reset_home = menu.addAction("📍  Đặt Lại Gốc Toạ Độ (Set Home Origin)")
        a_clear_traj = menu.addAction("🗑   Xoá Vệt Quỹ Đạo (Clear Trajectory)")

        chosen = menu.exec(global_pos)
        if not chosen:
            return

        if chosen in map_actions:
            self.switch_map(map_actions[chosen])
            return

        if chosen == a_iso:
            self._set_camera_mode(CameraMode.ISOMETRIC)
        elif chosen == a_chase:
            self._set_camera_mode(CameraMode.CHASE)
        elif chosen == a_orbit:
            self._set_camera_mode(CameraMode.ORBIT)
        elif chosen == a_map:
            self._set_camera_mode(CameraMode.MAP)
        elif chosen == a_manual:
            self._set_camera_mode(CameraMode.MANUAL)
        elif chosen == a_reset_view:
            self._reset_camera_view()
        elif chosen == a_reset_home:
            self.reset_origin()
        elif chosen == a_clear_traj:
            self._reset_trajectory()

    # ──────────────────────────────────────────────────────────
    # MOUSE INTERACTION & RESUME TIMER
    # ──────────────────────────────────────────────────────────
    def _on_vtk_left_press(self, obj, event):
        self._user_ctrl = True
        self._cam_resume_timer.stop()

    def _on_vtk_left_release(self, obj, event):
        if self._cam_mode != CameraMode.MANUAL:
            self._cam_resume_timer.start(4500)

    def _on_vtk_right_press(self, obj, event):
        pos = QtGui.QCursor.pos()
        self._show_context_menu(pos)

    def _on_cam_resume(self):
        self._user_ctrl = False
        if hasattr(self, "_hud"):
            self._hud.update_data(user_ctrl=False)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_hud"):
            self._hud.setGeometry(self.rect())

    def clean_up(self):
        """Dọn dẹp và giải phóng tài nguyên OpenGL/VTK an toàn trước khi đóng cửa sổ."""
        if getattr(self, "_is_cleaned_up", False):
            return
        self._is_cleaned_up = True
        try:
            self._anim_timer.stop()
            self._cam_resume_timer.stop()
        except Exception:
            pass

        try:
            if hasattr(self, "plotter") and self.plotter is not None:
                if hasattr(self.plotter, "interactor") and self.plotter.interactor:
                    try:
                        self.plotter.interactor.RemoveAllObservers()
                    except Exception:
                        pass
                if hasattr(self.plotter, "render_window") and self.plotter.render_window:
                    try:
                        self.plotter.render_window.Finalize()
                    except Exception:
                        pass
                self.plotter.close()
        except Exception:
            pass

    def closeEvent(self, event):
        self.clean_up()
        super().closeEvent(event)
