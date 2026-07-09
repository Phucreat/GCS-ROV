"""
gl_3d_widget.py - 3D OpenGL ROV Visualization Widget (Underwater Edition v2.0)
===============================================================================
Widget PyQtGraph OpenGL với môi trường đại dương sinh động, thực tế:

  Môi trường:
    - Nền deep-ocean gradient xanh sâu
    - Mặt nước bán trong suốt (z=0) rung theo sóng sine
    - Đáy biển terrain mesh lồi lõm tự nhiên
    - Tia God Rays từ mặt nước chiếu xuống
    - 200+ bong bóng phát ra xung quanh ROV, nổi lên mặt nước

  HUD Overlay (QPainter, không dùng OpenGL text):
    - Thước đo độ sâu dọc cạnh trái (gradient xanh → xanh thẫm)
    - Bảng thông tin tọa độ X/Y/Z và hướng HDG
    - Đồng hồ tốc độ (đổi màu theo vận tốc)
    - Chỉ báo chế độ camera + hướng dẫn R-Click

  Camera 3 chế độ (R-Click để chuyển):
    - FOLLOW   : Bám theo ROV với góc nghiêng cố định
    - ORBIT    : Tự xoay cinematic quanh ROV
    - TOP-DOWN : Nhìn từ trên xuống dạng bản đồ

  API (giữ nguyên cho main.py):
    set_model(model, cad_file)
    set_origin(position)
    update_pose(position, quat_xyzw)
    update_trajectory(x, y, z)
    update_slam_points(pts_xyz)
    update_fov_effect(heading_deg, fov_deg)
    reset_origin()
    set_follow_mode(enabled)
"""
import math
import struct
import time
import numpy as np
from pathlib import Path

from PyQt6 import QtCore, QtGui, QtWidgets
import pyqtgraph.opengl as gl
import pyqtgraph as pg


# ═══════════════════════════════════════════════════════════════
# CAMERA MODE CONSTANTS
# ═══════════════════════════════════════════════════════════════
class CameraMode:
    FOLLOW   = 0   # Camera theo sau ROV góc cố định
    ORBIT    = 1   # Xoay cinematic quanh ROV
    TOP_DOWN = 2   # Nhìn từ trên xuống

    LABELS = {FOLLOW: "FOLLOW", ORBIT: "ORBIT", TOP_DOWN: "TOP-DOWN"}


# ═══════════════════════════════════════════════════════════════
# HUD OVERLAY — QPainter widget trong suốt đặt trên GLViewWidget
# ═══════════════════════════════════════════════════════════════
class _HUDOverlay(QtWidgets.QWidget):
    """Lớp phủ HUD vẽ thông số ROV bằng QPainter lên trên canvas OpenGL."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAutoFillBackground(False)

        # Dữ liệu hiển thị
        self._depth    = 0.0
        self._heading  = 0.0
        self._pos      = [0.0, 0.0, 0.0]
        self._speed    = 0.0
        self._cam_mode = "FOLLOW"
        self._roll     = 0.0
        self._pitch    = 0.0

        # Font cache
        self._font_xs = QtGui.QFont("Consolas", 7)
        self._font_sm = QtGui.QFont("Consolas", 9)
        self._font_md = QtGui.QFont("Consolas", 10, QtGui.QFont.Weight.Bold)
        self._font_lg = QtGui.QFont("Consolas", 15, QtGui.QFont.Weight.Bold)

    def update_data(self, **kw):
        for k, v in kw.items():
            if hasattr(self, f"_{k}"):
                setattr(self, f"_{k}", v)
        self.update()

    def paintEvent(self, event):
        if self.width() < 10 or self.height() < 10:
            return
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()

        # ── 1. Depth bar (vertical, cạnh trái) ──────────────────
        bx, by = 8, 36
        bw, bh = 13, H - 110
        max_d  = 60.0

        # Nền mờ
        p.setPen(QtCore.Qt.PenStyle.NoPen)
        p.setBrush(QtGui.QColor(0, 0, 0, 85))
        p.drawRoundedRect(bx - 4, by - 14, bw + 42, bh + 38, 6, 6)

        # Track rãnh
        p.setBrush(QtGui.QColor(5, 18, 45, 140))
        p.drawRoundedRect(bx, by, bw, bh, 4, 4)

        # Fill gradient theo độ sâu
        grad = QtGui.QLinearGradient(bx, by, bx, by + bh)
        grad.setColorAt(0.0, QtGui.QColor(50, 210, 255, 230))
        grad.setColorAt(0.35, QtGui.QColor(0, 110, 220, 210))
        grad.setColorAt(0.75, QtGui.QColor(0,  40, 150, 200))
        grad.setColorAt(1.0,  QtGui.QColor(10,  0,  80, 200))
        p.setBrush(QtGui.QBrush(grad))
        ratio = min(abs(self._depth) / max_d, 1.0)
        fill  = int(bh * ratio)
        if fill > 0:
            p.drawRoundedRect(bx, by + bh - fill, bw, fill, 4, 4)

        # Tick marks + nhãn số
        p.setFont(self._font_xs)
        for d_mark in range(0, int(max_d) + 1, 10):
            ty = by + int(bh * d_mark / max_d)
            p.setPen(QtGui.QPen(QtGui.QColor(80, 160, 200, 140), 1))
            p.drawLine(bx + bw, ty, bx + bw + 5, ty)
            p.setPen(QtGui.QColor(100, 175, 215, 155))
            p.drawText(bx + bw + 7, ty + 4, f"{d_mark}m")

        # Giá trị hiện tại
        p.setPen(QtGui.QColor(0, 220, 255, 230))
        p.setFont(self._font_md)
        p.drawText(bx - 1, by + bh + 18, f"{abs(self._depth):.1f}m")

        # Nhãn tiêu đề
        p.setPen(QtGui.QColor(90, 150, 195, 155))
        p.setFont(self._font_xs)
        p.drawText(bx, by - 8, "DEPTH")

        # ── 2. Bảng thông tin vị trí + hướng (góc trái trên) ────
        px, py_ = 44, 12
        pw, ph  = 175, 98

        p.setPen(QtCore.Qt.PenStyle.NoPen)
        p.setBrush(QtGui.QColor(0, 8, 35, 125))
        p.drawRoundedRect(px, py_, pw, ph, 8, 8)
        p.setPen(QtGui.QPen(QtGui.QColor(0, 100, 180, 70), 1))
        p.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(px, py_, pw, ph, 8, 8)

        # Heading (dòng to)
        p.setPen(QtGui.QColor(0, 200, 255, 230))
        p.setFont(self._font_md)
        p.drawText(px + 10, py_ + 22, f"HDG  {self._heading:05.1f}°")

        # X / Y / Z
        p.setFont(self._font_sm)
        p.setPen(QtGui.QColor(0, 230, 190, 200))
        p.drawText(px + 10, py_ + 43, f"X  {self._pos[0]:+8.2f} m")
        p.drawText(px + 10, py_ + 58, f"Y  {self._pos[1]:+8.2f} m")
        p.drawText(px + 10, py_ + 73, f"Z  {self._pos[2]:+8.2f} m")

        # Roll & Pitch nhỏ
        p.setFont(self._font_xs)
        p.setPen(QtGui.QColor(150, 200, 220, 170))
        p.drawText(px + 10, py_ + 90,
                   f"R {self._roll:+6.1f}°  P {self._pitch:+6.1f}°")

        # ── 3. Đồng hồ tốc độ (góc phải dưới) ───────────────────
        spd = self._speed
        if spd < 0.5:
            sc = QtGui.QColor(0, 230, 255)
        elif spd < 1.5:
            sc = QtGui.QColor(255, 200, 0)
        else:
            sc = QtGui.QColor(255, 60, 60)

        sw, sh = 92, 52
        sx, sy_ = W - sw - 10, H - sh - 10

        p.setPen(QtCore.Qt.PenStyle.NoPen)
        p.setBrush(QtGui.QColor(0, 8, 35, 125))
        p.drawRoundedRect(sx, sy_, sw, sh, 8, 8)
        p.setPen(QtGui.QPen(sc.darker(140), 1))
        p.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(sx, sy_, sw, sh, 8, 8)

        p.setPen(sc)
        p.setFont(self._font_lg)
        p.drawText(sx + 7, sy_ + 30, f"{spd:.2f}")
        p.setFont(self._font_xs)
        p.setPen(QtGui.QColor(150, 185, 205, 160))
        p.drawText(sx + 7, sy_ + 45, "m/s  SPEED")

        # ── 4. Camera mode + hướng dẫn (góc phải trên) ──────────
        p.setFont(self._font_xs)
        p.setPen(QtGui.QColor(0, 190, 120, 200))
        cam_txt = f"[CAM: {self._cam_mode}]"
        p.drawText(W - 120, 14, cam_txt)
        p.setPen(QtGui.QColor(80, 120, 140, 140))
        p.drawText(W - 140, 26, "Right-click: switch mode")

        p.end()


# ═══════════════════════════════════════════════════════════════
# CAD LOADER (STL & OBJ)
# ═══════════════════════════════════════════════════════════════
class CADLoader:
    """Tải file CAD 3D (STL binary/ASCII, OBJ) → (vertices, faces)."""

    @staticmethod
    def load(filepath: str):
        """Trả về (vertices ndarray [N,3], faces ndarray [M,3])."""
        fp = Path(filepath)
        if not fp.exists():
            print(f"[CADLoader] File not found: {filepath}")
            return None, None
        ext = fp.suffix.lower()
        try:
            if ext == ".stl":
                return CADLoader._load_stl(fp)
            elif ext == ".obj":
                return CADLoader._load_obj(fp)
            else:
                print(f"[CADLoader] Unsupported format: {ext}")
                return None, None
        except Exception as e:
            print(f"[CADLoader] Load error {filepath}: {e}")
            return None, None

    @staticmethod
    def _load_stl(fp: Path):
        data = fp.read_bytes()
        is_binary = False
        try:
            n_tri = struct.unpack_from('<I', data, 80)[0]
            if 84 + n_tri * 50 == len(data):
                is_binary = True
        except Exception:
            pass
        if is_binary:
            return CADLoader._parse_binary_stl(data, n_tri)
        else:
            return CADLoader._parse_ascii_stl(data.decode('utf-8', errors='ignore'))

    @staticmethod
    def _parse_binary_stl(data: bytes, n_tri: int):
        verts, faces = [], []
        offset = 84
        for i in range(n_tri):
            v0 = struct.unpack_from('<fff', data, offset + 12)
            v1 = struct.unpack_from('<fff', data, offset + 24)
            v2 = struct.unpack_from('<fff', data, offset + 36)
            base = len(verts)
            verts += [v0, v1, v2]
            faces.append([base, base+1, base+2])
            offset += 50
        return np.array(verts, dtype=np.float32), np.array(faces, dtype=np.int32)

    @staticmethod
    def _parse_ascii_stl(text: str):
        verts, faces = [], []
        for line in text.strip().splitlines():
            tok = line.strip().split()
            if len(tok) >= 4 and tok[0] == 'vertex':
                verts.append([float(tok[1]), float(tok[2]), float(tok[3])])
        for i in range(0, len(verts) - 2, 3):
            faces.append([i, i+1, i+2])
        return np.array(verts, dtype=np.float32), np.array(faces, dtype=np.int32)

    @staticmethod
    def _load_obj(fp: Path):
        verts, faces = [], []
        with open(fp, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                tok = line.strip().split()
                if not tok:
                    continue
                if tok[0] == 'v':
                    verts.append([float(tok[1]), float(tok[2]), float(tok[3])])
                elif tok[0] == 'f':
                    idx = [int(t.split('/')[0]) - 1 for t in tok[1:]]
                    if len(idx) == 3:
                        faces.append(idx)
                    elif len(idx) == 4:
                        faces.append([idx[0], idx[1], idx[2]])
                        faces.append([idx[0], idx[2], idx[3]])
        if not verts or not faces:
            return None, None
        return np.array(verts, dtype=np.float32), np.array(faces, dtype=np.int32)


# ═══════════════════════════════════════════════════════════════
# PROC MESH BUILDER
# ═══════════════════════════════════════════════════════════════
class ProcMeshBuilder:
    """Tạo mesh hình học thủ công."""

    @staticmethod
    def box(lx, ly, lz):
        hx, hy, hz = lx/2, ly/2, lz/2
        v = np.array([
            [-hx,-hy,-hz],[+hx,-hy,-hz],[+hx,+hy,-hz],[-hx,+hy,-hz],
            [-hx,-hy,+hz],[+hx,-hy,+hz],[+hx,+hy,+hz],[-hx,+hy,+hz],
        ], dtype=np.float32)
        f = np.array([
            [0,1,2],[0,2,3],[4,5,6],[4,6,7],
            [0,1,5],[0,5,4],[2,3,7],[2,7,6],
            [1,2,6],[1,6,5],[0,3,7],[0,7,4],
        ], dtype=np.int32)
        return v, f

    @staticmethod
    def cylinder(r, h, segs=12):
        angles = np.linspace(0, 2*np.pi, segs, endpoint=False)
        bot_v = [[r*np.cos(a), r*np.sin(a), 0.0] for a in angles]
        top_v = [[r*np.cos(a), r*np.sin(a), h]   for a in angles]
        verts = [[0., 0., 0.]] + bot_v + [[0., 0., h]] + top_v
        n = segs; tc = n + 1
        faces = []
        for i in range(n):
            faces.append([0, 1+i, 1+(i+1)%n])
            faces.append([tc, tc+1+i, tc+1+(i+1)%n])
            b0,b1 = 1+i, 1+(i+1)%n
            t0,t1 = tc+1+i, tc+1+(i+1)%n
            faces.append([b0, b1, t1])
            faces.append([b0, t1, t0])
        return np.array(verts, dtype=np.float32), np.array(faces, dtype=np.int32)

    @staticmethod
    def cone(r, h, segs=16):
        angles = np.linspace(0, 2*np.pi, segs, endpoint=False)
        base  = [[r*np.cos(a), r*np.sin(a), 0.0] for a in angles]
        apex  = [0.0, 0.0, h]
        verts = base + [apex]
        ai    = len(base)
        faces = [[i, (i+1)%segs, ai] for i in range(segs)]
        for i in range(1, segs-1):
            faces.append([0, i, i+1])
        return np.array(verts, dtype=np.float32), np.array(faces, dtype=np.int32)


# ═══════════════════════════════════════════════════════════════
# UNDERWATER ENVIRONMENT BUILDER
# ═══════════════════════════════════════════════════════════════
class UnderwaterEnv:
    """Tạo các mesh/element môi trường đại dương."""

    @staticmethod
    def water_surface(size=60.0, grid=24):
        """Lưới mặt nước (z≈0) kích thước size×size."""
        xs = np.linspace(-size/2, size/2, grid)
        ys = np.linspace(-size/2, size/2, grid)
        XX, YY = np.meshgrid(xs, ys)
        verts  = np.stack([XX.ravel(), YY.ravel(),
                           np.zeros(grid*grid)], axis=1).astype(np.float32)
        faces  = []
        for iy in range(grid-1):
            for ix in range(grid-1):
                i0 = iy*grid+ix
                faces += [[i0, i0+1, i0+grid+1], [i0, i0+grid+1, i0+grid]]
        return verts, np.array(faces, dtype=np.int32), XX, YY

    @staticmethod
    def seafloor(size=90.0, grid=22, depth=-18.0):
        """Đáy biển terrain lồi lõm ngẫu nhiên."""
        np.random.seed(42)   # seed cố định để không thay đổi mỗi lần load
        xs = np.linspace(-size/2, size/2, grid)
        ys = np.linspace(-size/2, size/2, grid)
        XX, YY = np.meshgrid(xs, ys)
        ZZ = (np.sin(XX*0.28)*0.55 + np.cos(YY*0.22)*0.45
            + np.sin((XX+YY)*0.14)*0.35
            + np.random.uniform(-0.25, 0.25, XX.shape))
        ZZ = ZZ * 1.2 + depth
        verts = np.stack([XX.ravel(), YY.ravel(), ZZ.ravel()], axis=1).astype(np.float32)
        faces = []
        for iy in range(grid-1):
            for ix in range(grid-1):
                i0 = iy*grid+ix
                faces += [[i0, i0+1, i0+grid+1], [i0, i0+grid+1, i0+grid]]
        return verts, np.array(faces, dtype=np.int32)

    @staticmethod
    def god_ray_lines(n=8, length=15.0, spread=6.0):
        """Tia sáng từ mặt nước xuống đáy."""
        lines = []
        for i in range(n):
            angle = i * 2*math.pi / n + 0.3
            ox = math.cos(angle) * spread * 0.25 + np.random.uniform(-0.5, 0.5)
            oy = math.sin(angle) * spread * 0.25 + np.random.uniform(-0.5, 0.5)
            dx = math.cos(angle) * np.random.uniform(0.5, 2.0)
            dy = math.sin(angle) * np.random.uniform(0.5, 2.0)
            # 20 điểm interpolate dọc tia sáng
            t_arr = np.linspace(0, 1, 20)
            pts = np.stack([
                ox + t_arr * dx,
                oy + t_arr * dy,
                -t_arr * length
            ], axis=1).astype(np.float32)
            lines.append(pts)
        return lines


# ═══════════════════════════════════════════════════════════════
# GL ROV WIDGET  ← Widget chính
# ═══════════════════════════════════════════════════════════════
class GLROVWidget(gl.GLViewWidget):
    """
    Widget OpenGL 3D nhúng vào guirov.py (thay thế opw_motion).
    Môi trường đại dương sinh động với HUD overlay và 3 chế độ camera.
    """

    MAX_TRAJ_POINTS = 600

    def __init__(self, parent=None):
        super().__init__(parent=parent)

        # ── Trạng thái ROV ──────────────────────────────────────
        self._model_config  = None
        self._cad_file      = None
        self._current_pos   = np.zeros(3, dtype=np.float32)
        self._current_quat  = np.array([0., 0., 0., 1.], dtype=np.float32)
        self._origin        = None
        self._traj_pts      = []
        self._follow_mode   = True   # legacy compat
        self._heading       = 0.0
        self._depth         = 0.0
        self._speed         = 0.0
        self._roll          = 0.0
        self._pitch         = 0.0

        # ── Camera state ──────────────────────────────────────
        self._cam_mode    = CameraMode.FOLLOW
        self._orbit_yaw   = 45.0
        self._cam_actual  = np.zeros(3, dtype=np.float32)   # lerp target

        # ── GL item lists ────────────────────────────────────
        self._rov_items    = []
        self._axis_items   = []
        self._traj_item    = None
        self._slam_item    = None
        self._fov_item     = None

        # Water surface
        self._water_mesh       = None
        self._water_faces      = None
        self._water_verts_base = None
        self._water_XX         = None
        self._water_YY         = None
        self._water_t          = 0.0

        # God rays
        self._god_ray_items = []

        # Origin markers
        self._origin_grid   = None
        self._origin_sphere = None

        # Bubbles
        self._n_bubbles    = 220
        self._bubble_pts   = np.zeros((self._n_bubbles, 3), dtype=np.float32)
        self._bubble_spd   = np.random.uniform(0.018, 0.055, self._n_bubbles)
        self._bubble_size  = np.random.uniform(2.0, 5.5, self._n_bubbles)
        self._bubble_item  = None

        # ── HUD overlay ──────────────────────────────────────
        self._hud = _HUDOverlay(self)
        self._hud.setGeometry(self.rect())

        # ── Khởi tạo cảnh ───────────────────────────────────
        self._setup_scene()

        # ── Context menu ─────────────────────────────────────
        self.setContextMenuPolicy(
            QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        # ── Timer hoạt họa môi trường (20 FPS) ──────────────
        self._env_timer = QtCore.QTimer(self)
        self._env_timer.timeout.connect(self._animate_environment)
        self._env_timer.start(50)

    # ──────────────────────────────────────────────────────────
    # RESIZE — giữ HUD overlay đúng kích thước
    # ──────────────────────────────────────────────────────────
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, '_hud'):
            self._hud.setGeometry(self.rect())

    # ──────────────────────────────────────────────────────────
    # THIẾT LẬP CẢNH
    # ──────────────────────────────────────────────────────────
    def _setup_scene(self):
        """Khởi tạo toàn bộ cảnh underwater: nền, đáy, nước, tia sáng, bong bóng."""

        # Nền xanh đại dương sâu
        self.setBackgroundColor(pg.mkColor(3, 9, 22))
        self.setCameraPosition(distance=4.0, elevation=20, azimuth=45)

        # ── 1. Đáy biển terrain ──────────────────────────────
        sf_v, sf_f = UnderwaterEnv.seafloor()
        # Màu gradient: nâu tối → xanh đen
        n_sf = len(sf_f)
        sf_z = sf_v[sf_f[:, 0], 2]  # z của đỉnh đầu mỗi tam giác
        z_min, z_max = sf_z.min(), sf_z.max()
        t_sf = np.clip((sf_z - z_min) / max(z_max - z_min, 1e-6), 0, 1)
        sf_colors = np.zeros((n_sf, 4), dtype=np.float32)
        sf_colors[:, 0] = 0.05 + t_sf * 0.07
        sf_colors[:, 1] = 0.08 + t_sf * 0.10
        sf_colors[:, 2] = 0.14 + t_sf * 0.16
        sf_colors[:, 3] = 1.0
        seafloor = gl.GLMeshItem(
            vertexes=sf_v, faces=sf_f, faceColors=sf_colors,
            smooth=True, drawEdges=False
        )
        self.addItem(seafloor)

        # ── 2. Lưới mốc tọa độ gốc (origin launch pad) ───────
        self._origin_grid = gl.GLGridItem()
        self._origin_grid.setSize(6, 6)
        self._origin_grid.setSpacing(1, 1)
        self._origin_grid.setColor(pg.mkColor(255, 130, 0, 150))
        self._origin_grid.translate(0, 0, -0.01)
        self.addItem(self._origin_grid)

        sph_md = gl.MeshData.sphere(rows=12, cols=24, radius=0.09)
        self._origin_sphere = gl.GLMeshItem(
            meshdata=sph_md, color=(1.0, 0.5, 0.0, 0.9),
            smooth=True, drawEdges=False
        )
        self._origin_sphere.setGLOptions('translucent')
        self.addItem(self._origin_sphere)

        # ── 3. Trục tọa độ thế giới (không bao giờ biến mất) ──
        self._add_world_axes(length=2.5, width=3.0)

        # ── 4. God Rays ────────────────────────────────────────
        for ray_pts in UnderwaterEnv.god_ray_lines(n=8):
            n_seg = len(ray_pts)
            alpha = np.linspace(0.14, 0.0, n_seg)
            c = np.zeros((n_seg, 4), dtype=np.float32)
            c[:, 0] = 0.25; c[:, 1] = 0.65; c[:, 2] = 1.0
            c[:, 3] = alpha
            ray = gl.GLLinePlotItem(
                pos=ray_pts, color=c, width=2.5, antialias=True
            )
            ray.setGLOptions('additive')
            self.addItem(ray)
            self._god_ray_items.append(ray)

        # ── 5. Mặt nước (z=0, animated sine wave) ──────────────
        ws_v, ws_f, self._water_XX, self._water_YY = UnderwaterEnv.water_surface()
        self._water_verts_base = ws_v.copy()
        self._water_faces      = ws_f

        n_wsf = len(ws_f)
        ws_colors = np.zeros((n_wsf, 4), dtype=np.float32)
        ws_colors[:, 0] = 0.00
        ws_colors[:, 1] = 0.28
        ws_colors[:, 2] = 0.60
        ws_colors[:, 3] = 0.20
        self._water_mesh = gl.GLMeshItem(
            vertexes=ws_v, faces=ws_f, faceColors=ws_colors,
            smooth=True, drawEdges=True,
            edgeColor=(0.0, 0.45, 0.75, 0.04)
        )
        self._water_mesh.setGLOptions('translucent')
        self.addItem(self._water_mesh)

        # ── 6. Bong bóng nước ──────────────────────────────────
        self._bubble_pts[:, 0] = np.random.uniform(-10.0, 10.0, self._n_bubbles)
        self._bubble_pts[:, 1] = np.random.uniform(-10.0, 10.0, self._n_bubbles)
        self._bubble_pts[:, 2] = np.random.uniform(-9.0, 0.0, self._n_bubbles)

        self._bubble_item = gl.GLScatterPlotItem(
            pos=self._bubble_pts,
            color=(0.5, 0.82, 1.0, 0.45),
            size=self._bubble_size,
            pxMode=True
        )
        self._bubble_item.setGLOptions('additive')
        self.addItem(self._bubble_item)

    def _add_world_axes(self, length=2.5, width=3.0):
        """Trục thế giới X(đỏ), Y(xanh lá), Z(xanh dương) + sphere endpoint."""
        dirs   = [[length, 0, 0], [0, length, 0], [0, 0, length]]
        colors = [(1.0, 0.2, 0.2, 0.9), (0.2, 1.0, 0.2, 0.9), (0.2, 0.2, 1.0, 0.9)]
        labels = ['X', 'Y', 'Z']
        for d, c in zip(dirs, colors):
            pts  = np.array([[0, 0, 0], d], dtype=np.float32)
            line = gl.GLLinePlotItem(pos=pts, color=c, width=width, antialias=True)
            self.addItem(line)
            self._axis_items.append(line)
            sph = gl.GLMeshItem(
                meshdata=gl.MeshData.sphere(rows=8, cols=16, radius=0.09),
                color=c, smooth=True, drawEdges=False
            )
            sph.translate(*d)
            self.addItem(sph)
            self._axis_items.append(sph)

    # ──────────────────────────────────────────────────────────
    # HOẠT HỌA MÔI TRƯỜNG (gọi bởi _env_timer, 20 FPS)
    # ──────────────────────────────────────────────────────────
    def _animate_environment(self):
        """Cập nhật sóng nước + bong bóng."""
        self._water_t += 0.045
        t = self._water_t

        # Animate water surface vertices (sine wave overlay)
        new_v = self._water_verts_base.copy()
        XX    = self._water_XX.ravel()
        YY    = self._water_YY.ravel()
        new_v[:, 2] = (
            0.055 * np.sin(XX * 1.1 + t * 2.2) +
            0.040 * np.cos(YY * 0.85 + t * 1.6) +
            0.025 * np.sin((XX + YY) * 0.5 + t * 0.9)
        )
        n_wf = len(self._water_faces)
        ws_c = np.zeros((n_wf, 4), dtype=np.float32)
        ws_c[:, 0] = 0.00
        ws_c[:, 1] = 0.28
        ws_c[:, 2] = 0.60
        ws_c[:, 3] = 0.20
        self._water_mesh.setMeshData(
            vertexes=new_v,
            faces=self._water_faces,
            faceColors=ws_c
        )

        # Animate bubbles
        rp = self._current_pos
        self._bubble_pts[:, 2] += self._bubble_spd

        reset_mask = self._bubble_pts[:, 2] > (rp[2] + 1.5)
        n_reset = reset_mask.sum()
        if n_reset:
            self._bubble_pts[reset_mask, 0] = rp[0] + np.random.uniform(-9, 9, n_reset)
            self._bubble_pts[reset_mask, 1] = rp[1] + np.random.uniform(-9, 9, n_reset)
            self._bubble_pts[reset_mask, 2] = rp[2] - np.random.uniform(6, 10, n_reset)

        self._bubble_item.setData(pos=self._bubble_pts)

    # ──────────────────────────────────────────────────────────
    # CONTEXT MENU — R-Click đổi camera
    # ──────────────────────────────────────────────────────────
    def _show_context_menu(self, pos):
        menu = QtWidgets.QMenu(self)
        menu.setStyleSheet("""
            QMenu { background:#0D1726; color:#A0C0D0; border:1px solid #1E4060; }
            QMenu::item:selected { background:#003060; }
        """)
        act_follow  = menu.addAction("📹  FOLLOW Mode  (Camera bám theo)")
        act_orbit   = menu.addAction("🔄  ORBIT Mode   (Camera xoay vòng)")
        act_topdown = menu.addAction("🗺   TOP-DOWN Mode (Nhìn từ trên)")
        menu.addSeparator()
        act_reset   = menu.addAction("🎯  Reset Origin")
        act_clear   = menu.addAction("🗑   Clear Trajectory")

        # Đánh dấu mode hiện tại
        for act, mode in [(act_follow, CameraMode.FOLLOW),
                          (act_orbit,  CameraMode.ORBIT),
                          (act_topdown,CameraMode.TOP_DOWN)]:
            if self._cam_mode == mode:
                act.setCheckable(True)
                act.setChecked(True)

        action = menu.exec(self.mapToGlobal(pos))
        if action == act_follow:
            self._cam_mode = CameraMode.FOLLOW
            self._hud.update_data(cam_mode="FOLLOW")
        elif action == act_orbit:
            self._cam_mode  = CameraMode.ORBIT
            self._orbit_yaw = self._get_current_azimuth()
            self._hud.update_data(cam_mode="ORBIT")
        elif action == act_topdown:
            self._cam_mode = CameraMode.TOP_DOWN
            self._hud.update_data(cam_mode="TOP-DOWN")
        elif action == act_reset:
            self.reset_origin()
        elif action == act_clear:
            self._reset_trajectory()

    def _get_current_azimuth(self) -> float:
        opts = self.cameraParams()
        return opts.get('azimuth', 45.0)

    # ──────────────────────────────────────────────────────────
    # THIẾT LẬP MODEL ROV
    # ──────────────────────────────────────────────────────────
    def set_model(self, model, cad_file: str = None):
        self._model_config = model.get_visual_config()
        self._cad_file     = cad_file

        for item in self._rov_items:
            self.removeItem(item)
        self._rov_items.clear()

        if cad_file:
            self._build_cad_model(cad_file)
        else:
            self._build_proc_model()

        # Trục cục bộ gắn vào thân tàu
        self._rov_items.extend(self._build_local_axes())
        self._reset_trajectory()

    def _build_local_axes(self) -> list:
        items = []
        length = 0.55
        dirs   = [[length,0,0],[0,length,0],[0,0,length]]
        colors = [(1.,0.,0.,1.),(0.,1.,0.,1.),(0.,0.,1.,1.)]
        for d, c in zip(dirs, colors):
            pts  = np.array([[0,0,0], d], dtype=np.float32)
            line = gl.GLLinePlotItem(pos=pts, color=c, width=2.0, antialias=True)
            self.addItem(line)
            items.append(line)
        return items

    def _build_cad_model(self, filepath: str):
        verts, faces = CADLoader.load(filepath)
        if verts is None:
            print("[GLROVWidget] CAD load failed, using procedural mesh.")
            self._build_proc_model()
            return
        scale  = 1.0 / max(np.ptp(verts, axis=0))
        verts  = (verts - verts.mean(axis=0)) * scale
        # Màu metallic ocean blue
        n_f    = len(faces)
        colors = np.zeros((n_f, 4), dtype=np.float32)
        colors[:, 0] = 0.08
        colors[:, 1] = 0.38
        colors[:, 2] = 0.85
        colors[:, 3] = 0.88
        mesh = gl.GLMeshItem(
            vertexes=verts, faces=faces, faceColors=colors,
            smooth=True, drawEdges=True,
            edgeColor=(0.0, 0.8, 1.0, 0.25)
        )
        self.addItem(mesh)
        self._rov_items.append(mesh)

    def _build_proc_model(self):
        cfg = self._model_config
        if cfg is None:
            return
        cs = cfg["chassis"]
        if "size" in cs:
            box_dims = cs["size"]
        else:
            box_dims = [cs.get("length",0.40), cs.get("width",0.30), cs.get("height",0.20)]
        v, f = ProcMeshBuilder.box(*box_dims)
        colors = np.tile(list(cs["color"]), (len(f), 1))
        body = gl.GLMeshItem(
            vertexes=v, faces=f, faceColors=colors,
            smooth=False, drawEdges=True, edgeColor=cs["edge_color"]
        )
        self.addItem(body)
        self._rov_items.append(body)

        if "foam_block" in cfg:
            fb  = cfg["foam_block"]
            v2, f2 = ProcMeshBuilder.box(*fb["size"])
            v2 += np.array(fb["offset"])
            c2  = np.tile(list(fb["color"]), (len(f2), 1))
            foam = gl.GLMeshItem(
                vertexes=v2, faces=f2, faceColors=c2,
                smooth=False, drawEdges=True, edgeColor=fb["edge_color"]
            )
            self.addItem(foam)
            self._rov_items.append(foam)

        for ht in cfg.get("horizontal_thrusters", []):
            self._add_thruster_h(ht["pos"], ht["angle_deg"])
        for vt in cfg.get("vertical_thrusters", []):
            self._add_thruster_v(vt["pos"])
        for lt in cfg.get("headlights", []):
            self._add_headlight(lt["pos"])

    def _add_thruster_h(self, pos, angle_deg):
        v, f = ProcMeshBuilder.cylinder(0.028, 0.11, 10)
        a    = math.radians(angle_deg)
        rot  = np.array([[math.cos(a),-math.sin(a),0],
                         [math.sin(a), math.cos(a),0],
                         [0,           0,           1]])
        v = v @ rot.T + np.array(pos)
        c = np.tile([0.25, 0.72, 1.0, 0.92], (len(f), 1))
        m = gl.GLMeshItem(vertexes=v, faces=f, faceColors=c,
                          smooth=True, drawEdges=False)
        self.addItem(m)
        self._rov_items.append(m)

    def _add_thruster_v(self, pos):
        v, f = ProcMeshBuilder.cylinder(0.028, 0.09, 10)
        v   += np.array(pos)
        c    = np.tile([0.55, 0.92, 1.0, 0.92], (len(f), 1))
        m    = gl.GLMeshItem(vertexes=v, faces=f, faceColors=c,
                             smooth=True, drawEdges=False)
        self.addItem(m)
        self._rov_items.append(m)

    def _add_headlight(self, pos):
        v, f = ProcMeshBuilder.cone(0.045, 0.22, 16)
        rot  = np.array([[0,0,1],[0,1,0],[-1,0,0]], dtype=np.float32)
        v    = v @ rot.T + np.array(pos)
        c    = np.tile([0.0, 0.95, 1.0, 0.12], (len(f), 1))
        m    = gl.GLMeshItem(vertexes=v, faces=f, faceColors=c,
                             smooth=True, drawEdges=False)
        m.setGLOptions('translucent')
        self.addItem(m)
        self._rov_items.append(m)

    # ──────────────────────────────────────────────────────────
    # CẬP NHẬT TRẠNG THÁI (gọi mỗi frame từ main.py)
    # ──────────────────────────────────────────────────────────
    def set_origin(self, position: np.ndarray):
        self._origin = position.copy()

    def update_pose(self, position: np.ndarray, quat_xyzw: np.ndarray,
                    heading_deg: float = 0.0, depth_m: float = 0.0,
                    speed_mps: float = 0.0, roll_deg: float = 0.0,
                    pitch_deg: float = 0.0):
        # Dịch về hệ gốc widget
        if self._origin is not None:
            pos = position - self._origin
        else:
            pos = position.copy()

        # NED → OpenGL (X→X, Y→−Y, Z→−Z)
        gl_pos = np.array([pos[0], -pos[1], -pos[2]], dtype=np.float32)
        self._current_pos  = gl_pos
        self._current_quat = quat_xyzw.copy()
        self._heading      = heading_deg
        self._depth        = depth_m
        self._speed        = speed_mps
        self._roll         = roll_deg
        self._pitch        = pitch_deg

        # Áp transform mesh
        self._apply_transform(gl_pos, quat_xyzw)

        # Di chuyển water surface + god rays theo ROV
        self._water_verts_base[:, :2] = (
            UnderwaterEnv.water_surface.__func__(
                UnderwaterEnv, 60.0, 24
            )[0][:, :2] + np.array([gl_pos[0], gl_pos[1]])
            if False   # Tắt tính năng này để không rebuild mesh mỗi frame
            else self._water_verts_base[:, :2]   # giữ nguyên
        )

        # Update HUD
        self._hud.update_data(
            depth   = depth_m,
            heading = heading_deg,
            pos     = [pos[0], pos[1], pos[2]],
            speed   = speed_mps,
            roll    = roll_deg,
            pitch   = pitch_deg,
        )

        # Camera update
        self._update_camera(gl_pos)

    def _apply_transform(self, pos, quat_xyzw):
        qx, qy, qz, qw = quat_xyzw
        sinr = 2*(qw*qx + qy*qz)
        cosr = 1 - 2*(qx*qx + qy*qy)
        roll  = math.degrees(math.atan2(sinr, cosr))
        sinp  = max(-1.0, min(1.0, 2*(qw*qy - qz*qx)))
        pitch = math.degrees(math.asin(sinp))
        siny  = 2*(qw*qz + qx*qy)
        cosy  = 1 - 2*(qy*qy + qz*qz)
        yaw   = math.degrees(math.atan2(siny, cosy))
        for item in self._rov_items:
            item.resetTransform()
            item.rotate(yaw,   0, 0, 1)
            item.rotate(pitch, 0, 1, 0)
            item.rotate(roll,  1, 0, 0)
            item.translate(*pos)

    def _update_camera(self, gl_pos):
        """Smooth camera với 3 chế độ."""
        # Lerp vị trí target
        alpha = 0.07
        self._cam_actual = (self._cam_actual * (1 - alpha)
                            + gl_pos * alpha).astype(np.float32)
        tgt = pg.Vector(*self._cam_actual)

        if self._cam_mode == CameraMode.FOLLOW:
            self.setCameraPosition(pos=tgt, distance=3.5,
                                   elevation=20, azimuth=45)
        elif self._cam_mode == CameraMode.ORBIT:
            self._orbit_yaw = (self._orbit_yaw + 0.35) % 360
            self.setCameraPosition(pos=tgt, distance=4.5,
                                   elevation=16, azimuth=self._orbit_yaw)
        elif self._cam_mode == CameraMode.TOP_DOWN:
            self.setCameraPosition(pos=tgt, distance=6.0,
                                   elevation=87, azimuth=0)

    def update_trajectory(self, x: float, y: float, z: float):
        self._traj_pts.append([x, -y, -z])
        if len(self._traj_pts) > self.MAX_TRAJ_POINTS:
            self._traj_pts.pop(0)
        if len(self._traj_pts) < 2:
            return
        pts = np.array(self._traj_pts, dtype=np.float32)
        n   = len(pts)
        t   = np.linspace(0, 1, n)
        col = np.zeros((n, 4), dtype=np.float32)
        col[:, 0] = 1.0 - t
        col[:, 1] = 0.80
        col[:, 2] = t
        col[:, 3] = 0.90
        if self._traj_item is not None:
            self._traj_item.setData(pos=pts, color=col)
        else:
            self._traj_item = gl.GLLinePlotItem(
                pos=pts, color=col, width=2.0,
                antialias=True, mode='line_strip'
            )
            self.addItem(self._traj_item)

    def update_slam_points(self, pts_xyz: np.ndarray):
        if pts_xyz is None or len(pts_xyz) == 0:
            return
        gl_pts       = pts_xyz.copy()
        gl_pts[:, 1] *= -1
        gl_pts[:, 2] *= -1
        dists  = np.linalg.norm(gl_pts, axis=1)
        max_d  = max(dists.max(), 1e-6)
        t      = np.clip(dists / max_d, 0, 1)
        colors = np.zeros((len(gl_pts), 4), dtype=np.float32)
        colors[:, 0] = 1.0 - t
        colors[:, 1] = t * 0.7
        colors[:, 2] = t
        colors[:, 3] = 0.80
        if self._slam_item is not None:
            self._slam_item.setData(pos=gl_pts, color=colors, size=2.5)
        else:
            self._slam_item = gl.GLScatterPlotItem(
                pos=gl_pts, color=colors, size=2.5, pxMode=True
            )
            self.addItem(self._slam_item)

    def update_fov_effect(self, heading_deg: float, fov_deg: float = 60.0):
        if self._fov_item is not None:
            self.removeItem(self._fov_item)
            self._fov_item = None
        pos  = self._current_pos
        half = math.radians(fov_deg / 2)
        yaw  = math.radians(heading_deg)
        L    = 2.2
        segs = 20
        pts  = [pos.tolist()]
        for i in range(segs + 1):
            a = yaw - half + (fov_deg / segs * i) * math.pi / 180
            pts.append([pos[0]+L*math.cos(a), pos[1]+L*math.sin(a), pos[2]])
        pts.append(pos.tolist())
        pts_arr = np.array(pts, dtype=np.float32)
        n   = len(pts_arr)
        alp = np.linspace(0.30, 0.0, n)
        c   = np.zeros((n, 4), dtype=np.float32)
        c[:, 0] = 0.0; c[:, 1] = 0.85; c[:, 2] = 1.0
        c[:, 3] = alp
        self._fov_item = gl.GLLinePlotItem(
            pos=pts_arr, color=c, width=1.5, antialias=True
        )
        self.addItem(self._fov_item)

    # ──────────────────────────────────────────────────────────
    # TIỆN ÍCH
    # ──────────────────────────────────────────────────────────
    def _reset_trajectory(self):
        self._traj_pts = []
        if self._traj_item is not None:
            self.removeItem(self._traj_item)
            self._traj_item = None

    def reset_origin(self):
        self._origin = None
        self._reset_trajectory()

    def set_follow_mode(self, enabled: bool):
        """Tương thích ngược với main.py."""
        self._cam_mode = CameraMode.FOLLOW if enabled else CameraMode.ORBIT
        self._hud.update_data(cam_mode=CameraMode.LABELS[self._cam_mode])
