"""
gl_compass_3d_widget.py - 3D Compass & Attitude Display Widget (v2.0)
=====================================================================
Widget la bàn 3D nâng cao, hiển thị đầy đủ tư thế ROV dưới nước:

  OpenGL 3D scene:
    - Mô hình ROV ở trung tâm, xoay chính xác theo Roll/Pitch/Yaw
    - 36 vạch tick marks mỗi 10° quanh vành ngoài
    - 4 vạch lớn + đốm màu chỉ N/E/S/W
    - 3 vòng tròn cự ly với alpha giảm dần ra ngoài
    - Pitch ladder lines (đường gạch ngang theo góc pitch)
    - Roll arc indicator (nửa cung trên chỉ góc roll)
    - Vector vận tốc 3D với đầu mũi tên (arrowhead cone)
    - Point cloud SLAM 3D quanh ROV

  QPainter HUD Overlay:
    - Nhãn chữ N / E / S / W rõ ràng màu đặc trưng
    - Số độ mỗi 45° (0° / 45° / 90°...)
    - Bảng giá trị Roll / Pitch / Yaw số
    - Tốc độ (m/s) + Độ sâu (m)
    - Vệt ngang Artificial Horizon (đường chân trời giả)

  API (giữ nguyên cho main.py):
    set_model(model, cad_file)
    update_state(quat_xyzw, vel_ned)
    update_slam_points(pts_xyz)
"""
import math
import numpy as np
from PyQt6 import QtCore, QtGui, QtWidgets
import pyqtgraph.opengl as gl
import pyqtgraph as pg

from GUI.widgets.gl_3d_widget import CADLoader, ProcMeshBuilder


# ═══════════════════════════════════════════════════════════════
# COMPASS HUD OVERLAY — QPainter 2D lên trên OpenGL scene
# ═══════════════════════════════════════════════════════════════
class _CompassHUD(QtWidgets.QWidget):
    """
    Lớp phủ trong suốt vẽ:
      - Nhãn hướng N/E/S/W + số độ mỗi 45°
      - Bảng Roll / Pitch / Yaw / Speed / Depth
      - Đường Artificial Horizon
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAutoFillBackground(False)

        # Trạng thái
        self._roll  = 0.0
        self._pitch = 0.0
        self._yaw   = 0.0    # heading (degrees, 0=North)
        self._speed = 0.0
        self._depth = 0.0

        self._font_xs  = QtGui.QFont("Consolas", 7)
        self._font_sm  = QtGui.QFont("Consolas", 8)
        self._font_md  = QtGui.QFont("Consolas", 9, QtGui.QFont.Weight.Bold)
        self._font_dir = QtGui.QFont("Consolas", 11, QtGui.QFont.Weight.Bold)

    def update_data(self, roll=None, pitch=None, yaw=None,
                    speed=None, depth=None):
        if roll  is not None: self._roll  = roll
        if pitch is not None: self._pitch = pitch
        if yaw   is not None: self._yaw   = yaw
        if speed is not None: self._speed = speed
        if depth is not None: self._depth = depth
        self.update()

    def paintEvent(self, event):
        if self.width() < 20 or self.height() < 20:
            return
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        W, H = self.width(), self.height()
        cx, cy = W // 2, H // 2
        r_outer = min(W, H) * 0.44

        # ── 1. Vòng ngoài la bàn — vạch tick + số độ ──────────
        # Vạch 36 cái mỗi 10°, lớn hơn ở mỗi 45°
        for deg_i in range(0, 360, 10):
            # Xoay theo heading (yaw) của ROV để la bàn quay cùng
            disp_ang = math.radians(deg_i - self._yaw)
            is_major = (deg_i % 45 == 0)
            r_in  = r_outer * (0.84 if is_major else 0.89)
            r_lbl = r_outer * 0.75

            x1 = cx + r_in    * math.sin(disp_ang)
            y1 = cy - r_in    * math.cos(disp_ang)
            x2 = cx + r_outer * math.sin(disp_ang)
            y2 = cy - r_outer * math.cos(disp_ang)

            if is_major:
                p.setPen(QtGui.QPen(QtGui.QColor(0, 190, 255, 200), 2))
            else:
                p.setPen(QtGui.QPen(QtGui.QColor(0, 130, 180, 110), 1))
            p.drawLine(int(x1), int(y1), int(x2), int(y2))

            # Số độ tại mỗi 45°
            if is_major:
                lx = cx + r_lbl * math.sin(disp_ang)
                ly = cy - r_lbl * math.cos(disp_ang)
                p.setFont(self._font_xs)
                p.setPen(QtGui.QColor(100, 180, 220, 170))
                txt = str(deg_i)
                fm  = p.fontMetrics()
                tw  = fm.horizontalAdvance(txt)
                p.drawText(int(lx - tw/2), int(ly + 4), txt)

        # ── 2. Nhãn hướng chính N / E / S / W ──────────────────
        directions = {
            "N": (0,   QtGui.QColor(255,  60,  60, 240)),   # Đỏ
            "E": (90,  QtGui.QColor(  0, 200, 255, 220)),   # Cyan
            "S": (180, QtGui.QColor(180, 180, 190, 200)),   # Xám
            "W": (270, QtGui.QColor(  0, 200, 255, 220)),   # Cyan
        }
        r_lbl_dir = r_outer * 0.62
        for name, (deg_abs, color) in directions.items():
            disp = math.radians(deg_abs - self._yaw)
            lx   = cx + r_lbl_dir * math.sin(disp)
            ly   = cy - r_lbl_dir * math.cos(disp)
            p.setFont(self._font_dir)
            p.setPen(color)
            fm  = p.fontMetrics()
            tw  = fm.horizontalAdvance(name)
            th  = fm.height()
            p.drawText(int(lx - tw/2), int(ly + th/3), name)

        # ── 3. Artificial Horizon (đường chân trời) ─────────────
        # Đường ngang chỉ pitch = 0 xoay theo roll
        hor_len  = r_outer * 0.55
        roll_rad = math.radians(self._roll)
        # Điểm 2 đầu đường horizon
        hx1 = cx - hor_len * math.cos(roll_rad)
        hy1 = cy + hor_len * math.sin(roll_rad)  # y nghịch chiều
        hx2 = cx + hor_len * math.cos(roll_rad)
        hy2 = cy - hor_len * math.sin(roll_rad)

        # Dịch chuyển theo pitch: 1° pitch ≈ r_outer*0.008 px
        pitch_px = self._pitch * r_outer * 0.008
        pen_hor  = QtGui.QPen(QtGui.QColor(255, 160, 0, 200), 2)
        pen_hor.setStyle(QtCore.Qt.PenStyle.SolidLine)
        p.setPen(pen_hor)
        p.drawLine(int(hx1), int(hy1 - pitch_px),
                   int(hx2), int(hy2 - pitch_px))

        # Pitch ladder lines mỗi ±10°, ±20°, ±30°
        for pdeg in [-30, -20, -10, 10, 20, 30]:
            offset = (pdeg - self._pitch) * r_outer * 0.008
            if abs(offset) > r_outer * 0.8:
                continue
            # Vạch ngang ngắn hơn so với horizon chính
            frac = 0.25 if abs(pdeg) == 10 else 0.38
            llen = r_outer * frac
            lx1  = cx - llen * math.cos(roll_rad)
            ly1  = cy + llen * math.sin(roll_rad)
            lx2  = cx + llen * math.cos(roll_rad)
            ly2  = cy - llen * math.sin(roll_rad)
            off_perp_x = -math.sin(roll_rad) * offset * (-1)
            off_perp_y = -math.cos(roll_rad) * offset

            p.setPen(QtGui.QPen(QtGui.QColor(255, 130, 0, 120), 1,
                                QtCore.Qt.PenStyle.DashLine))
            p.drawLine(int(lx1 + off_perp_x), int(ly1 + off_perp_y),
                       int(lx2 + off_perp_x), int(ly2 + off_perp_y))

            # Nhãn số
            p.setFont(self._font_xs)
            p.setPen(QtGui.QColor(200, 130, 0, 140))
            p.drawText(int(lx2 + off_perp_x) + 3,
                       int(ly2 + off_perp_y) + 4, f"{pdeg:+d}°")

        # ── 4. Đường chỉ heading (mũi tên trung tâm → North) ───
        head_r = r_outer * 0.42
        p.setPen(QtGui.QPen(QtGui.QColor(255, 60, 60, 200), 2))
        p.drawLine(cx, cy,
                   int(cx + head_r * math.sin(math.radians(-self._yaw))),
                   int(cy - head_r * math.cos(math.radians(-self._yaw))))

        # ── 5. Chấm tâm ─────────────────────────────────────────
        p.setPen(QtCore.Qt.PenStyle.NoPen)
        p.setBrush(QtGui.QColor(0, 200, 255, 220))
        p.drawEllipse(cx - 5, cy - 5, 10, 10)

        # ── 6. Bảng RPY + Speed + Depth (góc trái dưới) ─────────
        px, py_ = 5, H - 80
        pw, ph  = 140, 72

        p.setPen(QtCore.Qt.PenStyle.NoPen)
        p.setBrush(QtGui.QColor(0, 8, 30, 130))
        p.drawRoundedRect(px, py_, pw, ph, 6, 6)
        p.setPen(QtGui.QPen(QtGui.QColor(0, 80, 150, 80), 1))
        p.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(px, py_, pw, ph, 6, 6)

        # Roll
        rcolor = (QtGui.QColor(255, 80, 80) if abs(self._roll) > 30
                  else QtGui.QColor(0, 200, 200))
        p.setPen(rcolor)
        p.setFont(self._font_md)
        p.drawText(px + 6, py_ + 16, f"R  {self._roll:+6.1f}°")

        # Pitch
        pcolor = (QtGui.QColor(255, 160, 0) if abs(self._pitch) > 30
                  else QtGui.QColor(0, 200, 200))
        p.setPen(pcolor)
        p.drawText(px + 6, py_ + 32, f"P  {self._pitch:+6.1f}°")

        # Yaw (heading)
        p.setPen(QtGui.QColor(0, 220, 255, 230))
        p.drawText(px + 6, py_ + 48, f"Y  {self._yaw % 360:05.1f}°")

        # Speed + Depth
        p.setFont(self._font_xs)
        p.setPen(QtGui.QColor(140, 180, 200, 160))
        p.drawText(px + 6, py_ + 64,
                   f"SPD {self._speed:.2f}m/s  D {abs(self._depth):.1f}m")

        p.end()


# ═══════════════════════════════════════════════════════════════
# GL COMPASS 3D WIDGET  ← Widget chính
# ═══════════════════════════════════════════════════════════════
class GLCompass3DWidget(gl.GLViewWidget):
    """
    Widget La bàn 3D và Attitude Display.
    ROV luôn ở trung tâm, xoay theo đúng Roll/Pitch/Yaw.
    Camera cố định nhìn từ trên nghiêng, đủ gần để thấy rõ tư thế.
    """

    BG_COLOR        = (0.018, 0.038, 0.072, 1.0)
    COLOR_VEL       = (1.0, 0.78, 0.0, 0.95)   # Vàng gold
    COLOR_NORTH     = (1.0, 0.22, 0.22, 1.0)    # Đỏ
    COLOR_RING_NEAR = (0.0, 0.72, 1.0, 0.60)    # Cyan sáng
    COLOR_RING_MID  = (0.0, 0.55, 0.85, 0.40)
    COLOR_RING_FAR  = (0.0, 0.40, 0.70, 0.22)

    def __init__(self, parent=None):
        super().__init__(parent=parent)

        # Trạng thái
        self._model_config = None
        self._cad_file     = None
        self._current_quat = np.array([0., 0., 0., 1.])
        self._velocity     = np.zeros(3)
        self._depth        = 0.0
        self._roll         = 0.0
        self._pitch        = 0.0
        self._yaw          = 0.0
        self._speed        = 0.0

        # GL items
        self._rov_items      = []
        self._ring_items     = []
        self._tick_items     = []
        self._dir_items      = []
        self._vel_items      = []   # velocity arrow (line + cone)
        self._slam_item      = None
        self._pitch_lines    = []
        self._roll_arc_item  = None

        # HUD overlay
        self._hud = _CompassHUD(self)
        self._hud.setGeometry(self.rect())

        self._setup_scene()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, '_hud'):
            self._hud.setGeometry(self.rect())

    # ──────────────────────────────────────────────────────────
    # THIẾT LẬP CẢNH
    # ──────────────────────────────────────────────────────────
    def _setup_scene(self):
        """Khởi tạo: nền, vòng la bàn, tick marks, trục."""
        self.setBackgroundColor(pg.mkColor(5, 10, 18))
        # Góc nhìn gần hơn, đủ thấy roll/pitch rõ ràng
        self.setCameraPosition(distance=1.55, elevation=32, azimuth=30)

        # Vòng la bàn (3 vòng tròn cự ly)
        self._draw_compass_rings()

        # Tick marks (36 vạch mỗi 10°)
        self._draw_tick_marks()

        # Điểm hướng chính N/E/S/W (sphere màu)
        self._draw_direction_markers()

        # Đường gạch nối N↔S và E↔W
        for pts_2d in [
            [[-1.65,0,0],[1.65,0,0]],
            [[0,-1.65,0],[0,1.65,0]]
        ]:
            ln = gl.GLLinePlotItem(
                pos=np.array(pts_2d, dtype=np.float32),
                color=(0.08, 0.28, 0.48, 0.35),
                width=1.0, antialias=True
            )
            self.addItem(ln)
            self._ring_items.append(ln)

        # Trục Z nhỏ chỉ up/down (xanh dương mờ)
        z_line = gl.GLLinePlotItem(
            pos=np.array([[0,0,-0.6],[0,0,0.6]], dtype=np.float32),
            color=(0.2, 0.4, 1.0, 0.45),
            width=1.5, antialias=True
        )
        self.addItem(z_line)
        self._ring_items.append(z_line)

    def _draw_compass_rings(self):
        """Vẽ 3 vòng tròn cự ly la bàn."""
        for item in self._ring_items:
            self.removeItem(item)
        self._ring_items.clear()

        configs = [
            (0.55, self.COLOR_RING_NEAR, 2.0),
            (1.05, self.COLOR_RING_MID,  1.8),
            (1.60, self.COLOR_RING_FAR,  1.5),
        ]
        segs = 72
        angles = np.linspace(0, 2*math.pi, segs, endpoint=False)

        for r, color, width in configs:
            pts = np.zeros((segs + 1, 3), dtype=np.float32)
            pts[:segs, 0] = r * np.cos(angles)
            pts[:segs, 1] = r * np.sin(angles)
            pts[segs]     = pts[0]   # đóng vòng
            ring = gl.GLLinePlotItem(
                pos=pts, color=color, width=width,
                antialias=True, mode='line_strip'
            )
            self.addItem(ring)
            self._ring_items.append(ring)

        # Vòng nhỏ ở bên trên (elevation z=0.4)
        for r, color, width in [(0.55, self.COLOR_RING_NEAR, 1.2),
                                  (1.05, self.COLOR_RING_MID, 1.0)]:
            pts = np.zeros((segs + 1, 3), dtype=np.float32)
            pts[:segs, 0] = r * np.cos(angles)
            pts[:segs, 1] = r * np.sin(angles)
            pts[:, 2]     = 0.40
            pts[segs]     = pts[0]
            ring = gl.GLLinePlotItem(
                pos=pts, color=(*color[:3], color[3]*0.4),
                width=0.9, antialias=True, mode='line_strip'
            )
            self.addItem(ring)
            self._ring_items.append(ring)

    def _draw_tick_marks(self):
        """Vẽ 36 vạch tick mỗi 10° trên vành la bàn."""
        for item in self._tick_items:
            self.removeItem(item)
        self._tick_items.clear()

        r_inner = 1.55
        r_outer = 1.65
        r_major = 1.50   # Vạch lớn ở 45°

        for i in range(36):
            deg      = i * 10
            rad      = math.radians(deg)
            is_major = (deg % 45 == 0)
            r_in     = r_major if is_major else r_inner
            r_out    = r_outer

            x1 = r_in  * math.cos(rad)
            y1 = r_in  * math.sin(rad)
            x2 = r_out * math.cos(rad)
            y2 = r_out * math.sin(rad)

            pts = np.array([[x1, y1, 0.0], [x2, y2, 0.0]], dtype=np.float32)
            col = (0.0, 0.75, 1.0, 0.80) if is_major else (0.0, 0.50, 0.75, 0.40)
            w   = 2.0 if is_major else 1.0
            tick = gl.GLLinePlotItem(pos=pts, color=col, width=w, antialias=True)
            self.addItem(tick)
            self._tick_items.append(tick)

    def _draw_direction_markers(self):
        """Sphere màu + đường tia tại 4 hướng chính N/E/S/W."""
        for item in self._dir_items:
            self.removeItem(item)
        self._dir_items.clear()

        dirs = {
            "N": ([1.65, 0.0, 0.0], self.COLOR_NORTH,               0.065),
            "E": ([0.0, -1.65, 0.0], (0.0, 0.80, 1.0, 0.90),        0.050),
            "S": ([-1.65, 0.0, 0.0], (0.60, 0.65, 0.72, 0.80),      0.050),
            "W": ([0.0,  1.65, 0.0], (0.0, 0.80, 1.0, 0.90),        0.050),
        }
        for name, (pos, color, radius) in dirs.items():
            sph = gl.GLMeshItem(
                meshdata=gl.MeshData.sphere(rows=10, cols=20, radius=radius),
                color=color, smooth=True, drawEdges=False
            )
            sph.translate(*pos)
            sph.setGLOptions('translucent')
            self.addItem(sph)
            self._dir_items.append(sph)

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

        self._apply_transform(self._current_quat)

    def _build_cad_model(self, filepath: str):
        verts, faces = CADLoader.load(filepath)
        if verts is None:
            self._build_proc_model()
            return
        # Scale nhỏ vừa radar (~0.38m)
        scale = 0.38 / max(np.ptp(verts, axis=0))
        verts = (verts - verts.mean(axis=0)) * scale
        n_f   = len(faces)
        colors = np.zeros((n_f, 4), dtype=np.float32)
        colors[:, 0] = 0.05
        colors[:, 1] = 0.42
        colors[:, 2] = 0.90
        colors[:, 3] = 0.85
        mesh = gl.GLMeshItem(
            vertexes=verts, faces=faces, faceColors=colors,
            smooth=True, drawEdges=True,
            edgeColor=(0.0, 0.85, 1.0, 0.30)
        )
        self.addItem(mesh)
        self._rov_items.append(mesh)

    def _build_proc_model(self):
        cfg = self._model_config
        if cfg is None:
            return
        sf    = 0.72
        cs    = cfg["chassis"]

        # Hỗ trợ cả 2 kiểu config
        if "size" in cs:
            size = [s * sf for s in cs["size"]]
        else:
            size = [cs.get("length",0.40)*sf,
                    cs.get("width", 0.30)*sf,
                    cs.get("height",0.20)*sf]

        v, f = ProcMeshBuilder.box(*size)
        col  = np.tile(list(cs["color"]), (len(f), 1))
        body = gl.GLMeshItem(
            vertexes=v, faces=f, faceColors=col,
            smooth=False, drawEdges=True, edgeColor=cs["edge_color"]
        )
        self.addItem(body)
        self._rov_items.append(body)

        if "foam_block" in cfg:
            fb      = cfg["foam_block"]
            fb_size = [s * sf for s in fb["size"]]
            v2, f2  = ProcMeshBuilder.box(*fb_size)
            v2     += np.array(fb["offset"]) * sf
            c2      = np.tile(list(fb["color"]), (len(f2), 1))
            foam    = gl.GLMeshItem(
                vertexes=v2, faces=f2, faceColors=c2,
                smooth=False, drawEdges=True, edgeColor=fb["edge_color"]
            )
            self.addItem(foam)
            self._rov_items.append(foam)

    # ──────────────────────────────────────────────────────────
    # CẬP NHẬT TRẠNG THÁI
    # ──────────────────────────────────────────────────────────
    def update_state(self, quat_xyzw: np.ndarray, vel_ned: np.ndarray,
                     depth: float = 0.0):
        self._current_quat = quat_xyzw.copy()
        self._velocity     = vel_ned.copy()
        self._depth        = depth

        # Tính RPY từ quaternion
        qx, qy, qz, qw = quat_xyzw
        sinr = 2*(qw*qx + qy*qz)
        cosr = 1 - 2*(qx*qx + qy*qy)
        self._roll = math.degrees(math.atan2(sinr, cosr))

        sinp = max(-1.0, min(1.0, 2*(qw*qy - qz*qx)))
        self._pitch = math.degrees(math.asin(sinp))

        siny = 2*(qw*qz + qx*qy)
        cosy = 1 - 2*(qy*qy + qz*qz)
        self._yaw = math.degrees(math.atan2(siny, cosy)) % 360

        # Tốc độ
        vel_gl = np.array([vel_ned[0], -vel_ned[1], -vel_ned[2]])
        self._speed = float(np.linalg.norm(vel_gl))

        # Xoay model
        self._apply_transform(quat_xyzw)

        # Vẽ vector vận tốc có đầu mũi tên
        self._update_velocity_arrow(vel_gl)

        # Cập nhật HUD
        self._hud.update_data(
            roll  = self._roll,
            pitch = self._pitch,
            yaw   = self._yaw,
            speed = self._speed,
            depth = depth,
        )

    def _apply_transform(self, quat_xyzw):
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

    def _update_velocity_arrow(self, vel_gl: np.ndarray):
        """Vẽ vector vận tốc 3D: line + cone mũi tên."""
        # Xóa arrow cũ
        for item in self._vel_items:
            self.removeItem(item)
        self._vel_items.clear()

        speed = np.linalg.norm(vel_gl)
        if speed < 0.04:
            return

        max_len  = 0.80
        v_dir    = vel_gl / speed
        arr_len  = min(speed * 1.0, max_len)
        end_pt   = v_dir * arr_len
        cone_len = 0.12

        # Line thân mũi tên
        shaft_end = end_pt - v_dir * cone_len
        pts = np.array([[0., 0., 0.], shaft_end.tolist()], dtype=np.float32)
        line = gl.GLLinePlotItem(
            pos=pts, color=self.COLOR_VEL, width=4.0, antialias=True
        )
        self.addItem(line)
        self._vel_items.append(line)

        # Cone đầu mũi tên
        cv, cf = ProcMeshBuilder.cone(r=0.048, h=cone_len, segs=14)
        # Xoay cone về hướng vel_gl
        if abs(v_dir[2]) < 0.999:
            z_axis  = np.array([0., 0., 1.])
            rot_ax  = np.cross(z_axis, v_dir)
            rot_ax /= np.linalg.norm(rot_ax)
            rot_ang = math.degrees(math.acos(np.clip(np.dot(z_axis, v_dir), -1, 1)))
        else:
            rot_ax  = np.array([1., 0., 0.])
            rot_ang = 0.0 if v_dir[2] > 0 else 180.0

        cone_colors = np.tile(list(self.COLOR_VEL), (len(cf), 1))
        cone_mesh   = gl.GLMeshItem(
            vertexes=cv, faces=cf, faceColors=cone_colors,
            smooth=True, drawEdges=False
        )
        cone_mesh.translate(*shaft_end)
        cone_mesh.rotate(rot_ang, *rot_ax)
        self.addItem(cone_mesh)
        self._vel_items.append(cone_mesh)

    def update_slam_points(self, pts_xyz: np.ndarray):
        """Hiển thị point cloud 3D quanh ROV trong radar."""
        if pts_xyz is None or len(pts_xyz) == 0:
            return

        gl_pts = pts_xyz.copy()
        gl_pts[:, 1] *= -1
        gl_pts[:, 2] *= -1

        # Scale xuống để vừa radar (max 1.5m)
        dists      = np.linalg.norm(gl_pts, axis=1)
        valid_mask = dists <= 1.55
        gl_pts     = gl_pts[valid_mask]
        dists      = dists[valid_mask]

        if len(gl_pts) == 0:
            return

        # Màu theo khoảng cách: đỏ nguy hiểm → vàng cảnh báo → cyan an toàn
        colors = np.zeros((len(gl_pts), 4), dtype=np.float32)
        for i, d in enumerate(dists):
            if d < 0.50:
                colors[i] = [1.0, 0.08, 0.08, 0.90]
            elif d < 0.90:
                colors[i] = [1.0, 0.75, 0.00, 0.85]
            else:
                colors[i] = [0.00, 0.82, 1.00, 0.78]

        if self._slam_item is not None:
            self._slam_item.setData(pos=gl_pts, color=colors, size=3.5)
        else:
            self._slam_item = gl.GLScatterPlotItem(
                pos=gl_pts, color=colors, size=3.5, pxMode=True
            )
            self.addItem(self._slam_item)
