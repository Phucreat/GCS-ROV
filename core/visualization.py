import numpy as np
import math
import struct
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QRadialGradient
import pyqtgraph.opengl as gl


class CADLoader:
    @staticmethod
    def load_mesh(filepath):
        """Loads STL or OBJ file and returns (vertices, faces)."""
        if filepath.lower().endswith('.stl'):
            return CADLoader.parse_stl(filepath)
        elif filepath.lower().endswith('.obj'):
            return CADLoader.parse_obj(filepath)
        else:
            raise ValueError("Unsupported file format. Use .stl or .obj")

    @staticmethod
    def parse_stl(filepath):
        """Parses binary or ASCII STL files."""
        with open(filepath, 'rb') as f:
            header = f.read(80)
            if len(header) < 80:
                raise ValueError("File too short for STL")

            is_ascii = False
            try:
                text_sample = header.decode('utf-8', errors='ignore')
                if text_sample.strip().startswith('solid'):
                    f.seek(0)
                    rest = f.read(2000).decode('utf-8', errors='ignore')
                    if 'facet normal' in rest or 'outer loop' in rest:
                        is_ascii = True
            except Exception:
                pass

            if is_ascii:
                f.seek(0)
                return CADLoader._parse_ascii_stl(f.read().decode('utf-8', errors='ignore'))
            else:
                return CADLoader._parse_binary_stl(f)

    @staticmethod
    def _parse_binary_stl(file_handle):
        """Helper to parse binary STL file."""
        num_triangles_bytes = file_handle.read(4)
        if len(num_triangles_bytes) < 4:
            raise ValueError("Missing triangle count in binary STL")
        num_triangles = struct.unpack('<I', num_triangles_bytes)[0]

        triangles_data = file_handle.read(num_triangles * 50)
        actual_triangles = len(triangles_data) // 50

        vertices = []
        faces = []

        for idx in range(actual_triangles):
            offset = idx * 50
            tdata = struct.unpack('<12fH', triangles_data[offset:offset+50])

            v1 = tdata[3:6]
            v2 = tdata[6:9]
            v3 = tdata[9:12]

            vertices.extend([v1, v2, v3])
            v_idx = idx * 3
            faces.append([v_idx, v_idx+1, v_idx+2])

        return np.array(vertices, dtype=np.float32), np.array(faces, dtype=np.int32)

    @staticmethod
    def _parse_ascii_stl(text):
        """Helper to parse ASCII STL file."""
        import re
        vertices = []
        faces = []

        vertex_pattern = re.compile(r'vertex\s+([^\s]+)\s+([^\s]+)\s+([^\s]+)')
        matches = vertex_pattern.findall(text)
        for m in matches:
            vertices.append([float(m[0]), float(m[1]), float(m[2])])

        num_triangles = len(vertices) // 3
        for idx in range(num_triangles):
            v_idx = idx * 3
            faces.append([v_idx, v_idx+1, v_idx+2])

        return np.array(vertices, dtype=np.float32), np.array(faces, dtype=np.int32)

    @staticmethod
    def parse_obj(filepath):
        """Parses wavefront OBJ files, triangulating polygons."""
        vertices = []
        faces = []
        with open(filepath, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                parts = line.split()
                if not parts:
                    continue
                if parts[0] == 'v':
                    vertices.append(
                        [float(parts[1]), float(parts[2]), float(parts[3])])
                elif parts[0] == 'f':
                    face_idx = []
                    for p in parts[1:]:
                        v_idx = int(p.split('/')[0])
                        if v_idx > 0:
                            face_idx.append(v_idx - 1)
                        elif v_idx < 0:
                            face_idx.append(len(vertices) + v_idx)

                    if len(face_idx) >= 3:
                        for i in range(1, len(face_idx) - 1):
                            faces.append(
                                [face_idx[0], face_idx[i], face_idx[i+1]])

        return np.array(vertices, dtype=np.float32), np.array(faces, dtype=np.int32)


class GLROVWidget(gl.GLViewWidget):
    def __init__(self, parent=None, version="6-thruster"):
        super().__init__(parent)
        # Futuristic dark blue-black background
        self.setBackgroundColor('#080E18')
        self.version = version

        # Camera Settings
        self.setCameraPosition(distance=2.5, elevation=25, azimuth=-45)

        # Grid Configuration
        self.grid = gl.GLGridItem()
        self.grid.setSize(x=40, y=40, z=0)
        self.grid.setSpacing(x=1, y=1, z=0)
        self.grid.setColor(QtGui.QColor(0, 160, 220, 45)
                           )  # Sleek cyan grid lines
        self.addItem(self.grid)

        # Axes Configuration
        self.axes = gl.GLAxisItem()
        self.axes.setSize(x=1.5, y=1.5, z=1.5)
        self.addItem(self.axes)

        # Trajectory Path Setup
        self.path_points = []
        self.max_path_points = 500

        self.trajectory_line = gl.GLLinePlotItem(
            color=QtGui.QColor(0, 240, 255, 200),  # Neon cyan path line
            width=2,
            mode='line_strip'
        )
        self.addItem(self.trajectory_line)

        self.trajectory_dots = gl.GLScatterPlotItem(
            color=np.array([1.0, 0.2, 0.2, 0.8]),  # Transparent neon red dots
            size=6,
            pxMode=True
        )
        self.addItem(self.trajectory_dots)

        # 3D SLAM Point Cloud Scatter Plot
        self.slam_points_item = gl.GLScatterPlotItem(
            color=np.array([0.0, 1.0, 0.5, 0.6]),  # Glowing neon green
            size=5,
            pxMode=True
        )
        self.addItem(self.slam_points_item)

        # List to track all parts of the ROV model
        self.rov_parts = []
        self.light_cones = []
        self.custom_cad_path = None

        # Load default ROV model
        self.build_rov_model()

    def build_rov_model(self):
        """Builds procedural ROV model depending on active configuration."""
        self.clear_rov()

        if self.custom_cad_path is not None:
            self.import_cad_model(self.custom_cad_path)
            return

        if self.version == "3-thruster":
            # Procedural 3-thruster ROV (Sleek triangular frames)
            # Main Chassis (Central triangular wedge shape)
            v_chassis = np.array([
                [0.2, 0.0, 0.08], [-0.25, 0.15,
                                   0.08], [-0.25, -0.15, 0.08],  # Top triangle
                [0.2, 0.0, -0.08], [-0.25, 0.15, -
                                    # Bottom triangle
                                    0.08], [-0.25, -0.15, -0.08]
            ], dtype=np.float32)
            f_chassis = np.array([
                [0, 1, 2], [5, 4, 3],  # top/bottom caps
                [0, 3, 4], [0, 4, 1],  # front port
                [0, 2, 5], [0, 5, 3],  # front starboard
                [1, 4, 5], [1, 5, 2]  # rear plate
            ], dtype=np.int32)

            m_chassis = gl.GLMeshItem(
                vertexes=v_chassis, faces=f_chassis,
                color=(0.12, 0.22, 0.32, 0.8), edgeColor=(0.0, 0.8, 1.0, 0.5),
                drawEdges=True, smooth=True
            )
            self.addItem(m_chassis)
            self.rov_parts.append(m_chassis)

            # Thrusters (2 Horizontal on side plates, 1 Vertical in center)
            # T1: Port Horizontal, T2: Starboard Horizontal
            h_thrusters = [
                ([0.0, 0.16, 0.0], 0),
                ([0.0, -0.16, 0.0], 0)
            ]
            for pos, yaw in h_thrusters:
                v_cyl, f_cyl = self._generate_cylinder(
                    radius=0.035, length=0.08, direction='x')
                v_cyl += np.array([-0.04, 0.0, 0.0])
                v_cyl = self._rotate_vertices(v_cyl, 0, 0, yaw)
                v_cyl += np.array(pos)
                m_cyl = gl.GLMeshItem(
                    vertexes=v_cyl, faces=f_cyl,
                    color=(0.15, 0.15, 0.15, 1.0), edgeColor=(0.0, 0.6, 0.8, 0.6),
                    drawEdges=True, smooth=True
                )
                self.addItem(m_cyl)
                self.rov_parts.append(m_cyl)

            # T3: Vertical Center
            v_cyl, f_cyl = self._generate_cylinder(
                radius=0.04, length=0.08, direction='z')
            # center and offset backwards
            v_cyl += np.array([-0.1, 0.0, -0.04])
            m_cyl = gl.GLMeshItem(
                vertexes=v_cyl, faces=f_cyl,
                color=(0.15, 0.15, 0.15, 1.0), edgeColor=(0.0, 0.6, 0.8, 0.6),
                drawEdges=True, smooth=True
            )
            self.addItem(m_cyl)
            self.rov_parts.append(m_cyl)

            # Front Headlight and Light cone (Single center camera & headlight)
            pos_light = [0.2, 0.0, 0.0]
            v_cyl, f_cyl = self._generate_cylinder(
                radius=0.025, length=0.03, direction='x')
            v_cyl += np.array(pos_light)
            m_cyl = gl.GLMeshItem(
                vertexes=v_cyl, faces=f_cyl,
                color=(0.8, 0.8, 0.8, 1.0), edgeColor=(1.0, 1.0, 0.0, 0.6),
                drawEdges=True, smooth=True
            )
            self.addItem(m_cyl)
            self.rov_parts.append(m_cyl)

            # Volumetric cone
            v_cone, f_cone = self._generate_cylinder(
                radius=0.024, length=1.5, direction='x', radius2=0.35)
            v_cone += np.array(pos_light) + np.array([0.03, 0.0, 0.0])
            m_cone = gl.GLMeshItem(
                vertexes=v_cone, faces=f_cone,
                color=(0.0, 0.8, 1.0, 0.08), smooth=True, blending='additive'
            )
            self.addItem(m_cone)
            self.rov_parts.append(m_cone)
            self.light_cones.append(m_cone)

        else:
            # Procedural 6-thruster ROV (BlueROV2 box shape)
            # Main Chassis (Slate Box)
            v_chassis, f_chassis = self._generate_box(0.45, 0.34, 0.22)
            m_chassis = gl.GLMeshItem(
                vertexes=v_chassis, faces=f_chassis,
                color=(0.1, 0.15, 0.25, 0.85), edgeColor=(0.0, 0.8, 1.0, 0.4),
                drawEdges=True, smooth=True
            )
            self.addItem(m_chassis)
            self.rov_parts.append(m_chassis)

            # Buoyancy foam block (White top cover)
            v_shield, f_shield = self._generate_box(0.48, 0.36, 0.05)
            v_shield += np.array([0.0, 0.0, 0.13])
            m_shield = gl.GLMeshItem(
                vertexes=v_shield, faces=f_shield,
                color=(0.92, 0.92, 0.95, 0.95), edgeColor=(0.0, 0.8, 1.0, 0.5),
                drawEdges=True, smooth=True
            )
            self.addItem(m_shield)
            self.rov_parts.append(m_shield)

            # Thrusters: 4 Horizontal angled at 45 degrees, 2 vertical
            h_thrusters = [
                ([0.15, -0.15, 0.0], 45),
                ([0.15, 0.15, 0.0], -45),
                ([-0.15, -0.15, 0.0], -135),
                ([-0.15, 0.15, 0.0], 135)
            ]
            for pos, yaw in h_thrusters:
                v_cyl, f_cyl = self._generate_cylinder(
                    radius=0.04, length=0.1, direction='x')
                v_cyl += np.array([-0.05, 0.0, 0.0])
                v_cyl = self._rotate_vertices(v_cyl, 0, 0, yaw)
                v_cyl += np.array(pos)
                m_cyl = gl.GLMeshItem(
                    vertexes=v_cyl, faces=f_cyl,
                    color=(0.15, 0.15, 0.15, 1.0), edgeColor=(0.0, 0.6, 0.8, 0.6),
                    drawEdges=True, smooth=True
                )
                self.addItem(m_cyl)
                self.rov_parts.append(m_cyl)

            # 2 Vertical Thrusters
            v_thrusters = [
                [0.0, -0.12, 0.05],
                [0.0, 0.12, 0.05]
            ]
            for pos in v_thrusters:
                v_cyl, f_cyl = self._generate_cylinder(
                    radius=0.035, length=0.09, direction='z')
                v_cyl += np.array([0.0, 0.0, -0.045])
                v_cyl += np.array(pos)
                m_cyl = gl.GLMeshItem(
                    vertexes=v_cyl, faces=f_cyl,
                    color=(0.15, 0.15, 0.15, 1.0), edgeColor=(0.0, 0.6, 0.8, 0.6),
                    drawEdges=True, smooth=True
                )
                self.addItem(m_cyl)
                self.rov_parts.append(m_cyl)

            # 2 Headlights
            light_positions = [
                [0.21, -0.08, -0.04],
                [0.21, 0.08, -0.04]
            ]
            for pos in light_positions:
                v_cyl, f_cyl = self._generate_cylinder(
                    radius=0.02, length=0.04, direction='x')
                v_cyl += np.array(pos)
                m_cyl = gl.GLMeshItem(
                    vertexes=v_cyl, faces=f_cyl,
                    color=(0.8, 0.8, 0.8, 1.0), edgeColor=(1.0, 1.0, 0.0, 0.5),
                    drawEdges=True, smooth=True
                )
                self.addItem(m_cyl)
                self.rov_parts.append(m_cyl)

                v_cone, f_cone = self._generate_cylinder(
                    radius=0.019, length=1.5, direction='x', radius2=0.35)
                v_cone += np.array(pos) + np.array([0.04, 0.0, 0.0])
                m_cone = gl.GLMeshItem(
                    vertexes=v_cone, faces=f_cone,
                    color=(0.0, 0.8, 1.0, 0.08), smooth=True, blending='additive'
                )
                self.addItem(m_cone)
                self.rov_parts.append(m_cone)
                self.light_cones.append(m_cone)

    def change_configuration(self, version):
        """Sets version type and rebuilds default models."""
        self.version = version
        self.build_rov_model()

    def import_cad_model(self, filepath):
        """Imports an STL/OBJ CAD model."""
        try:
            vertices, faces = CADLoader.load_mesh(filepath)
            self.custom_cad_path = filepath

            # Bounding box scaling
            vmin = vertices.min(axis=0)
            vmax = vertices.max(axis=0)
            center = (vmin + vmax) / 2.0
            size = vmax - vmin
            max_dim = size.max()

            scale = 0.5 / max_dim if max_dim > 0 else 1.0
            vertices = (vertices - center) * scale

            self.clear_rov()

            cad_mesh = gl.GLMeshItem(
                vertexes=vertices, faces=faces,
                color=(0.2, 0.45, 0.65, 0.85), edgeColor=(0.0, 0.8, 1.0, 0.5),
                drawEdges=True, smooth=True
            )
            self.addItem(cad_mesh)
            self.rov_parts.append(cad_mesh)

            # Headlights for imported CAD
            light_positions = [[0.22, -0.06, 0.0], [0.22, 0.06, 0.0]]
            for pos in light_positions:
                v_cone, f_cone = self._generate_cylinder(
                    radius=0.015, length=1.5, direction='x', radius2=0.35)
                v_cone += np.array(pos)
                m_cone = gl.GLMeshItem(
                    vertexes=v_cone, faces=f_cone,
                    color=(0.0, 0.8, 1.0, 0.08), smooth=True, blending='additive'
                )
                self.addItem(m_cone)
                self.rov_parts.append(m_cone)
                self.light_cones.append(m_cone)
            return True
        except Exception as e:
            print(f"Error importing CAD: {e}")
            return False

    def clear_rov(self):
        for part in self.rov_parts:
            self.removeItem(part)
        self.rov_parts.clear()
        self.light_cones.clear()

    def update_pose(self, position, orientation_quat):
        m = QtGui.QMatrix4x4()
        m.translate(position[0], position[1], position[2])
        q = QtGui.QQuaternion(
            orientation_quat[3],
            orientation_quat[0],
            orientation_quat[1],
            orientation_quat[2]
        )
        m.rotate(q)

        for part in self.rov_parts:
            part.setTransform(m)

        self.path_points.append(position)
        if len(self.path_points) > self.max_path_points:
            self.path_points.pop(0)

        pts = np.array(self.path_points)
        self.trajectory_line.setData(pos=pts)

        dot_indices = list(range(0, len(self.path_points), 10))
        if len(self.path_points) - 1 not in dot_indices and len(self.path_points) > 0:
            dot_indices.append(len(self.path_points) - 1)

        self.trajectory_dots.setData(pos=pts[dot_indices])

    def update_slam_points(self, points):
        """Updates the 3D scatter plot of visual SLAM points."""
        if len(points) > 0:
            self.slam_points_item.setData(pos=np.array(points))

    def toggle_headlights(self, enabled):
        for cone in self.light_cones:
            cone.setVisible(enabled)

    # Mesh Helpers
    def _generate_box(self, dx, dy, dz):
        x, y, z = dx/2.0, dy/2.0, dz/2.0
        vertices = np.array([
            [-x, -y, -z], [x, -y, -z], [x,  y, -z], [-x,  y, -z],
            [-x, -y,  z], [x, -y,  z], [x,  y,  z], [-x,  y,  z]
        ], dtype=np.float32)
        faces = np.array([
            [0, 1, 2], [0, 2, 3], [4, 5, 6], [4, 6, 7],
            [0, 1, 5], [0, 5, 4], [1, 2, 6], [1, 6, 5],
            [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7]
        ], dtype=np.int32)
        return vertices, faces

    def _generate_cylinder(self, radius, length, direction='z', cols=16, radius2=None):
        r1 = radius
        r2 = radius if radius2 is None else radius2
        vertices = []
        faces = []

        for i in range(cols):
            theta = 2.0 * math.pi * i / cols
            cos_t, sin_t = math.cos(theta), math.sin(theta)

            if direction == 'x':
                vertices.append([0.0, r1 * cos_t, r1 * sin_t])
                vertices.append([length, r2 * cos_t, r2 * sin_t])
            elif direction == 'y':
                vertices.append([r1 * cos_t, 0.0, r1 * sin_t])
                vertices.append([r2 * cos_t, length, r2 * sin_t])
            else:  # z
                vertices.append([r1 * cos_t, r1 * sin_t, 0.0])
                vertices.append([r2 * cos_t, r2 * sin_t, length])

        for i in range(cols):
            v0 = i * 2
            v1 = v0 + 1
            v2 = ((i + 1) % cols) * 2
            v3 = v2 + 1
            faces.append([v0, v1, v3])
            faces.append([v0, v3, v2])

        c1_idx = len(vertices)
        vertices.append([0.0, 0.0, 0.0])
        c2_idx = len(vertices)
        if direction == 'x':
            vertices.append([length, 0.0, 0.0])
        elif direction == 'y':
            vertices.append([0.0, length, 0.0])
        else:
            vertices.append([0.0, 0.0, length])

        for i in range(cols):
            v0 = i * 2
            v1 = v0 + 1
            v2 = ((i + 1) % cols) * 2
            faces.append([v0, v2, c1_idx])
            faces.append([v1, c2_idx, v2 + 1])

        return np.array(vertices, dtype=np.float32), np.array(faces, dtype=np.int32)

    def _rotate_vertices(self, vertices, roll, pitch, yaw):
        r, p, y = math.radians(roll), math.radians(pitch), math.radians(yaw)
        Rx = np.array([[1, 0, 0], [0, math.cos(r), -math.sin(r)],
                      [0, math.sin(r), math.cos(r)]])
        Ry = np.array([[math.cos(p), 0, math.sin(p)], [
                      0, 1, 0], [-math.sin(p), 0, math.cos(p)]])
        Rz = np.array([[math.cos(y), -math.sin(y), 0],
                      [math.sin(y), math.cos(y), 0], [0, 0, 1]])
        R = Rz @ Ry @ Rx
        return vertices @ R.T


class SLAMRadarWidget(QWidget):
    """
    Futuristic 2D Polar SLAM Minimap / Radar display.
    Places the ROV in the center, rotating according to attitude (roll, pitch, yaw).
    Plots SLAM points colored by proximity warning levels (Red, Yellow, Green).
    Includes translucent camera Field-of-View (FOV) sweeping projection.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(250, 250)

        # State variables
        self.rov_pos = np.array([0.0, 0.0, 0.0])
        self.rov_yaw = 0.0
        self.rov_pitch = 0.0
        self.rov_roll = 0.0

        self.slam_points = []  # Array of [x, y, z] points in world frame

        # Display settings
        self.radar_radius_meters = 4.0  # Range shown by the outermost circle

    def update_state(self, position, roll, pitch, yaw):
        self.rov_pos = np.array(position)
        self.rov_roll = roll
        self.rov_pitch = pitch
        self.rov_yaw = yaw
        self.update()

    def update_points(self, points):
        self.slam_points = points
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        width = self.width()
        height = self.height()
        center_x = width // 2
        center_y = height // 2
        radar_size = min(width, height) - 20
        radius_px = radar_size // 2

        pixels_per_meter = radius_px / self.radar_radius_meters

        # 1. Background Fill (Very dark HUD blue-black)
        painter.fillRect(self.rect(), QColor("#060b13"))

        # 2. Polar Grid Circles (1m, 2m, 3m, 4m)
        painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))

        grid_rings = [1.0, 2.0, 3.0, 4.0]
        for ring in grid_rings:
            ring_r = int(ring * pixels_per_meter)
            # Fading grid styling
            pen_color = QColor(0, 180, 220, 30 if ring != 3.0 else 60)
            pen_width = 1 if ring != 3.0 else 2
            painter.setPen(QPen(pen_color, pen_width, Qt.PenStyle.SolidLine))
            painter.drawEllipse(center_x - ring_r, center_y -
                                ring_r, ring_r * 2, ring_r * 2)

            # Label
            painter.setPen(QColor(0, 160, 200, 100))
            painter.setFont(QFont("Consolas", 8))
            painter.drawText(center_x + 5, center_y -
                             ring_r + 12, f"{int(ring)}M")

        # 3. Radial angle helper lines (every 30 degrees)
        painter.setPen(QPen(QColor(0, 180, 220, 20), 1, Qt.PenStyle.DashLine))
        for angle in range(0, 360, 30):
            rad = math.radians(angle)
            x_end = center_x + radius_px * math.cos(rad)
            y_end = center_y + radius_px * math.sin(rad)
            painter.drawLine(center_x, center_y, int(x_end), int(y_end))

        # 4. Camera Field-Of-View (FOV) Fan (Projecting forward from ROV nose)
        # In SNAME/ROV frame, forward is X (straight up in widget)
        # We sweep +/- 30 degrees from the forward axis (90 deg relative to canvas angles)
        fov_angle = 60  # degrees
        painter.save()
        painter.translate(center_x, center_y)
        # Rotate by yaw so the FOV sweep aligns with actual heading
        # Qt angles are clockwise, heading is clockwise (0 at North/Up)
        # To point up at yaw=0, we rotate -90 degrees initially
        painter.rotate(-self.rov_yaw)

        # Draw translucent sector
        fov_gradient = QRadialGradient(0, 0, radius_px)
        fov_gradient.setColorAt(0.0, QColor(
            0, 229, 255, 60))  # Glowing cyan center
        fov_gradient.setColorAt(0.6, QColor(0, 180, 220, 20))
        fov_gradient.setColorAt(1.0, QColor(0, 0, 0, 0)
                                )  # fade out at boundary
        painter.setBrush(QBrush(fov_gradient))
        painter.setPen(Qt.PenStyle.NoPen)

        # Sector goes from -fov_angle/2 to +fov_angle/2 relative to straight UP (-90 deg)
        start_angle_qt = -90 - (fov_angle // 2)
        # Qt drawChord/drawPie takes 1/16th degree
        painter.drawPie(-radius_px, -radius_px, radius_px * 2, radius_px *
                        2, int(-start_angle_qt * 16), int(-fov_angle * 16))
        painter.restore()

        # 5. Plot SLAM Point Cloud (ROV-Centric mapping)
        # Points color indicates hazard levels: Red (<1.0m), Yellow (<2.5m), Green (>=2.5m)
        for pt in self.slam_points:
            # Translation relative to ROV
            dx = pt[0] - self.rov_pos[0]
            dy = pt[1] - self.rov_pos[1]

            # Rotate points by negative yaw so the radar frame is ROV-centric (ROV points UP)
            rad_yaw = -math.radians(self.rov_yaw)
            # Body coordinate: forward (X), port (Y)
            rx = dx * math.cos(rad_yaw) - dy * math.sin(rad_yaw)
            ry = dx * math.sin(rad_yaw) + dy * math.cos(rad_yaw)

            # Map body coordinates to Widget Canvas coordinates:
            # Forward body (rx) -> Upward widget (-y)
            # Port body (ry) -> Leftward widget (-x), Starboard (-ry) -> Rightward (+x)
            pt_x = center_x + int((-ry) * pixels_per_meter)
            pt_y = center_y - int(rx * pixels_per_meter)

            # Check boundaries
            dist_2d = math.sqrt(dx*dx + dy*dy)
            if dist_2d > self.radar_radius_meters:
                continue  # Outside radar sweep distance

            # Classify danger levels
            if dist_2d < 1.0:
                color = QColor("#ff3333")  # Red (Danger)
            elif dist_2d < 2.5:
                color = QColor("#ffcc00")  # Yellow (Warning)
            else:
                color = QColor("#00ff66")  # Green (Safe)

            # Draw point dot
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(pt_x - 3, pt_y - 3, 6, 6)

        # 6. Central ROV icon (Top-down view profile, rotated by local Roll/Pitch)
        painter.save()
        painter.translate(center_x, center_y)
        # The minimap is ROV-centric, so the ROV stays in the center pointing UP.
        # But we can rotate the icon representing minor yaw/pitch/roll fluctuations if desired,
        # or keep the map north-up and rotate the ROV. Let's make the radar HEADING-UP (ROV always points up),
        # but we draw yaw/pitch/roll labels for precision, and show yaw on the outer compass ring.
        # Wait, having the ROV point straight UP (yaw=0 in ROV frame) is highly readable for heading-up radar.

        # Let's draw a high-tech ROV schematic:
        # Main hull box
        painter.setBrush(QBrush(QColor("#0f233c")))
        painter.setPen(QPen(QColor("#00e5ff"), 2))

        # Dimensions for drawing: 40px length, 30px width
        painter.drawRoundedRect(-15, -20, 30, 40, 5, 5)

        # Draw side thruster wings
        painter.setBrush(QBrush(QColor("#060b13")))
        painter.drawRect(-20, -12, 5, 10)  # Port thruster
        painter.drawRect(15, -12, 5, 10)  # Starboard thruster

        # Draw front camera lens block
        painter.setBrush(QBrush(QColor("#00e5ff")))
        painter.drawRect(-6, -23, 12, 4)

        # Highlight Center indicator dot
        painter.setBrush(QBrush(QColor("#ffffff")))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(-2, -2, 4, 4)

        painter.restore()

        # 7. Draw Outer Compass ring indicator
        painter.setPen(QPen(QColor(0, 229, 255, 80), 1))
        painter.drawEllipse(center_x - radius_px, center_y -
                            radius_px, radius_px * 2, radius_px * 2)

        # Cardinal labels (North, East, South, West) rotating on the outer ring to show direction
        cardinals = [("N", 0), ("E", 90), ("S", 180), ("W", 270)]
        for text, angle in cardinals:
            # We offset by heading to rotate cardinals relative to the ROV's heading
            rel_angle = angle - self.rov_yaw - 90
            rad = math.radians(rel_angle)
            tx = center_x + (radius_px - 15) * math.cos(rad)
            ty = center_y + (radius_px - 15) * math.sin(rad)

            painter.setPen(QColor("#00e5ff") if text ==
                           "N" else QColor("#8c9ba5"))
            painter.setFont(
                QFont("Consolas", 8, QFont.Weight.Bold if text == "N" else QFont.Weight.Normal))
            # Center the text
            painter.drawText(int(tx) - 5, int(ty) + 4, text)
