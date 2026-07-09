"""
gl_3d_widget.py - 3D OpenGL ROV Visualization Widget
=====================================================
Widget PyQtGraph OpenGL nhúng thẳng vào layout guirov.py.
Thay thế QOpenGLWidget 'opw_motion' trong frm_simulate_motion.

Chức năng:
  - Dựng mô hình 3D ROV từ get_visual_config() của model
  - Import file STL/OBJ CAD nếu được cung cấp
  - Hiển thị trục tọa độ, lưới đáy, bong bóng, quỹ đạo
  - Nhận pose (pos, quat) và cập nhật mượt mà 60 FPS
  - Hỗ trợ headlight effect
  - Camera orbit + follow mode
"""
import math
import struct
import numpy as np
from pathlib import Path

from PyQt6 import QtCore, QtGui, QtWidgets
import pyqtgraph.opengl as gl
import pyqtgraph as pg


# ============================================================
# CAD LOADER (STL & OBJ)
# ============================================================
class CADLoader:
    """Tải file CAD 3D (STL binary/ASCII, OBJ) → (vertices, faces)."""

    @staticmethod
    def load(filepath: str):
        """
        Trả về (vertices ndarray [N,3], faces ndarray [M,3]).
        Trả về None nếu lỗi.
        """
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
        # Kiểm tra Binary STL
        is_binary = False
        try:
            # Binary: header 80 bytes + 4 bytes số tam giác + N*50 bytes
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
            # Bỏ qua 12 bytes normal
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
        i = 0
        lines = text.strip().splitlines()
        for line in lines:
            tok = line.strip().split()
            if len(tok) >= 4 and tok[0] == 'vertex':
                verts.append([float(tok[1]), float(tok[2]), float(tok[3])])
        # Nhóm 3 verts liên tiếp thành 1 mặt
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
                    # Chỉ lấy index đỉnh (bỏ uv/normal)
                    idx = [int(t.split('/')[0]) - 1 for t in tok[1:]]
                    if len(idx) == 3:
                        faces.append(idx)
                    elif len(idx) == 4:
                        # Quad → 2 tam giác
                        faces.append([idx[0], idx[1], idx[2]])
                        faces.append([idx[0], idx[2], idx[3]])
        if not verts or not faces:
            return None, None
        return np.array(verts, dtype=np.float32), np.array(faces, dtype=np.int32)


# ============================================================
# MESH BUILDER (Tạo mesh thủ công nếu không có CAD)
# ============================================================
class ProcMeshBuilder:
    """Tạo mesh hình học thủ công (đủ đẹp khi không có file CAD)."""

    @staticmethod
    def box(lx, ly, lz):
        """Khối hộp tâm tại gốc."""
        hx, hy, hz = lx/2, ly/2, lz/2
        v = np.array([
            [-hx, -hy, -hz], [+hx, -hy, -hz], [+hx, +hy, -hz], [-hx, +hy, -hz],
            [-hx, -hy, +hz], [+hx, -hy, +hz], [+hx, +hy, +hz], [-hx, +hy, +hz],
        ], dtype=np.float32)
        f = np.array([
            [0,1,2],[0,2,3],    # bottom
            [4,5,6],[4,6,7],    # top
            [0,1,5],[0,5,4],    # front
            [2,3,7],[2,7,6],    # back
            [1,2,6],[1,6,5],    # right
            [0,3,7],[0,7,4],    # left
        ], dtype=np.int32)
        return v, f

    @staticmethod
    def cylinder(r, h, segs=12):
        """Hình trụ theo trục Z."""
        v_list, f_list = [], []
        top_c, bot_c = len(v_list), 0
        angles = np.linspace(0, 2*np.pi, segs, endpoint=False)
        bot_verts = [[r*np.cos(a), r*np.sin(a), 0.0] for a in angles]
        top_verts = [[r*np.cos(a), r*np.sin(a), h]   for a in angles]
        bot_center = [0.0, 0.0, 0.0]
        top_center = [0.0, 0.0, h]
        verts = [bot_center] + bot_verts + [top_center] + top_verts
        n = segs
        faces = []
        # Đáy dưới
        for i in range(n):
            faces.append([0, 1 + i, 1 + (i+1)%n])
        # Đáy trên
        tc = n + 1
        for i in range(n):
            faces.append([tc, tc + 1 + i, tc + 1 + (i+1)%n])
        # Mặt bên
        for i in range(n):
            b0 = 1 + i; b1 = 1 + (i+1)%n
            t0 = tc + 1 + i; t1 = tc + 1 + (i+1)%n
            faces.append([b0, b1, t1])
            faces.append([b0, t1, t0])
        return np.array(verts, dtype=np.float32), np.array(faces, dtype=np.int32)

    @staticmethod
    def cone(r, h, segs=16):
        """Hình nón (cone) cho đèn pha."""
        angles = np.linspace(0, 2*np.pi, segs, endpoint=False)
        base = [[r*np.cos(a), r*np.sin(a), 0.0] for a in angles]
        apex = [0.0, 0.0, h]
        verts = base + [apex]
        apex_idx = len(base)
        faces = []
        for i in range(segs):
            faces.append([i, (i+1)%segs, apex_idx])
        # Đáy
        for i in range(1, segs-1):
            faces.append([0, i, i+1])
        return np.array(verts, dtype=np.float32), np.array(faces, dtype=np.int32)


# ============================================================
# GL ROV WIDGET
# ============================================================
class GLROVWidget(gl.GLViewWidget):
    """
    Widget OpenGL 3D nhúng vào guirov.py (thay thế opw_motion).
    
    Cách dùng:
        self.gl_3d = GLROVWidget(parent=self.frm_simulate_motion)
        self.gl_3d.set_model(rov_model_instance)
        # Mỗi frame:
        self.gl_3d.update_pose(position, quat_xyzw)
        self.gl_3d.update_trajectory(x, y, z)
    """

    # --- Màu sắc giao diện ---
    BG_COLOR       = (0.024, 0.043, 0.078, 1.0)  # #060B14
    GRID_COLOR     = (0.09, 0.23, 0.40, 0.6)
    AXIS_COLORS    = [(1,0,0,1), (0,1,0,1), (0,0,1,1)]  # X, Y, Z

    # --- Quỹ đạo ---
    MAX_TRAJ_POINTS = 500

    def __init__(self, parent=None):
        super().__init__(parent=parent)

        # Trạng thái nội bộ
        self._model_config  = None
        self._cad_file      = None
        self._current_pos   = np.zeros(3)
        self._current_quat  = np.array([0., 0., 0., 1.])
        self._origin        = None      # điểm mốc tọa độ lần đầu nhận
        self._traj_pts      = []
        self._follow_mode   = True

        # Các items GL được quản lý
        self._rov_items     = []        # Tất cả mesh của thân ROV
        self._axis_items    = []
        self._traj_item     = None
        self._grid_item     = None
        self._slam_item     = None
        self._fov_item      = None
        self._bubble_item   = None
        self._origin_grid   = None
        self._origin_sphere = None

        # Khởi tạo hạt bong bóng nước (Water Bubbles Animation)
        self._n_bubbles = 100
        self._bubble_pts = np.zeros((self._n_bubbles, 3), dtype=np.float32)
        self._bubble_pts[:, 0] = np.random.uniform(-10.0, 10.0, self._n_bubbles)
        self._bubble_pts[:, 1] = np.random.uniform(-10.0, 10.0, self._n_bubbles)
        self._bubble_pts[:, 2] = np.random.uniform(-5.0, 5.0, self._n_bubbles)
        self._bubble_speeds = np.random.uniform(0.015, 0.04, self._n_bubbles)

        self._setup_scene()

        # Timer hoạt họa bong bóng nổi lên (30 FPS)
        self._anim_timer = QtCore.QTimer(self)
        self._anim_timer.timeout.connect(self._animate_bubbles)
        self._anim_timer.start(33)

    # --------------------------------------------------------
    # THIẾT LẬP CẢNH
    # --------------------------------------------------------
    def _setup_scene(self):
        """Khởi tạo scene cơ bản: background, camera, grid, axes, bubbles."""
        self.setBackgroundColor(pg.mkColor(*[int(c*255) for c in self.BG_COLOR]))
        self.setCameraPosition(distance=3.5, elevation=25, azimuth=45)

        # Lưới đáy biển khổng lồ (200m x 200m) giúp không bao giờ bị lạc
        self._grid_item = gl.GLGridItem()
        self._grid_item.setSize(200, 200)
        self._grid_item.setSpacing(5, 5)
        self._grid_item.setColor(pg.mkColor(9, 23, 40, 100))
        self._grid_item.translate(0, 0, -5)
        self.addItem(self._grid_item)

        # Lưới mốc xuất phát tại gốc tọa độ (Origin Launch Pad) màu cam rực rỡ
        self._origin_grid = gl.GLGridItem()
        self._origin_grid.setSize(6, 6)
        self._origin_grid.setSpacing(1, 1)
        self._origin_grid.setColor(pg.mkColor(255, 120, 0, 140))
        self._origin_grid.translate(0, 0, -4.99) # Hơi cao hơn lưới đáy biển 1 chút
        self.addItem(self._origin_grid)

        # Cầu phát sáng tại gốc tọa độ (Orange Glow Dock Sphere)
        sph_md = gl.MeshData.sphere(rows=12, cols=24, radius=0.08)
        self._origin_sphere = gl.GLMeshItem(
            meshdata=sph_md, color=(1.0, 0.45, 0.0, 0.8),
            smooth=True, drawEdges=False
        )
        self._origin_sphere.translate(0, 0, 0)
        self._origin_sphere.setGLOptions('translucent')
        self.addItem(self._origin_sphere)

        # Thêm trục tọa độ thế giới (dài hơn và có đầu hướng)
        self._add_world_axes(length=2.5, width=3.0)

        # Thêm particle bong bóng vào cảnh
        self._bubble_item = gl.GLScatterPlotItem(
            pos=self._bubble_pts, color=(0.4, 0.7, 1.0, 0.4),
            size=3.0, pxMode=True
        )
        self._bubble_item.setGLOptions('additive')
        self.addItem(self._bubble_item)

    def _add_world_axes(self, length=2.5, width=3.0):
        """Vẽ trục thế giới X(đỏ), Y(xanh lá), Z(xanh dương) dài hơn và có cầu định vị hướng."""
        dirs = [[length, 0, 0], [0, length, 0], [0, 0, length]]
        colors = [(1.0, 0.2, 0.2, 0.9), (0.2, 1.0, 0.2, 0.9), (0.2, 0.2, 1.0, 0.9)]
        for d, c in zip(dirs, colors):
            # Vẽ đường trục chính
            pts = np.array([[0, 0, 0], d], dtype=np.float32)
            line = gl.GLLinePlotItem(pos=pts, color=c, width=width, antialias=True)
            self.addItem(line)
            self._axis_items.append(line)

            # Cầu định vị hướng ở đầu trục thế giới để không bao giờ bị biến mất khỏi tầm mắt
            marker_md = gl.MeshData.sphere(rows=8, cols=16, radius=0.08)
            marker = gl.GLMeshItem(meshdata=marker_md, color=c, smooth=True, drawEdges=False)
            marker.translate(*d)
            self.addItem(marker)
            self._axis_items.append(marker)

    def _animate_bubbles(self):
        """Hoạt họa bong bóng nước nổi lên."""
        self._bubble_pts[:, 2] += self._bubble_speeds
        
        # Reset các bong bóng vượt quá tầm nhìn của ROV
        rov_pos = self._current_pos
        for i in range(self._n_bubbles):
            if self._bubble_pts[i, 2] > rov_pos[2] + 6.0:
                self._bubble_pts[i, 0] = rov_pos[0] + np.random.uniform(-10.0, 10.0)
                self._bubble_pts[i, 1] = rov_pos[1] + np.random.uniform(-10.0, 10.0)
                self._bubble_pts[i, 2] = rov_pos[2] - np.random.uniform(4.0, 7.0)
        
        self._bubble_item.setData(pos=self._bubble_pts)

    # --------------------------------------------------------
    # THIẾT LẬP MODEL
    # --------------------------------------------------------
    def set_model(self, model, cad_file: str = None):
        """
        Gắn model ROV vào widget.
        
        Args:
            model   : instance của BaseROVModel
            cad_file: đường dẫn file STL/OBJ (tùy chọn)
        """
        self._model_config = model.get_visual_config()
        self._cad_file = cad_file

        # Xóa mô hình cũ
        for item in self._rov_items:
            self.removeItem(item)
        self._rov_items.clear()

        # Xây dựng mô hình mới
        if cad_file:
            self._build_cad_model(cad_file)
        else:
            self._build_proc_model()

        # Vẽ trục tọa độ cục bộ trực tiếp trên ROV
        local_axes = self._build_local_axes()
        self._rov_items.extend(local_axes)

        self._reset_trajectory()

    def _build_local_axes(self) -> list:
        """Vẽ trục tọa độ cục bộ nhỏ gắn chặt vào thân tàu (X=đỏ, Y=xanh lá, Z=xanh dương)."""
        items = []
        length = 0.5
        dirs = [[length, 0, 0], [0, length, 0], [0, 0, length]]
        colors = [(1.0, 0.0, 0.0, 1.0), (0.0, 1.0, 0.0, 1.0), (0.0, 0.0, 1.0, 1.0)]
        for d, c in zip(dirs, colors):
            pts = np.array([[0, 0, 0], d], dtype=np.float32)
            line = gl.GLLinePlotItem(pos=pts, color=c, width=2.0, antialias=True)
            self.addItem(line)
            items.append(line)
        return items

    def _build_cad_model(self, filepath: str):
        """Tải file CAD và dựng GLMeshItem."""
        verts, faces = CADLoader.load(filepath)
        if verts is None:
            print("[GLROVWidget] CAD load failed, using procedural mesh.")
            self._build_proc_model()
            return
        # Chuẩn hóa kích thước về 1m
        scale = 1.0 / max(np.ptp(verts, axis=0))
        verts = (verts - verts.mean(axis=0)) * scale
        colors = np.tile([0.1, 0.4, 0.9, 0.85], (len(faces), 1))
        mesh = gl.GLMeshItem(
            vertexes=verts, faces=faces, faceColors=colors,
            smooth=True, drawEdges=True,
            edgeColor=(0.0, 0.8, 1.0, 0.3)
        )
        self.addItem(mesh)
        self._rov_items.append(mesh)

    def _build_proc_model(self):
        """Xây dựng mô hình thủ công từ get_visual_config()."""
        cfg = self._model_config
        if cfg is None:
            return

        # --- Thân ROV ---
        cs = cfg["chassis"]
        # Hỗ trợ 2 kiểu config: {"size": [l,w,h]} hoặc {"length":..., "width":..., "height":...}
        if "size" in cs:
            box_dims = cs["size"]
        else:
            box_dims = [
                cs.get("length", 0.40),
                cs.get("width",  0.30),
                cs.get("height", 0.20),
            ]
        v, f = ProcMeshBuilder.box(*box_dims)
        colors = np.tile(list(cs["color"]), (len(f), 1))
        body_mesh = gl.GLMeshItem(
            vertexes=v, faces=f, faceColors=colors,
            smooth=False, drawEdges=True, edgeColor=cs["edge_color"]
        )
        self.addItem(body_mesh)
        self._rov_items.append(body_mesh)

        # --- Khối xốp (foam) nếu có ---
        if "foam_block" in cfg:
            fb = cfg["foam_block"]
            v2, f2 = ProcMeshBuilder.box(*fb["size"])
            off = np.array(fb["offset"])
            v2 += off
            c2 = np.tile(list(fb["color"]), (len(f2), 1))
            foam = gl.GLMeshItem(
                vertexes=v2, faces=f2, faceColors=c2,
                smooth=False, drawEdges=True, edgeColor=fb["edge_color"]
            )
            self.addItem(foam)
            self._rov_items.append(foam)

        # --- Thruster nằm ngang ---
        for ht in cfg.get("horizontal_thrusters", []):
            self._add_thruster_h(ht["pos"], ht["angle_deg"])

        # --- Thruster thẳng đứng ---
        for vt in cfg.get("vertical_thrusters", []):
            self._add_thruster_v(vt["pos"])

        # --- Đèn pha ---
        for lt in cfg.get("headlights", []):
            self._add_headlight(lt["pos"])

    def _add_thruster_h(self, pos, angle_deg):
        """Vẽ thruster nằm ngang (hình trụ nhỏ)."""
        v, f = ProcMeshBuilder.cylinder(0.025, 0.10, 10)
        # Xoay hình trụ theo góc (trong mặt phẳng XY)
        a = math.radians(angle_deg)
        rot = np.array([
            [math.cos(a), -math.sin(a), 0],
            [math.sin(a),  math.cos(a), 0],
            [0,            0,           1],
        ])
        v = v @ rot.T
        v += np.array(pos)
        c = np.tile([0.3, 0.7, 1.0, 0.9], (len(f), 1))
        m = gl.GLMeshItem(vertexes=v, faces=f, faceColors=c,
                          smooth=True, drawEdges=False)
        self.addItem(m)
        self._rov_items.append(m)

    def _add_thruster_v(self, pos):
        """Vẽ thruster thẳng đứng (hình trụ nhỏ)."""
        v, f = ProcMeshBuilder.cylinder(0.025, 0.08, 10)
        v += np.array(pos)
        c = np.tile([0.6, 0.9, 1.0, 0.9], (len(f), 1))
        m = gl.GLMeshItem(vertexes=v, faces=f, faceColors=c,
                          smooth=True, drawEdges=False)
        self.addItem(m)
        self._rov_items.append(m)

    def _add_headlight(self, pos):
        """Vẽ hình nón đèn pha (cyan bán trong suốt)."""
        v, f = ProcMeshBuilder.cone(0.04, 0.18, 16)
        # Xoay nón về hướng Forward (+X)
        rot = np.array([[0,0,1],[0,1,0],[-1,0,0]], dtype=np.float32)
        v = v @ rot.T
        v += np.array(pos)
        # Màu cyan bán trong suốt
        c = np.tile([0.0, 0.9, 1.0, 0.15], (len(f), 1))
        m = gl.GLMeshItem(vertexes=v, faces=f, faceColors=c,
                          smooth=True, drawEdges=False)
        m.setGLOptions('translucent')
        self.addItem(m)
        self._rov_items.append(m)

    # --------------------------------------------------------
    # CẬP NHẬT TRẠNG THÁI (GỌI MỖI FRAME)
    # --------------------------------------------------------
    def set_origin(self, position: np.ndarray):
        """Đặt điểm mốc tọa độ (lần đầu nhận heartbeat từ ROV)."""
        self._origin = position.copy()

    def update_pose(self, position: np.ndarray, quat_xyzw: np.ndarray):
        """
        Cập nhật vị trí và tư thế ROV.
        position  : [x, y, z] (m, hệ NED từ SLAM)
        quat_xyzw : [qx, qy, qz, qw]
        """
        # Dịch chuyển về hệ tọa độ widget (gốc tại điểm mốc)
        if self._origin is not None:
            pos = position - self._origin
        else:
            pos = position.copy()

        # Đổi trục NED → OpenGL: X→X, Y→−Y, Z→−Z (NED to RHS)
        gl_pos = np.array([pos[0], -pos[1], -pos[2]])

        self._current_pos  = gl_pos
        self._current_quat = quat_xyzw.copy()

        # Áp biến đổi cho tất cả mesh ROV
        self._apply_transform(gl_pos, quat_xyzw)

        # Camera follow
        if self._follow_mode:
            self.setCameraPosition(
                pos=pg.Vector(*gl_pos),
                distance=3.0, elevation=20, azimuth=45
            )

    def _apply_transform(self, pos, quat_xyzw):
        """Đặt transform (reset + translate + rotate) cho tất cả mesh ROV."""
        # Chuyển quaternion sang Euler
        qx, qy, qz, qw = quat_xyzw
        # Euler ZYX (Yaw, Pitch, Roll)
        sinr_cosp =  2*(qw*qx + qy*qz)
        cosr_cosp =  1 - 2*(qx*qx + qy*qy)
        roll  = math.degrees(math.atan2(sinr_cosp, cosr_cosp))
        sinp  = 2*(qw*qy - qz*qx)
        sinp  = max(-1.0, min(1.0, sinp))
        pitch = math.degrees(math.asin(sinp))
        siny_cosp = 2*(qw*qz + qx*qy)
        cosy_cosp = 1 - 2*(qy*qy + qz*qz)
        yaw   = math.degrees(math.atan2(siny_cosp, cosy_cosp))

        for item in self._rov_items:
            item.resetTransform()
            item.rotate(yaw,   0, 0, 1)
            item.rotate(pitch, 0, 1, 0)
            item.rotate(roll,  1, 0, 0)
            item.translate(*pos)

    def update_trajectory(self, x: float, y: float, z: float):
        """Thêm 1 điểm vào quỹ đạo và vẽ lại."""
        self._traj_pts.append([x, -y, -z])
        if len(self._traj_pts) > self.MAX_TRAJ_POINTS:
            self._traj_pts.pop(0)
        if len(self._traj_pts) < 2:
            return
        pts = np.array(self._traj_pts, dtype=np.float32)
        # Gradient màu: vàng → xanh cyan theo thời gian
        n = len(pts)
        colors = np.zeros((n, 4), dtype=np.float32)
        t = np.linspace(0, 1, n)
        colors[:, 0] = 1.0 - t          # R: vàng → cyan
        colors[:, 1] = 0.8
        colors[:, 2] = t                 # B: vàng → cyan
        colors[:, 3] = 0.9
        if self._traj_item is not None:
            self._traj_item.setData(pos=pts, color=colors)
        else:
            self._traj_item = gl.GLLinePlotItem(
                pos=pts, color=colors, width=2.0,
                antialias=True, mode='line_strip'
            )
            self.addItem(self._traj_item)

    def update_slam_points(self, pts_xyz: np.ndarray):
        """
        Cập nhật đám mây điểm SLAM.
        pts_xyz: ndarray (N, 3)  — tọa độ tương đối so với ROV
        """
        if pts_xyz is None or len(pts_xyz) == 0:
            return
        # Đổi trục: NED → OpenGL
        gl_pts = pts_xyz.copy()
        gl_pts[:, 1] *= -1
        gl_pts[:, 2] *= -1
        # Màu theo khoảng cách: gần→đỏ, xa→xanh
        dists = np.linalg.norm(gl_pts, axis=1)
        max_d = max(dists.max(), 1e-6)
        t = np.clip(dists / max_d, 0, 1)
        colors = np.zeros((len(gl_pts), 4), dtype=np.float32)
        colors[:, 0] = 1.0 - t     # R
        colors[:, 1] = t * 0.7     # G
        colors[:, 2] = t           # B
        colors[:, 3] = 0.8

        if self._slam_item is not None:
            self._slam_item.setData(pos=gl_pts, color=colors, size=2.5)
        else:
            self._slam_item = gl.GLScatterPlotItem(
                pos=gl_pts, color=colors, size=2.5, pxMode=True
            )
            self.addItem(self._slam_item)

    def update_fov_effect(self, heading_deg: float, fov_deg: float = 60.0):
        """
        Vẽ/cập nhật vệt sáng hình quạt (FOV camera) trước mũi tàu.
        """
        if self._fov_item is not None:
            self.removeItem(self._fov_item)
            self._fov_item = None

        pos = self._current_pos
        half = math.radians(fov_deg / 2)
        yaw  = math.radians(heading_deg)
        length = 2.0
        segs = 20
        pts = [pos.tolist()]
        for i in range(segs + 1):
            a = yaw - half + (fov_deg / segs * i) * math.pi / 180
            pts.append([
                pos[0] + length * math.cos(a),
                pos[1] + length * math.sin(a),
                pos[2]
            ])
        pts.append(pos.tolist())
        pts_arr = np.array(pts, dtype=np.float32)
        n = len(pts_arr)
        alpha = np.linspace(0.3, 0.0, n)
        c = np.zeros((n, 4), dtype=np.float32)
        c[:, 0] = 0.0; c[:, 1] = 0.8; c[:, 2] = 1.0
        c[:, 3] = alpha
        self._fov_item = gl.GLLinePlotItem(
            pos=pts_arr, color=c, width=1.5, antialias=True
        )
        self.addItem(self._fov_item)

    # --------------------------------------------------------
    # TIỆN ÍCH
    # --------------------------------------------------------
    def _reset_trajectory(self):
        """Xóa quỹ đạo."""
        self._traj_pts = []
        if self._traj_item is not None:
            self.removeItem(self._traj_item)
            self._traj_item = None

    def reset_origin(self):
        """Đặt lại điểm mốc về None → lần tới nhận pose sẽ set lại."""
        self._origin = None
        self._reset_trajectory()

    def set_follow_mode(self, enabled: bool):
        """Bật/tắt camera theo dõi ROV."""
        self._follow_mode = enabled
