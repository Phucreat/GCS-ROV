"""
gl_compass_3d_widget.py - 3D Compass & Radar Minimap Widget
============================================================
Widget hiển thị la bàn và radar 3D cho ROV.
Thay thế SLAMRadarWidget trong frm_simulate_view_bottom.

Chức năng:
  - Giữ mô hình ROV ở trung tâm (0,0,0)
  - Mô hình ROV xoay theo đúng Roll, Pitch, Yaw của tàu
  - Hiển thị la bàn 3D (Compass Ring) và các hướng Đông Tây Nam Bắc (N, E, S, W)
  - Vẽ vector vận tốc 3D (Velocity Vector) chỉ hướng di chuyển
  - Hiển thị đám mây điểm SLAM Point Cloud 3D xung quanh ROV
  - Thêm các vòng tròn cự ly (Range Rings) 3D để ước lượng khoảng cách
"""
import math
import numpy as np
from PyQt6 import QtCore, QtGui, QtWidgets
import pyqtgraph.opengl as gl
import pyqtgraph as pg

# Import helper từ gl_3d_widget để tái sử dụng
from GUI.widgets.gl_3d_widget import CADLoader, ProcMeshBuilder


class GLCompass3DWidget(gl.GLViewWidget):
    """
    Widget La bàn 3D và Radar Minimap.
    """
    BG_COLOR = (0.024, 0.043, 0.078, 1.0)  # #060B14
    COLOR_RING = (0.0, 0.66, 1.0, 0.5)     # Cyan
    COLOR_VELOCITY = (1.0, 0.78, 0.0, 0.9) # Orange/Gold
    COLOR_NORTH = (1.0, 0.2, 0.2, 1.0)     # Red for North

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        
        # Trạng thái
        self._model_config = None
        self._cad_file = None
        self._current_quat = np.array([0., 0., 0., 1.])
        self._velocity = np.zeros(3)
        self._depth = 0.0
        
        # Items
        self._rov_items = []
        self._ring_items = []
        self._label_items = []
        self._vel_vector_item = None
        self._slam_item = None

        self._setup_scene()

    # --------------------------------------------------------
    # THIẾT LẬP CẢNH
    # --------------------------------------------------------
    def _setup_scene(self):
        self.setBackgroundColor(pg.mkColor(*[int(c*255) for c in self.BG_COLOR]))
        # Đặt góc nhìn nghiêng từ trên xuống, cố định tiêu điểm tại tâm (0,0,0)
        self.setCameraPosition(distance=1.8, elevation=35, azimuth=45)
        
        # Vẽ các vòng tròn cự ly la bàn 3D (0.5m, 1.0m, 1.5m)
        self._draw_compass_rings()

    def _draw_compass_rings(self):
        # Xóa các vòng cũ nếu có
        for item in self._ring_items:
            self.removeItem(item)
        self._ring_items.clear()
        for item in self._label_items:
            self.removeItem(item)
        self._label_items.clear()

        radii = [0.5, 1.0, 1.5]
        segs = 64
        for r in radii:
            # Tạo đường tròn trong mặt phẳng XY
            angles = np.linspace(0, 2*np.pi, segs)
            pts = np.zeros((segs, 3), dtype=np.float32)
            pts[:, 0] = r * np.cos(angles)
            pts[:, 1] = r * np.sin(angles)
            pts[:, 2] = 0.0
            
            # Càng ra ngoài vòng tròn càng mờ
            alpha = max(0.1, 0.6 - r * 0.3)
            color = (0.0, 0.66, 1.0, alpha)
            
            line = gl.GLLinePlotItem(pos=pts, color=color, width=1.5, antialias=True, mode='line_strip')
            self.addItem(line)
            self._ring_items.append(line)

        # Vẽ 4 hướng chính N, E, S, W bằng các khối màu nhỏ dễ quan sát
        # North (+X) - Red
        self._add_direction_marker([1.5, 0.0, 0.0], self.COLOR_NORTH)
        # East (-Y) - Blue-gray
        self._add_direction_marker([0.0, -1.5, 0.0], (0.0, 0.8, 1.0, 0.8))
        # South (-X) - Gray
        self._add_direction_marker([-1.5, 0.0, 0.0], (0.5, 0.6, 0.7, 0.8))
        # West (+Y) - Blue-gray
        self._add_direction_marker([0.0, 1.5, 0.0], (0.0, 0.8, 1.0, 0.8))

        # Đường gạch nối các hướng chính
        axis_line_x = gl.GLLinePlotItem(
            pos=np.array([[-1.5, 0, 0], [1.5, 0, 0]], dtype=np.float32),
            color=(0.1, 0.3, 0.5, 0.4), width=1.0, antialias=True
        )
        axis_line_y = gl.GLLinePlotItem(
            pos=np.array([[0, -1.5, 0], [0, 1.5, 0]], dtype=np.float32),
            color=(0.1, 0.3, 0.5, 0.4), width=1.0, antialias=True
        )
        self.addItem(axis_line_x)
        self.addItem(axis_line_y)
        self._ring_items.extend([axis_line_x, axis_line_y])

    def _add_direction_marker(self, pos, color):
        """Vẽ một khối hộp nhỏ đại diện cho chữ hướng chính."""
        v, f = ProcMeshBuilder.box(0.06, 0.06, 0.06)
        v += np.array(pos)
        colors = np.tile(list(color), (len(f), 1))
        m = gl.GLMeshItem(vertexes=v, faces=f, faceColors=colors, smooth=False, drawEdges=True, edgeColor=(1,1,1,0.5))
        self.addItem(m)
        self._label_items.append(m)

    # --------------------------------------------------------
    # THIẾT LẬP MODEL
    # --------------------------------------------------------
    def set_model(self, model, cad_file: str = None):
        """Gắn mô hình ROV cho la bàn 3D."""
        self._model_config = model.get_visual_config()
        self._cad_file = cad_file

        # Xóa mô hình cũ
        for item in self._rov_items:
            self.removeItem(item)
        self._rov_items.clear()

        # Tạo mô hình mới tại tâm
        if cad_file:
            self._build_cad_model(cad_file)
        else:
            self._build_proc_model()

        # Áp góc xoay hiện tại lên model mới
        self._apply_transform(self._current_quat)

    def _build_cad_model(self, filepath: str):
        verts, faces = CADLoader.load(filepath)
        if verts is None:
            self._build_proc_model()
            return
        # Chuẩn hóa về kích thước nhỏ để vừa với radar (tỷ lệ 0.3m)
        scale = 0.35 / max(np.ptp(verts, axis=0))
        verts = (verts - verts.mean(axis=0)) * scale
        colors = np.tile([0.0, 0.66, 1.0, 0.8], (len(faces), 1))
        mesh = gl.GLMeshItem(
            vertexes=verts, faces=faces, faceColors=colors,
            smooth=True, drawEdges=True,
            edgeColor=(0.0, 0.8, 1.0, 0.4)
        )
        self.addItem(mesh)
        self._rov_items.append(mesh)

    def _build_proc_model(self):
        cfg = self._model_config
        if cfg is None:
            return

        # Nhân bản tỉ lệ nhỏ hơn (bằng 70% so với 3D main view) để gọn gàng
        scale_fac = 0.7
        cs = cfg["chassis"]
        size = [s * scale_fac for s in cs["size"]]
        v, f = ProcMeshBuilder.box(*size)
        colors = np.tile(list(cs["color"]), (len(f), 1))
        body_mesh = gl.GLMeshItem(
            vertexes=v, faces=f, faceColors=colors,
            smooth=False, drawEdges=True, edgeColor=cs["edge_color"]
        )
        self.addItem(body_mesh)
        self._rov_items.append(body_mesh)

        if "foam_block" in cfg:
            fb = cfg["foam_block"]
            fb_size = [s * scale_fac for s in fb["size"]]
            v2, f2 = ProcMeshBuilder.box(*fb_size)
            off = np.array(fb["offset"]) * scale_fac
            v2 += off
            c2 = np.tile(list(fb["color"]), (len(f2), 1))
            foam = gl.GLMeshItem(
                vertexes=v2, faces=f2, faceColors=c2,
                smooth=False, drawEdges=True, edgeColor=fb["edge_color"]
            )
            self.addItem(foam)
            self._rov_items.append(foam)

    # --------------------------------------------------------
    # CẬP NHẬT TRẠNG THÁI
    # --------------------------------------------------------
    def update_state(self, quat_xyzw: np.ndarray, vel_ned: np.ndarray):
        """Cập nhật góc nghiêng và vector vận tốc."""
        self._current_quat = quat_xyzw.copy()
        self._velocity = vel_ned.copy()
        
        # Xoay mô hình ROV
        self._apply_transform(quat_xyzw)
        
        # Vẽ vector vận tốc 3D
        self._update_velocity_vector(vel_ned, quat_xyzw)

    def _apply_transform(self, quat_xyzw):
        qx, qy, qz, qw = quat_xyzw
        sinr_cosp = 2*(qw*qx + qy*qz)
        cosr_cosp = 1 - 2*(qx*qx + qy*qy)
        roll = math.degrees(math.atan2(sinr_cosp, cosr_cosp))
        
        sinp = 2*(qw*qy - qz*qx)
        sinp = max(-1.0, min(1.0, sinp))
        pitch = math.degrees(math.asin(sinp))
        
        siny_cosp = 2*(qw*qz + qx*qy)
        cosy_cosp = 1 - 2*(qy*qy + qz*qz)
        yaw = math.degrees(math.atan2(siny_cosp, cosy_cosp))

        for item in self._rov_items:
            item.resetTransform()
            item.rotate(yaw, 0, 0, 1)
            item.rotate(pitch, 0, 1, 0)
            item.rotate(roll, 1, 0, 0)

    def _update_velocity_vector(self, vel_ned, quat_xyzw):
        """Vẽ vector vận tốc 3D từ ROV."""
        if self._vel_vector_item is not None:
            self.removeItem(self._vel_vector_item)
            self._vel_vector_item = None

        # Chuyển đổi vận tốc từ hệ NED sang OpenGL: X->X, Y->-Y, Z->-Z
        vel_gl = np.array([vel_ned[0], -vel_ned[1], -vel_ned[2]])
        speed = np.linalg.norm(vel_gl)
        if speed < 0.05:
            return  # Dừng hẳn thì không vẽ vector

        # Vẽ mũi tên hướng di chuyển bắt đầu từ tâm (0,0,0)
        # Giới hạn chiều dài hiển thị vector
        max_len = 0.6
        scale = 1.0
        v_dir = vel_gl / speed
        length = min(speed * scale, max_len)
        end_pt = v_dir * length

        pts = np.array([[0.0, 0.0, 0.0], end_pt], dtype=np.float32)
        
        # GLLinePlotItem vẽ đường mũi tên dày màu vàng
        self._vel_vector_item = gl.GLLinePlotItem(
            pos=pts, color=self.COLOR_VELOCITY, width=3.0, antialias=True
        )
        self.addItem(self._vel_vector_item)

    def update_slam_points(self, pts_xyz: np.ndarray):
        """Hiển thị point cloud 3D quanh ROV."""
        if pts_xyz is None or len(pts_xyz) == 0:
            return
        
        # Đổi trục: NED -> OpenGL
        gl_pts = pts_xyz.copy()
        gl_pts[:, 1] *= -1
        gl_pts[:, 2] *= -1

        # Giới hạn bán kính hiển thị trong radar (tối đa 1.5m)
        dists = np.linalg.norm(gl_pts, axis=1)
        valid_mask = dists <= 1.5
        gl_pts = gl_pts[valid_mask]
        dists = dists[valid_mask]

        if len(gl_pts) == 0:
            return

        # Màu sắc theo khoảng cách: gần -> đỏ, xa -> xanh
        colors = np.zeros((len(gl_pts), 4), dtype=np.float32)
        for i, d in enumerate(dists):
            if d < 0.6:
                colors[i] = [1.0, 0.1, 0.1, 0.85]  # Đỏ nguy hiểm
            elif d < 1.1:
                colors[i] = [1.0, 0.8, 0.0, 0.8]   # Vàng cảnh báo
            else:
                colors[i] = [0.0, 0.8, 1.0, 0.75]  # Cyan an toàn

        if self._slam_item is not None:
            self._slam_item.setData(pos=gl_pts, color=colors, size=3.5)
        else:
            self._slam_item = gl.GLScatterPlotItem(
                pos=gl_pts, color=colors, size=3.5, pxMode=True
            )
            self.addItem(self._slam_item)
