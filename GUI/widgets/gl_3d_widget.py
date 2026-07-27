"""
gl_3d_widget.py - 3D OpenGL ROV Visualization Widget (Underwater Edition v3.0)
===============================================================================
Nâng cấp toàn diện theo tiêu chuẩn GCS chuyên nghiệp (QGC / Blue Robotics):

  Màu sắc:
    - Nền teal sáng như nước biển thật (không dark navy)
    - Model CAD giữ màu gốc của file / màu xám metallic trung tính
    - Seafloor màu đá tự nhiên nâu-xám

  Quỹ đạo:
    - Lưu 2000 điểm (dài ≈33 giây @ 60 FPS), không tự mất
    - Gần: đường sáng solid liên tục (cyan, width 2.5)
    - Lịch sử: chấm mờ dày đặc (dotted persistent trail)
    - Cả 2 phai dần từ sáng → mờ theo thứ tự thời gian

  Chuột:
    - Trái giữ + kéo: xoay góc nhìn (được khôi phục)
    - Phải: context menu đổi camera
    - Cuộn: zoom
    - Khi user đang xoay: tạm dừng auto-camera (không giật)
    - Sau 4 giây không tương tác: camera follow lại mượt mà

  Camera 3 chế độ:
    - FOLLOW: Bám theo ROV (tạm dừng khi user đang thao tác chuột)
    - ORBIT : Xoay cinematic tự động quanh ROV
    - MAP   : Nhìn từ trên xuống dạng bản đồ

  Tính năng GCS nâng cao (nghiên cứu QGC/Mission Planner):
    - Waypoints 3D: sphere + số thứ tự + path line liên kết
    - Proximity Alert: vòng đỏ khi SLAM phát hiện vật thể gần
    - Depth Limit Plane: mặt phẳng cảnh báo max safe depth
    - Velocity vector 3D hiển thị ngay trên thân ROV
    - Scale bar trong HUD (m/pixel reference)
    - Home indicator: mốc xuất phát luôn hiển thị rõ
    - Distance-to-home: tính khoảng cách về Home trong HUD
"""
import math
import struct
import numpy as np
from pathlib import Path

from PyQt6 import QtCore, QtGui, QtWidgets
import pyqtgraph.opengl as gl
import pyqtgraph as pg


# ═══════════════════════════════════════════════════════════════
# CAMERA MODE
# ═══════════════════════════════════════════════════════════════
class CameraMode:
    FOLLOW   = 0
    ORBIT    = 1
    MAP      = 2
    MANUAL   = 3
    LABELS   = {FOLLOW: "FOLLOW", ORBIT: "ORBIT", MAP: "MAP", MANUAL: "MANUAL"}


# ═══════════════════════════════════════════════════════════════
# HUD OVERLAY
# ═══════════════════════════════════════════════════════════════
class _HUDOverlay(QtWidgets.QWidget):
    """QPainter HUD trong suốt phủ lên OpenGL canvas."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAutoFillBackground(False)

        self._depth      = 0.0
        self._heading    = 0.0
        self._pos        = [0., 0., 0.]
        self._speed      = 0.0
        self._cam_mode   = "FOLLOW"
        self._roll       = 0.0
        self._pitch      = 0.0
        self._dist_home  = 0.0       # khoảng cách về home (m)
        self._proximity  = False     # cảnh báo vật thể gần
        self._user_ctrl  = False     # user đang thao tác chuột

        self._font_xs = QtGui.QFont("Consolas", 7)
        self._font_sm = QtGui.QFont("Consolas", 9)
        self._font_md = QtGui.QFont("Consolas", 10, QtGui.QFont.Weight.Bold)
        self._font_lg = QtGui.QFont("Consolas", 14, QtGui.QFont.Weight.Bold)

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

        # ── 1. Proximity alert flash (nền đỏ mờ khi gần vật thể) ──
        if self._proximity:
            p.setPen(QtCore.Qt.PenStyle.NoPen)
            p.setBrush(QtGui.QColor(255, 0, 0, 30))
            p.drawRect(0, 0, W, H)
            p.setPen(QtGui.QColor(255, 60, 60, 220))
            p.setFont(self._font_md)
            p.drawText(W//2 - 80, H//2, "⚠ OBSTACLE NEAR")

        # ── 2. Depth bar (cạnh trái) ─────────────────────────────
        bx, by = 8, 36
        bw, bh = 13, H - 115
        max_d  = 60.0

        p.setPen(QtCore.Qt.PenStyle.NoPen)
        p.setBrush(QtGui.QColor(0, 0, 0, 70))
        p.drawRoundedRect(bx-4, by-14, bw+46, bh+38, 6, 6)

        p.setBrush(QtGui.QColor(0, 20, 40, 130))
        p.drawRoundedRect(bx, by, bw, bh, 4, 4)

        grad = QtGui.QLinearGradient(bx, by, bx, by+bh)
        grad.setColorAt(0.0,  QtGui.QColor(80, 220, 255, 230))
        grad.setColorAt(0.3,  QtGui.QColor(0,  170, 210, 210))
        grad.setColorAt(0.7,  QtGui.QColor(0,   90, 160, 200))
        grad.setColorAt(1.0,  QtGui.QColor(0,   30,  90, 195))
        p.setBrush(QtGui.QBrush(grad))
        ratio = min(abs(self._depth) / max_d, 1.0)
        fill  = int(bh * ratio)
        if fill > 0:
            p.drawRoundedRect(bx, by + bh - fill, bw, fill, 4, 4)

        # Tick
        p.setFont(self._font_xs)
        for dm in range(0, int(max_d)+1, 10):
            ty = by + int(bh * dm / max_d)
            p.setPen(QtGui.QPen(QtGui.QColor(0, 160, 200, 130), 1))
            p.drawLine(bx+bw, ty, bx+bw+5, ty)
            p.setPen(QtGui.QColor(80, 180, 220, 150))
            p.drawText(bx+bw+7, ty+4, f"{dm}m")

        p.setPen(QtGui.QColor(0, 230, 255, 230))
        p.setFont(self._font_md)
        p.drawText(bx-1, by+bh+18, f"{abs(self._depth):.1f}m")
        p.setFont(self._font_xs)
        p.setPen(QtGui.QColor(80, 160, 200, 140))
        p.drawText(bx, by-8, "DEPTH")

        # ── 3. Panel thông tin vị trí (trái trên) ─────────────────
        px, py_ = 44, 12
        pw, ph  = 185, 108

        p.setPen(QtCore.Qt.PenStyle.NoPen)
        p.setBrush(QtGui.QColor(0, 10, 30, 115))
        p.drawRoundedRect(px, py_, pw, ph, 8, 8)
        p.setPen(QtGui.QPen(QtGui.QColor(0, 140, 190, 60), 1))
        p.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(px, py_, pw, ph, 8, 8)

        p.setPen(QtGui.QColor(0, 220, 255, 230))
        p.setFont(self._font_md)
        p.drawText(px+10, py_+22, f"HDG  {self._heading:05.1f}°")

        p.setFont(self._font_sm)
        p.setPen(QtGui.QColor(50, 240, 200, 200))
        p.drawText(px+10, py_+42, f"X  {self._pos[0]:+8.2f} m")
        p.drawText(px+10, py_+57, f"Y  {self._pos[1]:+8.2f} m")
        p.drawText(px+10, py_+72, f"Z  {self._pos[2]:+8.2f} m")

        p.setFont(self._font_xs)
        p.setPen(QtGui.QColor(150, 200, 225, 170))
        p.drawText(px+10, py_+88, f"R {self._roll:+6.1f}°  P {self._pitch:+6.1f}°")

        # Distance to home
        dh_color = (QtGui.QColor(255, 100, 100)
                    if self._dist_home > 15 else QtGui.QColor(100, 220, 200))
        p.setPen(dh_color)
        p.drawText(px+10, py_+102, f"HOME  {self._dist_home:.1f} m")

        # ── 4. Speed badge (phải dưới) ────────────────────────────
        spd = self._speed
        sc  = (QtGui.QColor(0, 235, 255) if spd < 0.5
               else QtGui.QColor(255, 200, 0) if spd < 1.5
               else QtGui.QColor(255, 60, 60))
        sw, sh = 96, 52
        sx, sy_ = W-sw-10, H-sh-10

        p.setPen(QtCore.Qt.PenStyle.NoPen)
        p.setBrush(QtGui.QColor(0, 8, 30, 120))
        p.drawRoundedRect(sx, sy_, sw, sh, 8, 8)
        p.setPen(QtGui.QPen(sc.darker(140), 1))
        p.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(sx, sy_, sw, sh, 8, 8)

        p.setPen(sc)
        p.setFont(self._font_lg)
        p.drawText(sx+7, sy_+30, f"{spd:.2f}")
        p.setFont(self._font_xs)
        p.setPen(QtGui.QColor(150, 195, 215, 155))
        p.drawText(sx+7, sy_+44, "m/s  SPEED")

        # ── 5. Scale bar (phải dưới cùng) ────────────────────────
        sb_y = H - 20
        sb_x = W - 140
        sb_len = 60
        p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 180), 2))
        p.drawLine(sb_x, sb_y, sb_x+sb_len, sb_y)
        p.drawLine(sb_x, sb_y-4, sb_x, sb_y+4)
        p.drawLine(sb_x+sb_len, sb_y-4, sb_x+sb_len, sb_y+4)
        p.setFont(self._font_xs)
        p.setPen(QtGui.QColor(220, 220, 220, 180))
        p.drawText(sb_x + sb_len//2 - 8, sb_y - 6, "~ 2m")

        # ── 6. Camera mode + user control indicator ────────────────
        cam_col = (QtGui.QColor(255, 160, 0, 220)
                   if self._user_ctrl else QtGui.QColor(0, 200, 130, 200))
        p.setFont(self._font_xs)
        p.setPen(cam_col)
        label = (f"[MANUAL CAM]" if self._user_ctrl
                 else f"[CAM: {self._cam_mode}]")
        p.drawText(W-130, 14, label)
        p.setPen(QtGui.QColor(80, 130, 150, 130))
        p.drawText(W-155, 26, "L-drag:rotate  R:menu  Scroll:zoom")

        p.end()


# ═══════════════════════════════════════════════════════════════
# CAD LOADER
# ═══════════════════════════════════════════════════════════════
class CADLoader:
    """Tải STL / OBJ → (vertices, faces)."""

    @staticmethod
    def load(filepath: str):
        fp = Path(filepath)
        if not fp.exists():
            return None, None
        try:
            ext = fp.suffix.lower()
            if ext == ".stl":
                return CADLoader._load_stl(fp)
            elif ext == ".obj":
                return CADLoader._load_obj(fp)
        except Exception as e:
            print(f"[CADLoader] {e}")
        return None, None

    @staticmethod
    def _load_stl(fp):
        data = fp.read_bytes()
        try:
            n = struct.unpack_from('<I', data, 80)[0]
            if 84 + n * 50 == len(data):
                return CADLoader._binary_stl(data, n)
        except Exception:
            pass
        return CADLoader._ascii_stl(data.decode('utf-8', errors='ignore'))

    @staticmethod
    def _binary_stl(data, n):
        vs, fs = [], []
        off = 84
        for i in range(n):
            v0 = struct.unpack_from('<fff', data, off+12)
            v1 = struct.unpack_from('<fff', data, off+24)
            v2 = struct.unpack_from('<fff', data, off+36)
            b  = len(vs)
            vs += [v0, v1, v2]; fs.append([b, b+1, b+2])
            off += 50
        return np.array(vs, np.float32), np.array(fs, np.int32)

    @staticmethod
    def _ascii_stl(txt):
        vs, fs = [], []
        for ln in txt.splitlines():
            t = ln.strip().split()
            if len(t) >= 4 and t[0] == 'vertex':
                vs.append([float(t[1]), float(t[2]), float(t[3])])
        for i in range(0, len(vs)-2, 3):
            fs.append([i, i+1, i+2])
        return np.array(vs, np.float32), np.array(fs, np.int32)

    @staticmethod
    def _load_obj(fp):
        vs, fs = [], []
        with open(fp, 'r', errors='ignore') as f:
            for ln in f:
                t = ln.strip().split()
                if not t: continue
                if t[0] == 'v':
                    vs.append([float(t[1]), float(t[2]), float(t[3])])
                elif t[0] == 'f':
                    idx = [int(x.split('/')[0])-1 for x in t[1:]]
                    if len(idx) == 3:
                        fs.append(idx)
                    elif len(idx) == 4:
                        fs += [[idx[0],idx[1],idx[2]], [idx[0],idx[2],idx[3]]]
        if not vs or not fs:
            return None, None
        return np.array(vs, np.float32), np.array(fs, np.int32)


# ═══════════════════════════════════════════════════════════════
# PROC MESH BUILDER
# ═══════════════════════════════════════════════════════════════
class ProcMeshBuilder:

    @staticmethod
    def box(lx, ly, lz):
        hx,hy,hz = lx/2, ly/2, lz/2
        v = np.array([
            [-hx,-hy,-hz],[+hx,-hy,-hz],[+hx,+hy,-hz],[-hx,+hy,-hz],
            [-hx,-hy,+hz],[+hx,-hy,+hz],[+hx,+hy,+hz],[-hx,+hy,+hz],
        ], np.float32)
        f = np.array([
            [0,1,2],[0,2,3],[4,5,6],[4,6,7],
            [0,1,5],[0,5,4],[2,3,7],[2,7,6],
            [1,2,6],[1,6,5],[0,3,7],[0,7,4],
        ], np.int32)
        return v, f

    @staticmethod
    def cylinder(r, h, segs=12):
        ang = np.linspace(0, 2*np.pi, segs, endpoint=False)
        bv  = [[r*np.cos(a), r*np.sin(a), 0.] for a in ang]
        tv  = [[r*np.cos(a), r*np.sin(a), h]  for a in ang]
        v   = [[0.,0.,0.]] + bv + [[0.,0.,h]] + tv
        tc  = segs + 1
        f   = []
        for i in range(segs):
            f.append([0, 1+i, 1+(i+1)%segs])
            f.append([tc, tc+1+i, tc+1+(i+1)%segs])
            b0,b1 = 1+i, 1+(i+1)%segs
            t0,t1 = tc+1+i, tc+1+(i+1)%segs
            f += [[b0,b1,t1],[b0,t1,t0]]
        return np.array(v, np.float32), np.array(f, np.int32)

    @staticmethod
    def cone(r, h, segs=16):
        ang = np.linspace(0, 2*np.pi, segs, endpoint=False)
        bs  = [[r*np.cos(a), r*np.sin(a), 0.] for a in ang]
        v   = bs + [[0.,0.,h]]
        ai  = len(bs)
        f   = [[i,(i+1)%segs,ai] for i in range(segs)]
        for i in range(1, segs-1):
            f.append([0, i, i+1])
        return np.array(v, np.float32), np.array(f, np.int32)

    @staticmethod
    def sphere_simple(r=0.1, rows=8, cols=16):
        return gl.MeshData.sphere(rows=rows, cols=cols, radius=r)


# ═══════════════════════════════════════════════════════════════
# UNDERWATER ENVIRONMENT BUILDER
# ═══════════════════════════════════════════════════════════════
class UnderwaterEnv:

    @staticmethod
    def water_surface(size=70.0, grid=26):
        xs = np.linspace(-size/2, size/2, grid)
        ys = np.linspace(-size/2, size/2, grid)
        XX, YY = np.meshgrid(xs, ys)
        verts  = np.stack([XX.ravel(), YY.ravel(),
                           np.zeros(grid*grid)], axis=1).astype(np.float32)
        faces  = []
        for iy in range(grid-1):
            for ix in range(grid-1):
                i0 = iy*grid+ix
                faces += [[i0,i0+1,i0+grid+1],[i0,i0+grid+1,i0+grid]]
        return verts, np.array(faces, np.int32), XX, YY

    @staticmethod
    def seafloor(size=100.0, grid=24, depth=-16.0):
        np.random.seed(7)
        xs = np.linspace(-size/2, size/2, grid)
        ys = np.linspace(-size/2, size/2, grid)
        XX, YY = np.meshgrid(xs, ys)
        ZZ = (np.sin(XX*0.24)*0.6 + np.cos(YY*0.20)*0.5
            + np.sin((XX+YY)*0.12)*0.4
            + np.random.uniform(-0.30, 0.30, XX.shape))
        ZZ = ZZ * 1.4 + depth
        verts = np.stack([XX.ravel(), YY.ravel(), ZZ.ravel()], axis=1).astype(np.float32)
        faces = []
        for iy in range(grid-1):
            for ix in range(grid-1):
                i0 = iy*grid+ix
                faces += [[i0,i0+1,i0+grid+1],[i0,i0+grid+1,i0+grid]]
        return verts, np.array(faces, np.int32)

    @staticmethod
    def god_rays(n=8, length=13.0, spread=5.0):
        lines = []
        np.random.seed(3)
        for i in range(n):
            ang = i * 2*math.pi/n + 0.25
            ox  = math.cos(ang)*spread*0.2 + np.random.uniform(-0.6, 0.6)
            oy  = math.sin(ang)*spread*0.2 + np.random.uniform(-0.6, 0.6)
            dx  = math.cos(ang) * np.random.uniform(0.4, 1.8)
            dy  = math.sin(ang) * np.random.uniform(0.4, 1.8)
            t   = np.linspace(0, 1, 22)
            pts = np.stack([ox+t*dx, oy+t*dy, -t*length], axis=1).astype(np.float32)
            lines.append(pts)
        return lines


# ═══════════════════════════════════════════════════════════════
# GL ROV WIDGET  ← Widget chính
# ═══════════════════════════════════════════════════════════════
class GLROVWidget(gl.GLViewWidget):
    """
    Widget 3D OpenGL ROV - Underwater Edition v3.0
    Màu teal sáng, quỹ đạo bền vững, chuột xoay tự nhiên,
    tính năng GCS chuyên nghiệp (waypoints, alert, velocity vector...).
    """

    MAX_TRAJ_POINTS  = 2000    # ~33 giây @ 60 FPS
    TRAJ_DOT_STRIDE  = 4       # mỗi N điểm lịch sử vẽ 1 chấm
    USER_CAM_TIMEOUT = 4000    # ms - sau khi nhả chuột bao lâu mới follow lại

    def __init__(self, parent=None):
        super().__init__(parent=parent)

        # ── ROV state ─────────────────────────────────────────
        self._model_config = None
        self._cad_file     = None
        self._current_pos  = np.zeros(3, np.float32)
        self._current_quat = np.array([0.,0.,0.,1.], np.float32)
        self._origin       = None
        self._heading      = 0.0
        self._depth        = 0.0
        self._speed        = 0.0
        self._roll         = 0.0
        self._pitch        = 0.0

        # ── Trajectory ──────────────────────────────────────
        self._traj_pts = []        # list of [x,y,z] in GL coords

        # ── Camera ──────────────────────────────────────────
        self._cam_mode      = CameraMode.FOLLOW
        self._orbit_yaw     = 45.0
        self._cam_lerp_pos  = np.zeros(3, np.float32)   # smooth target
        self._user_ctrl     = False    # user đang thao tác chuột
        self._cam_resume_timer = QtCore.QTimer(self)
        self._cam_resume_timer.setSingleShot(True)
        self._cam_resume_timer.timeout.connect(self._on_cam_resume)

        # ── GL items ─────────────────────────────────────────
        self._rov_items     = []
        self._axis_items    = []
        self._traj_line     = None   # recent solid trail
        self._traj_dots     = None   # historical dotted trail
        self._slam_item     = None
        self._waypoint_items= []     # waypoint markers
        self._wp_path_item  = None   # waypoint connecting path
        self._depth_plane   = None   # max depth warning plane

        # ── Pre-allocated velocity arrow (reused, never deleted) ──
        self._vel_line = gl.GLLinePlotItem(
            pos=np.zeros((2, 3), np.float32),
            color=(1., 0.85, 0., 1.), width=3.5, antialias=True
        )
        self._vel_line.setVisible(False)
        self.addItem(self._vel_line)

        cv, cf = ProcMeshBuilder.cone(r=0.048, h=0.12, segs=14)
        cone_colors = np.tile([1., 0.85, 0., 1.], (len(cf), 1))
        self._vel_cone = gl.GLMeshItem(
            vertexes=cv, faces=cf, faceColors=cone_colors,
            smooth=True, drawEdges=False
        )
        self._vel_cone.setVisible(False)
        self.addItem(self._vel_cone)

        # ── Pre-allocated FOV effect line (reused) ───────────────
        self._fov_item = gl.GLLinePlotItem(
            pos=np.zeros((2, 3), np.float32),
            color=(0, 0.9, 1, 0.3), width=1.5, antialias=True
        )
        self._fov_item.setVisible(False)
        self.addItem(self._fov_item)

        # ── Pre-allocated proximity ring (reused) ────────────────
        self._prox_ring = gl.GLLinePlotItem(
            pos=np.zeros((2, 3), np.float32),
            color=(1., 0.1, 0.1, 0.85), width=3.0, antialias=True
        )
        self._prox_ring.setVisible(False)
        self.addItem(self._prox_ring)

        # ── Trajectory throttle counter ──────────────────────────
        self._traj_update_cnt = 0

        # Water surface state
        self._water_mesh    = None
        self._water_faces   = None
        self._water_base    = None
        self._water_XX      = None
        self._water_YY      = None
        self._water_t       = 0.0
        self._water_colors  = None

        # Bubbles
        self._n_bub   = 240
        self._bub_pts = np.zeros((self._n_bub, 3), np.float32)
        self._bub_spd = np.random.uniform(0.020, 0.058, self._n_bub)
        self._bub_sz  = np.random.uniform(2.0, 6.0, self._n_bub)
        self._bub_item = None

        # ── HUD overlay ──────────────────────────────────────
        self._hud = _HUDOverlay(self)
        self._hud.setGeometry(self.rect())

        self._setup_scene()

        # R-Click context menu
        self.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        # Env animation timer (20 FPS)
        self._env_timer = QtCore.QTimer(self)
        self._env_timer.timeout.connect(self._animate_env)
        self._env_timer.start(50)

    # ──────────────────────────────────────────────────────────
    # RESIZE
    # ──────────────────────────────────────────────────────────
    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        if hasattr(self, '_hud'):
            self._hud.setGeometry(self.rect())

    # ──────────────────────────────────────────────────────────
    # CHUỘT — khôi phục xoay + pause auto-camera
    # ──────────────────────────────────────────────────────────
    def mousePressEvent(self, ev):
        # Chỉ bắt L-click và M-click để xoay/pan; R-click → menu
        if ev.button() == QtCore.Qt.MouseButton.LeftButton:
            self._user_ctrl = True
            self._cam_resume_timer.stop()
            self._hud.update_data(user_ctrl=True)
        super().mousePressEvent(ev)

    def mouseReleaseEvent(self, ev):
        if ev.button() == QtCore.Qt.MouseButton.LeftButton:
            # MANUAL mode: không bao giờ tự resume camera
            if self._cam_mode != CameraMode.MANUAL:
                self._cam_resume_timer.start(self.USER_CAM_TIMEOUT)
        super().mouseReleaseEvent(ev)

    def _on_cam_resume(self):
        """Timer callback: hết timeout → camera follow lại."""
        # Không resume nếu đang ở chế độ MANUAL
        if self._cam_mode == CameraMode.MANUAL:
            return
        self._user_ctrl = False
        self._hud.update_data(user_ctrl=False)

    # ──────────────────────────────────────────────────────────
    # THIẾT LẬP CẢNH
    # ──────────────────────────────────────────────────────────
    def _setup_scene(self):
        # ── Nền teal sáng như nước biển ───────────────────────
        # Màu giống screenshot: turquoise #00889C
        self.setBackgroundColor(pg.mkColor(0, 120, 150))
        self.setCameraPosition(distance=4.0, elevation=20, azimuth=45)

        # ── Đáy biển terrain (nâu-xám đá) ─────────────────────
        sf_v, sf_f = UnderwaterEnv.seafloor()
        n_sf   = len(sf_f)
        sf_z   = sf_v[sf_f[:, 0], 2]
        z_min, z_max = sf_z.min(), sf_z.max()
        t_sf   = np.clip((sf_z - z_min) / max(z_max - z_min, 1e-6), 0, 1)
        sf_col = np.zeros((n_sf, 4), np.float32)
        # Màu đá: nâu xám tự nhiên
        sf_col[:, 0] = 0.28 + t_sf * 0.12   # R
        sf_col[:, 1] = 0.25 + t_sf * 0.10   # G
        sf_col[:, 2] = 0.20 + t_sf * 0.08   # B
        sf_col[:, 3] = 1.0
        seafloor = gl.GLMeshItem(
            vertexes=sf_v, faces=sf_f, faceColors=sf_col,
            smooth=True, drawEdges=False
        )
        self.addItem(seafloor)

        # ── Home marker (gốc tọa độ) ──────────────────────────
        orig_grid = gl.GLGridItem()
        orig_grid.setSize(5, 5)
        orig_grid.setSpacing(1, 1)
        orig_grid.setColor(pg.mkColor(255, 220, 0, 170))
        orig_grid.translate(0, 0, -0.01)
        self.addItem(orig_grid)

        sph_md = gl.MeshData.sphere(rows=12, cols=24, radius=0.10)
        orig_sph = gl.GLMeshItem(
            meshdata=sph_md, color=(1.0, 0.85, 0.0, 0.95),
            smooth=True, drawEdges=False
        )
        orig_sph.setGLOptions('translucent')
        self.addItem(orig_sph)

        # ── Trục tọa độ thế giới ─────────────────────────────
        self._add_world_axes(2.5, 3.0)

        # ── God Rays (ánh sáng từ mặt nước) ──────────────────
        for ray in UnderwaterEnv.god_rays(n=8):
            n_r = len(ray)
            alp = np.linspace(0.18, 0.0, n_r)
            c   = np.zeros((n_r, 4), np.float32)
            # Màu ánh sáng teal
            c[:, 0] = 0.60; c[:, 1] = 0.95; c[:, 2] = 1.0
            c[:, 3] = alp
            ri = gl.GLLinePlotItem(pos=ray, color=c, width=3.0, antialias=True)
            ri.setGLOptions('additive')
            self.addItem(ri)

        # ── Mặt nước (animated sine wave) ────────────────────
        ws_v, ws_f, self._water_XX, self._water_YY = UnderwaterEnv.water_surface()
        self._water_base  = ws_v.copy()
        self._water_faces = ws_f
        n_wf = len(ws_f)
        self._water_colors = np.zeros((n_wf, 4), np.float32)
        self._water_colors[:, 0] = 0.10
        self._water_colors[:, 1] = 0.72
        self._water_colors[:, 2] = 0.80
        self._water_colors[:, 3] = 0.22
        self._water_mesh = gl.GLMeshItem(
            vertexes=ws_v, faces=ws_f, faceColors=self._water_colors,
            smooth=True, drawEdges=True,
            edgeColor=(0.2, 0.8, 0.9, 0.05)
        )
        self._water_mesh.setGLOptions('translucent')
        self.addItem(self._water_mesh)

        # ── Bong bóng ─────────────────────────────────────────
        self._bub_pts[:, 0] = np.random.uniform(-10, 10, self._n_bub)
        self._bub_pts[:, 1] = np.random.uniform(-10, 10, self._n_bub)
        self._bub_pts[:, 2] = np.random.uniform(-9, 0, self._n_bub)
        self._bub_item = gl.GLScatterPlotItem(
            pos=self._bub_pts,
            color=(0.9, 0.98, 1.0, 0.50),
            size=self._bub_sz, pxMode=True
        )
        self._bub_item.setGLOptions('additive')
        self.addItem(self._bub_item)

        # ── Depth warning plane (mặc định tại -10m) ──────────
        self._add_depth_plane(depth_limit=-10.0)

    def _add_world_axes(self, length=2.5, width=3.0):
        dirs   = [[length,0,0],[0,length,0],[0,0,length]]
        colors = [(1.,0.2,0.2,0.9),(0.2,1.,0.2,0.9),(0.2,0.4,1.,0.9)]
        for d, c in zip(dirs, colors):
            ln = gl.GLLinePlotItem(
                pos=np.array([[0,0,0],d], np.float32),
                color=c, width=width, antialias=True
            )
            self.addItem(ln)
            self._axis_items.append(ln)
            sph = gl.GLMeshItem(
                meshdata=gl.MeshData.sphere(rows=8,cols=16,radius=0.09),
                color=c, smooth=True
            )
            sph.translate(*d)
            self.addItem(sph)
            self._axis_items.append(sph)

    def _add_depth_plane(self, depth_limit: float = -10.0):
        """Mặt phẳng bán trong suốt đỏ tại depth giới hạn."""
        if self._depth_plane is not None:
            self.removeItem(self._depth_plane)
        s   = 30.0
        v   = np.array([[-s,-s,depth_limit],[s,-s,depth_limit],
                         [s,s,depth_limit],[-s,s,depth_limit]], np.float32)
        f   = np.array([[0,1,2],[0,2,3]], np.int32)
        col = np.tile([1.0,0.15,0.0,0.12], (2,1)).astype(np.float32)
        self._depth_plane = gl.GLMeshItem(
            vertexes=v, faces=f, faceColors=col,
            smooth=False, drawEdges=True,
            edgeColor=(1.0, 0.2, 0.0, 0.25)
        )
        self._depth_plane.setGLOptions('translucent')
        self.addItem(self._depth_plane)

    # ──────────────────────────────────────────────────────────
    # HOẠT HỌA (20 FPS env timer)
    # ──────────────────────────────────────────────────────────
    def _animate_env(self):
        self._water_t += 0.048
        t  = self._water_t
        nv = self._water_base.copy()
        XX = self._water_XX.ravel()
        YY = self._water_YY.ravel()
        nv[:, 2] = (0.055*np.sin(XX*1.10 + t*2.1)
                  + 0.040*np.cos(YY*0.85 + t*1.7)
                  + 0.025*np.sin((XX+YY)*0.50 + t*0.9))
        self._water_mesh.setMeshData(
            vertexes=nv, faces=self._water_faces,
            faceColors=self._water_colors
        )

        # Bong bóng
        rp = self._current_pos
        self._bub_pts[:, 2] += self._bub_spd
        mask = self._bub_pts[:, 2] > (rp[2] + 1.5)
        n    = mask.sum()
        if n:
            self._bub_pts[mask, 0] = rp[0] + np.random.uniform(-9, 9, n)
            self._bub_pts[mask, 1] = rp[1] + np.random.uniform(-9, 9, n)
            self._bub_pts[mask, 2] = rp[2] - np.random.uniform(6, 11, n)
        self._bub_item.setData(pos=self._bub_pts)

    # ──────────────────────────────────────────────────────────
    # CONTEXT MENU
    # ──────────────────────────────────────────────────────────
    def _show_context_menu(self, pos):
        menu = QtWidgets.QMenu(self)
        menu.setStyleSheet("""
            QMenu{background:#082030;color:#A0D0E0;border:1px solid #0A5070;}
            QMenu::item:selected{background:#0A4060;}
        """)
        a_follow  = menu.addAction("📹  FOLLOW — Bám theo ROV")
        a_orbit   = menu.addAction("🔄  ORBIT  — Xoay cinematic")
        a_map     = menu.addAction("🗺   MAP    — Nhìn từ trên")
        a_manual  = menu.addAction("🖐  MANUAL — Tự do điều khiển")
        menu.addSeparator()
        a_reset   = menu.addAction("🎯  Reset gốc tọa độ")
        a_clear   = menu.addAction("🗑   Xóa quỹ đạo")
        menu.addSeparator()
        a_wp_clr  = menu.addAction("📍  Xóa Waypoints")
        menu.addSeparator()
        a_depth   = menu.addAction("⚠   Đặt Depth Limit tại đây")

        for a, m in [(a_follow, CameraMode.FOLLOW),
                     (a_orbit,  CameraMode.ORBIT),
                     (a_map,    CameraMode.MAP),
                     (a_manual, CameraMode.MANUAL)]:
            a.setCheckable(True)
            a.setChecked(self._cam_mode == m)

        act = menu.exec(self.mapToGlobal(pos))
        if act == a_follow:
            self._cam_mode = CameraMode.FOLLOW
            self._user_ctrl = False
        elif act == a_orbit:
            self._cam_mode = CameraMode.ORBIT
            self._orbit_yaw = self._get_azimuth()
        elif act == a_map:
            self._cam_mode = CameraMode.MAP
        elif act == a_manual:
            self._cam_mode = CameraMode.MANUAL
            self._user_ctrl = False          # reset flag, MANUAL tự xử lý
            self._cam_resume_timer.stop()    # dừng timer resume
        elif act == a_reset:
            self.reset_origin()
        elif act == a_clear:
            self._reset_trajectory()
        elif act == a_wp_clr:
            self.clear_waypoints()
        elif act == a_depth:
            d = float(self._current_pos[2])
            self._add_depth_plane(depth_limit=d)
        self._hud.update_data(cam_mode=CameraMode.LABELS.get(self._cam_mode,"?"))

    def _get_azimuth(self):
        return self.cameraParams().get('azimuth', 45.0)

    # ──────────────────────────────────────────────────────────
    # MODEL ROV
    # ──────────────────────────────────────────────────────────
    def set_model(self, model, cad_file: str = None):
        self._model_config = model.get_visual_config()
        self._cad_file     = cad_file
        for it in self._rov_items:
            self.removeItem(it)
        self._rov_items.clear()
        # Velocity arrow items are persistent (pre-allocated), just hide them
        self._vel_line.setVisible(False)
        self._vel_cone.setVisible(False)

        if cad_file:
            self._build_cad(cad_file)
        else:
            self._build_proc()
        self._rov_items.extend(self._build_local_axes())
        self._reset_trajectory()

    def _build_local_axes(self):
        items, L = [], 0.55
        for d, c in [([L,0,0],(1.,0.,0.,1.)),
                      ([0,L,0],(0.,1.,0.,1.)),
                      ([0,0,L],(0.,0.4,1.,1.))]:
            ln = gl.GLLinePlotItem(
                pos=np.array([[0,0,0],d], np.float32),
                color=c, width=2.0, antialias=True
            )
            self.addItem(ln)
            items.append(ln)
        return items

    def _build_cad(self, fp):
        v, f = CADLoader.load(fp)
        if v is None:
            self._build_proc(); return
        scale = 1.0 / max(np.ptp(v, axis=0))
        v     = (v - v.mean(axis=0)) * scale
        # ── Màu TRUNG TÍNH (xám metallic) — không override màu gốc file ──
        # Dùng xám bạc trung tính thay vì xanh lè
        n_f   = len(f)
        col   = np.zeros((n_f, 4), np.float32)
        col[:, 0] = 0.62   # R  xám bạc ấm
        col[:, 1] = 0.65   # G
        col[:, 2] = 0.68   # B
        col[:, 3] = 0.92
        mesh = gl.GLMeshItem(
            vertexes=v, faces=f, faceColors=col,
            smooth=True, drawEdges=True,
            edgeColor=(0.9, 0.9, 0.95, 0.20)
        )
        self.addItem(mesh)
        self._rov_items.append(mesh)

    def _build_proc(self):
        cfg = self._model_config
        if cfg is None: return
        cs = cfg["chassis"]
        dims = (cs["size"] if "size" in cs
                else [cs.get("length",0.4),cs.get("width",0.3),cs.get("height",0.2)])
        v, f = ProcMeshBuilder.box(*dims)
        col  = np.tile(list(cs["color"]), (len(f),1))
        body = gl.GLMeshItem(
            vertexes=v, faces=f, faceColors=col,
            smooth=False, drawEdges=True, edgeColor=cs["edge_color"]
        )
        self.addItem(body); self._rov_items.append(body)

        if "foam_block" in cfg:
            fb  = cfg["foam_block"]
            v2,f2 = ProcMeshBuilder.box(*fb["size"])
            v2   += np.array(fb["offset"])
            c2    = np.tile(list(fb["color"]), (len(f2),1))
            foam  = gl.GLMeshItem(
                vertexes=v2, faces=f2, faceColors=c2,
                smooth=False, drawEdges=True, edgeColor=fb["edge_color"]
            )
            self.addItem(foam); self._rov_items.append(foam)

        for ht in cfg.get("horizontal_thrusters",[]):
            v,f = ProcMeshBuilder.cylinder(0.028, 0.11, 10)
            a   = math.radians(ht["angle_deg"])
            rot = np.array([[math.cos(a),-math.sin(a),0],
                            [math.sin(a), math.cos(a),0],[0,0,1]])
            v   = v @ rot.T + np.array(ht["pos"])
            c   = np.tile([0.25,0.72,1.,0.92],(len(f),1))
            m   = gl.GLMeshItem(vertexes=v,faces=f,faceColors=c,smooth=True)
            self.addItem(m); self._rov_items.append(m)

        for vt in cfg.get("vertical_thrusters",[]):
            v,f = ProcMeshBuilder.cylinder(0.028, 0.09, 10)
            v  += np.array(vt["pos"])
            c   = np.tile([0.55,0.92,1.,0.92],(len(f),1))
            m   = gl.GLMeshItem(vertexes=v,faces=f,faceColors=c,smooth=True)
            self.addItem(m); self._rov_items.append(m)

        for lt in cfg.get("headlights",[]):
            v,f = ProcMeshBuilder.cone(0.045, 0.22, 16)
            rot = np.array([[0,0,1],[0,1,0],[-1,0,0]], np.float32)
            v   = v @ rot.T + np.array(lt["pos"])
            c   = np.tile([0.,0.95,1.,0.10],(len(f),1))
            m   = gl.GLMeshItem(vertexes=v,faces=f,faceColors=c,smooth=True)
            m.setGLOptions('translucent')
            self.addItem(m); self._rov_items.append(m)

    # ──────────────────────────────────────────────────────────
    # CẬP NHẬT TRẠNG THÁI
    # ──────────────────────────────────────────────────────────
    def set_origin(self, pos: np.ndarray):
        self._origin = pos.copy()

    def update_pose(self, position: np.ndarray, quat_xyzw: np.ndarray,
                    heading_deg=0., depth_m=0., speed_mps=0.,
                    roll_deg=0., pitch_deg=0.):
        if self._origin is not None:
            pos = position - self._origin
        else:
            pos = position.copy()

        # NED → OpenGL
        gl_pos = np.array([pos[0], -pos[1], -pos[2]], np.float32)
        self._current_pos  = gl_pos
        self._current_quat = quat_xyzw.copy()
        self._heading = heading_deg
        self._depth   = depth_m
        self._speed   = speed_mps
        self._roll    = roll_deg
        self._pitch   = pitch_deg

        self._apply_transform(gl_pos, quat_xyzw)

        # Velocity vector trên main view
        self._update_vel_vector(speed_mps, heading_deg, pitch_deg, gl_pos)

        # HUD
        dist_home = float(np.linalg.norm(gl_pos))
        self._hud.update_data(
            depth=depth_m, heading=heading_deg,
            pos=[pos[0],pos[1],pos[2]],
            speed=speed_mps, roll=roll_deg, pitch=pitch_deg,
            dist_home=dist_home,
        )
        self._update_camera(gl_pos)

    def _apply_transform(self, pos, q):
        qx,qy,qz,qw = q
        roll  = math.degrees(math.atan2(2*(qw*qx+qy*qz), 1-2*(qx*qx+qy*qy)))
        sinp  = max(-1., min(1., 2*(qw*qy-qz*qx)))
        pitch = math.degrees(math.asin(sinp))
        yaw   = math.degrees(math.atan2(2*(qw*qz+qx*qy), 1-2*(qy*qy+qz*qz)))
        for it in self._rov_items:
            it.resetTransform()
            it.rotate(yaw,  0,0,1)
            it.rotate(pitch,0,1,0)
            it.rotate(roll, 1,0,0)
            it.translate(*pos)

    def _update_vel_vector(self, speed, hdg_deg, pitch_deg, pos):
        """Mũi tên vận tốc gắn trên thân ROV — reuses pre-allocated items."""
        if speed < 0.05:
            self._vel_line.setVisible(False)
            self._vel_cone.setVisible(False)
            return
        hdg  = math.radians(hdg_deg)
        pit  = math.radians(-pitch_deg)
        scale = min(speed * 0.8, 1.2)
        dx = math.cos(pit) * math.sin(hdg) * scale
        dy = math.cos(pit) * math.cos(hdg) * scale
        dz = math.sin(pit) * scale
        end = pos + np.array([dx, -dy, -dz])  # NED→GL
        pts = np.array([pos.tolist(), end.tolist()], np.float32)
        self._vel_line.setData(pos=pts)
        self._vel_line.setVisible(True)

        # Cone — reuse with transform
        v_dir = (end - pos)
        v_len = np.linalg.norm(v_dir)
        if v_len > 1e-6:
            v_dir /= v_len
        cone_pos = end - v_dir * 0.12
        # Compute rotation from Z-axis to velocity direction
        z_axis = np.array([0., 0., 1.])
        if abs(v_dir[2]) < 0.999:
            rot_ax = np.cross(z_axis, v_dir)
            rot_ax /= np.linalg.norm(rot_ax)
            rot_ang = math.degrees(math.acos(np.clip(np.dot(z_axis, v_dir), -1, 1)))
        else:
            rot_ax = np.array([1., 0., 0.])
            rot_ang = 0.0 if v_dir[2] > 0 else 180.0
        self._vel_cone.resetTransform()
        self._vel_cone.rotate(rot_ang, *rot_ax)
        self._vel_cone.translate(*cone_pos)
        self._vel_cone.setVisible(True)

    def _update_camera(self, gl_pos):
        if self._user_ctrl:
            return   # User đang xoay tay → không override camera
        if self._cam_mode == CameraMode.MANUAL:
            return   # MANUAL mode: camera hoàn toàn do user điều khiển

        alpha = 0.07
        self._cam_lerp_pos = (self._cam_lerp_pos*(1-alpha) + gl_pos*alpha).astype(np.float32)
        tgt = pg.Vector(*self._cam_lerp_pos)

        if self._cam_mode == CameraMode.FOLLOW:
            self.setCameraPosition(pos=tgt, distance=3.5, elevation=20, azimuth=45)
        elif self._cam_mode == CameraMode.ORBIT:
            self._orbit_yaw = (self._orbit_yaw + 0.30) % 360
            self.setCameraPosition(pos=tgt, distance=4.5, elevation=16,
                                   azimuth=self._orbit_yaw)
        elif self._cam_mode == CameraMode.MAP:
            self.setCameraPosition(pos=tgt, distance=6.0, elevation=88, azimuth=0)

    # ──────────────────────────────────────────────────────────
    # QUỸ ĐẠO BỀN VỮNG — solid recent + dotted historical
    # ──────────────────────────────────────────────────────────
    def update_trajectory(self, x: float, y: float, z: float):
        self._traj_pts.append([x, -y, -z])
        if len(self._traj_pts) > self.MAX_TRAJ_POINTS:
            self._traj_pts.pop(0)

        # Throttle: only redraw every 3 frames to reduce numpy overhead
        self._traj_update_cnt += 1
        if self._traj_update_cnt % 3 != 0:
            return

        pts = np.array(self._traj_pts, np.float32)
        n   = len(pts)
        if n < 2:
            return

        # ── A. Recent trail (300 điểm gần nhất): solid bright ──
        recent_n = min(300, n)
        rp  = pts[-recent_n:]
        rn  = len(rp)
        t_r = np.linspace(0, 1, rn)
        rc  = np.zeros((rn, 4), np.float32)
        rc[:, 0] = 0.8 * (1 - t_r)        # fade từ sáng → mờ
        rc[:, 1] = 1.0
        rc[:, 2] = 1.0
        rc[:, 3] = 0.9 * t_r + 0.1        # alpha tăng dần lên đầu

        if self._traj_line is not None:
            self._traj_line.setData(pos=rp, color=rc)
        else:
            self._traj_line = gl.GLLinePlotItem(
                pos=rp, color=rc, width=2.5,
                antialias=True, mode='line_strip'
            )
            self.addItem(self._traj_line)

        # ── B. Historical trail: dotted scatter ─────────────────
        # Lấy các điểm lịch sử (bỏ 300 điểm recent), mỗi STRIDE điểm lấy 1
        hist_pts = pts[:-recent_n:self.TRAJ_DOT_STRIDE] if n > recent_n else pts[::self.TRAJ_DOT_STRIDE]
        if len(hist_pts) < 2:
            return

        nh  = len(hist_pts)
        t_h = np.linspace(0, 1, nh)
        hc  = np.zeros((nh, 4), np.float32)
        hc[:, 0] = 0.4 + 0.5 * t_h
        hc[:, 1] = 0.9
        hc[:, 2] = 1.0
        hc[:, 3] = 0.15 + 0.35 * t_h    # rất mờ ở phần cũ, rõ hơn phần gần

        if self._traj_dots is not None:
            self._traj_dots.setData(pos=hist_pts, color=hc, size=2.0)
        else:
            self._traj_dots = gl.GLScatterPlotItem(
                pos=hist_pts, color=hc, size=2.0, pxMode=True
            )
            self.addItem(self._traj_dots)

    # ──────────────────────────────────────────────────────────
    # SLAM POINTS
    # ──────────────────────────────────────────────────────────
    def update_slam_points(self, pts_xyz: np.ndarray):
        if pts_xyz is None or len(pts_xyz) == 0:
            return
        gp = pts_xyz.copy()
        gp[:, 1] *= -1; gp[:, 2] *= -1
        d = np.linalg.norm(gp, axis=1)
        t = np.clip(d / max(d.max(), 1e-6), 0, 1)
        c = np.zeros((len(gp), 4), np.float32)
        c[:, 0] = 1.0-t; c[:, 1] = t*0.7; c[:, 2] = t; c[:, 3] = 0.80
        if self._slam_item is not None:
            self._slam_item.setData(pos=gp, color=c, size=2.5)
        else:
            self._slam_item = gl.GLScatterPlotItem(pos=gp,color=c,size=2.5,pxMode=True)
            self.addItem(self._slam_item)

        # Proximity check: có điểm SLAM nào trong 0.5m không?
        near = (d < 0.6).any()
        self._hud.update_data(proximity=near)

        # Proximity ring quanh ROV khi gần vật thể
        self._update_prox_ring(near)

    def _update_prox_ring(self, active: bool):
        """Proximity ring — reuses pre-allocated GLLinePlotItem."""
        if not active:
            self._prox_ring.setVisible(False)
            return
        segs = 40
        ang  = np.linspace(0, 2*math.pi, segs, endpoint=False)
        p    = self._current_pos
        r    = 0.65
        pts  = np.zeros((segs+1, 3), np.float32)
        pts[:segs, 0] = p[0] + r*np.cos(ang)
        pts[:segs, 1] = p[1] + r*np.sin(ang)
        pts[:segs, 2] = p[2]
        pts[segs]     = pts[0]
        self._prox_ring.setData(pos=pts)
        self._prox_ring.setVisible(True)

    # ──────────────────────────────────────────────────────────
    # FOV EFFECT
    # ──────────────────────────────────────────────────────────
    def update_fov_effect(self, heading_deg: float, fov_deg: float = 60.0):
        """FOV cone overlay — reuses pre-allocated GLLinePlotItem."""
        pos  = self._current_pos
        half = math.radians(fov_deg/2)
        yaw  = math.radians(heading_deg)
        L    = 2.2; segs = 20
        pts  = [pos.tolist()]
        for i in range(segs+1):
            a = yaw - half + (fov_deg/segs*i)*math.pi/180
            pts.append([pos[0]+L*math.cos(a), pos[1]+L*math.sin(a), pos[2]])
        pts.append(pos.tolist())
        arr = np.array(pts, np.float32)
        n   = len(arr)
        c   = np.zeros((n,4), np.float32)
        c[:,0]=0.; c[:,1]=0.90; c[:,2]=1.0
        c[:,3]=np.linspace(0.30, 0., n)
        self._fov_item.setData(pos=arr, color=c)
        self._fov_item.setVisible(True)

    # ──────────────────────────────────────────────────────────
    # WAYPOINTS (GCS Feature)
    # ──────────────────────────────────────────────────────────
    def add_waypoint(self, x: float, y: float, z: float,
                     index: int = None, reached: bool = False):
        """
        Thêm waypoint tại vị trí (x,y,z) NED coordinates.
        reached=True: màu xanh lá (đã qua); False: màu vàng/cam (chưa tới).
        """
        gl_p  = np.array([x, -y, -z], np.float32)
        color = (0.2, 1.0, 0.4, 0.9) if reached else (1.0, 0.75, 0.0, 0.9)
        sph   = gl.GLMeshItem(
            meshdata=gl.MeshData.sphere(rows=10,cols=20,radius=0.12),
            color=color, smooth=True, drawEdges=False
        )
        sph.translate(*gl_p)
        self.addItem(sph)
        self._waypoint_items.append(sph)

        # Đường nối các waypoint
        self._redraw_wp_path()

    def _redraw_wp_path(self):
        # Xóa path cũ
        if self._wp_path_item is not None:
            self.removeItem(self._wp_path_item)
            self._wp_path_item = None
        n = len(self._waypoint_items)
        if n < 2:
            return
        # Lấy vị trí của mỗi waypoint sphere
        # (không có cách lấy trực tiếp từ GLMeshItem nên ta track riêng)
        pass   # TODO: track positions separately nếu cần

    def clear_waypoints(self):
        for it in self._waypoint_items:
            self.removeItem(it)
        self._waypoint_items.clear()
        if self._wp_path_item is not None:
            self.removeItem(self._wp_path_item)
            self._wp_path_item = None

    # ──────────────────────────────────────────────────────────
    # TIỆN ÍCH
    # ──────────────────────────────────────────────────────────
    def _reset_trajectory(self):
        self._traj_pts = []
        if self._traj_line is not None:
            self.removeItem(self._traj_line); self._traj_line = None
        if self._traj_dots is not None:
            self.removeItem(self._traj_dots); self._traj_dots = None

    def reset_origin(self):
        self._origin = None
        self._reset_trajectory()

    def set_follow_mode(self, enabled: bool):
        self._cam_mode = CameraMode.FOLLOW if enabled else CameraMode.ORBIT
        self._hud.update_data(cam_mode=CameraMode.LABELS[self._cam_mode])

    def set_camera_mode(self, mode: int):
        """Public API để đặt camera mode: FOLLOW/ORBIT/MAP/MANUAL."""
        self._cam_mode = mode
        if mode == CameraMode.MANUAL:
            self._cam_resume_timer.stop()
        self._hud.update_data(cam_mode=CameraMode.LABELS.get(mode, "?"))

    def set_depth_limit(self, depth_m: float):
        """Public API để đặt mặt phẳng cảnh báo độ sâu tối đa."""
        # depth_m là số dương, ta chuyển sang GL coords (−z)
        self._add_depth_plane(depth_limit=-abs(depth_m))
