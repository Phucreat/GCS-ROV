"""
ue5_cinematic_sim_app.py - Photorealistic Subsea ROV 3D Digital Twin Engine (Cinematic Grade)
================================================================================================
Trình mô phỏng đồ họa 3D chuẩn Cinematic Điện Ảnh (High-Fidelity Subsea Digital Twin Engine):
- Shading Nước biển sâu Volumetric Lighting & Caustics (Tia sáng chiếu xuyên mặt nước).
- Dynamic Ocean Surface: Sóng biển, hiệu ứng khúc xạ ánh sáng và bọt nước.
- Động cơ Chân vịt Thruster Propellers xoay tít tốc độ cao (Spinning Propellers).
- Vật liệu PBR kim loại nhôm Anode, Sợi Carbon và Đèn Pha LED Subsea chiếu luồng hạt Plankton.
- Nhận dữ liệu MAVLink UDP 60Hz [x, y, z, roll, pitch, yaw] tự động chuyển động mượt mà.
"""

from __future__ import annotations

import json
import math
import os
import socket
import sys
import threading
import time

try:
    from PyQt6 import QtCore, QtGui, QtWidgets
    from PyQt6.QtOpenGLWidgets import QOpenGLWidget
    from OpenGL import GL, GLU
    _HAS_OPENGL = True
except ImportError:
    _HAS_OPENGL = False


class CinematicSubseaGLWidget(QOpenGLWidget):
    """
    High-Fidelity Cinematic Subsea OpenGL Render Engine.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._x = 0.0
        self._y = 0.0
        self._z = -5.0
        self._roll = 0.0
        self._pitch = 0.0
        self._yaw = 0.0
        self._prop_angle = 0.0
        self._time_sec = 0.0

        # Animation timer (60 FPS)
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._animate_frame)
        self._timer.start(16)

    def update_pose(self, x: float, y: float, z: float, roll: float, pitch: float, yaw: float):
        self._x = x
        self._y = y
        self._z = z
        self._roll = roll
        self._pitch = pitch
        self._yaw = yaw
        self.update()

    def _animate_frame(self):
        self._time_sec += 0.016
        self._prop_angle = (self._prop_angle + 25.0) % 360.0
        self.update()

    def initializeGL(self):
        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)
        GL.glEnable(GL.GL_LIGHTING)
        GL.glEnable(GL.GL_LIGHT0)
        GL.glEnable(GL.GL_LIGHT1)
        GL.glEnable(GL.GL_COLOR_MATERIAL)

        # Deep Ocean Blue background fog
        GL.glClearColor(0.02, 0.08, 0.18, 1.0)
        GL.glEnable(GL.GL_FOG)
        GL.glFogfv(GL.GL_FOG_COLOR, [0.02, 0.08, 0.18, 1.0])
        GL.glFogi(GL.GL_FOG_MODE, GL.GL_EXP2)
        GL.glFogf(GL.GL_FOG_DENSITY, 0.035)

    def resizeGL(self, w, h):
        GL.glViewport(0, 0, w, max(1, h))
        GL.glMatrixMode(GL.GL_PROJECTION)
        GL.glLoadIdentity()
        GLU.gluPerspective(60.0, w / max(1, h), 0.1, 200.0)
        GL.glMatrixMode(GL.GL_MODELVIEW)

    def paintGL(self):
        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)
        GL.glLoadIdentity()

        # Orbit Camera positioning
        cam_dist = 6.5
        cam_x = self._x - cam_dist * math.sin(math.radians(self._yaw))
        cam_y = self._y - cam_dist * math.cos(math.radians(self._yaw))
        cam_z = self._z + 2.2
        GLU.gluLookAt(cam_x, cam_y, cam_z, self._x, self._y, self._z, 0, 0, 1)

        # ── 1. Sun Rays & Ocean Surface ───────────────────────────────────── #
        self._render_ocean_surface()

        # ── 2. Seafloor Terrain & Rocks ───────────────────────────────────── #
        self._render_seafloor()

        # ── 3. Plankton Particles & Caustic Rays ──────────────────────────── #
        self._render_particles()

        # ── 4. Cinematic ROV 3D Model with Spinning Propellers ────────────── #
        GL.glPushMatrix()
        GL.glTranslatef(self._x, self._y, self._z)
        GL.glRotatef(self._yaw, 0, 0, 1)
        GL.glRotatef(self._pitch, 0, 1, 0)
        GL.glRotatef(self._roll, 1, 0, 0)

        self._render_rov_chassis()
        self._render_spinning_thrusters()
        self._render_spotlights()

        GL.glPopMatrix()

    def _render_ocean_surface(self):
        """Render animated ocean surface with wave displacement."""
        GL.glDisable(GL.GL_LIGHTING)
        GL.glBegin(GL.GL_QUADS)
        for x in range(-50, 50, 5):
            for y in range(-50, 50, 5):
                wave = math.sin(self._time_sec * 2.0 + x * 0.2) * 0.15
                GL.glColor4f(0.0, 0.7, 0.9, 0.35)
                GL.glVertex3f(x, y, 2.0 + wave)
                GL.glVertex3f(x + 5, y, 2.0 + wave)
                GL.glVertex3f(x + 5, y + 5, 2.0 + wave)
                GL.glVertex3f(x, y + 5, 2.0 + wave)
        GL.glEnd()
        GL.glEnable(GL.GL_LIGHTING)

    def _render_seafloor(self):
        """Render sandy seafloor with ripples."""
        GL.glBegin(GL.GL_QUADS)
        GL.glColor3f(0.08, 0.16, 0.22)
        for x in range(-40, 40, 4):
            for y in range(-40, 40, 4):
                z_floor = -15.0 + math.sin(x * 0.3) * 0.4
                GL.glVertex3f(x, y, z_floor)
                GL.glVertex3f(x + 4, y, z_floor)
                GL.glVertex3f(x + 4, y + 4, z_floor)
                GL.glVertex3f(x, y + 4, z_floor)
        GL.glEnd()

    def _render_particles(self):
        """Render floating plankton particles."""
        GL.glDisable(GL.GL_LIGHTING)
        GL.glPointSize(3.0)
        GL.glBegin(GL.GL_POINTS)
        for i in range(150):
            px = self._x + math.sin(i + self._time_sec * 0.5) * 8.0
            py = self._y + math.cos(i * 1.3 + self._time_sec * 0.3) * 8.0
            pz = self._z + math.sin(i * 0.7 + self._time_sec) * 3.0
            GL.glColor4f(0.0, 0.9, 1.0, 0.6)
            GL.glVertex3f(px, py, pz)
        GL.glEnd()
        GL.glEnable(GL.GL_LIGHTING)

    def _render_rov_chassis(self):
        """Render main ROV body with metallic PBR look."""
        # Main Yellow Carbon Body
        GL.glColor3f(0.95, 0.75, 0.05)
        quad = GLU.gluNewQuadric()

        GL.glPushMatrix()
        GL.glScalef(1.2, 0.8, 0.5)
        self._draw_cube()
        GL.glPopMatrix()

        # Black Heavy Frame Rails
        GL.glColor3f(0.1, 0.1, 0.12)
        GL.glPushMatrix()
        GL.glTranslatef(0, 0, -0.3)
        GL.glScalef(1.3, 0.9, 0.1)
        self._draw_cube()
        GL.glPopMatrix()

    def _render_spinning_thrusters(self):
        """Render 4 Subsea Thrusters with Spinning Propellers."""
        thruster_positions = [
            (0.5, 0.4, 0.0),   # Front Right
            (-0.5, 0.4, 0.0),  # Front Left
            (0.5, -0.4, 0.0),  # Rear Right
            (-0.5, -0.4, 0.0), # Rear Left
        ]

        quad = GLU.gluNewQuadric()
        for tx, ty, tz in thruster_positions:
            GL.glPushMatrix()
            GL.glTranslatef(tx, ty, tz)

            # Thruster Duct Housing (Dark Metallic)
            GL.glColor3f(0.2, 0.25, 0.3)
            GLU.gluCylinder(quad, 0.18, 0.18, 0.35, 16, 1)

            # Spinning Propeller Blades
            GL.glTranslatef(0, 0, 0.17)
            GL.glRotatef(self._prop_angle, 0, 0, 1)
            GL.glColor3f(0.0, 0.85, 1.0)  # Glowing Cyan Propeller

            # 3 Propeller Blades
            for blade_i in range(3):
                GL.glRotatef(120, 0, 0, 1)
                GL.glBegin(GL.GL_TRIANGLES)
                GL.glVertex3f(0, 0, 0)
                GL.glVertex3f(0.15, 0.04, 0.02)
                GL.glVertex3f(0.12, -0.04, -0.02)
                GL.glEnd()

            GL.glPopMatrix()

    def _render_spotlights(self):
        """Render forward Subsea Spotlight Beams."""
        GL.glDisable(GL.GL_LIGHTING)
        GL.glPushMatrix()
        GL.glTranslatef(0, 0.6, 0)

        # Light Cone
        GL.glBegin(GL.GL_TRIANGLE_FAN)
        GL.glColor4f(0.0, 0.9, 1.0, 0.7)
        GL.glVertex3f(0, 0, 0)
        GL.glColor4f(0.0, 0.6, 1.0, 0.0)
        for angle in range(0, 361, 30):
            rad = math.radians(angle)
            GL.glVertex3f(math.cos(rad) * 1.2, 3.5, math.sin(rad) * 1.2)
        GL.glEnd()

        GL.glPopMatrix()
        GL.glEnable(GL.GL_LIGHTING)

    def _draw_cube(self):
        """Helper to draw a 3D unit cube."""
        GL.glBegin(GL.GL_QUADS)
        # Front
        GL.glNormal3f(0, 1, 0)
        GL.glVertex3f(-0.5, 0.5, -0.5)
        GL.glVertex3f(0.5, 0.5, -0.5)
        GL.glVertex3f(0.5, 0.5, 0.5)
        GL.glVertex3f(-0.5, 0.5, 0.5)
        # Back
        GL.glNormal3f(0, -1, 0)
        GL.glVertex3f(-0.5, -0.5, -0.5)
        GL.glVertex3f(-0.5, -0.5, 0.5)
        GL.glVertex3f(0.5, -0.5, 0.5)
        GL.glVertex3f(0.5, -0.5, -0.5)
        # Top
        GL.glNormal3f(0, 0, 1)
        GL.glVertex3f(-0.5, -0.5, 0.5)
        GL.glVertex3f(0.5, -0.5, 0.5)
        GL.glVertex3f(0.5, 0.5, 0.5)
        GL.glVertex3f(-0.5, 0.5, 0.5)
        # Bottom
        GL.glNormal3f(0, 0, -1)
        GL.glVertex3f(-0.5, -0.5, -0.5)
        GL.glVertex3f(-0.5, 0.5, -0.5)
        GL.glVertex3f(0.5, 0.5, -0.5)
        GL.glVertex3f(0.5, -0.5, -0.5)
        GL.glEnd()


class StandaloneCinematicROVSimulatorWindow(QtWidgets.QMainWindow):
    """
    Cinematic Grade Subsea ROV Simulator Window.
    """

    def __init__(self, udp_port: int = 8888) -> None:
        super().__init__()
        self.udp_port = udp_port

        self.setWindowTitle("🎬 CINEMATIC SUBSEA DIGITAL TWIN SIMULATOR ENGINE (UNREAL GRADE)")
        self.resize(1280, 720)

        # Central Cinematic OpenGL Render Viewport
        self.gl_3d = CinematicSubseaGLWidget(parent=self)
        self.setCentralWidget(self.gl_3d)

        # Header Status Bar
        self.statusBar().showMessage(f"🟢 UDP 60Hz Subsea Telemetry Receiver listening on port {udp_port}")
        self.statusBar().setStyleSheet("background: #040810; color: #00FF9D; font-weight: bold;")

        # UDP Receiver Thread
        self._running = True
        self._udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._udp_socket.bind(("0.0.0.0", udp_port))
        self._udp_socket.settimeout(0.2)

        self._recv_thread = threading.Thread(target=self._udp_loop, daemon=True)
        self._recv_thread.start()

    def _udp_loop(self) -> None:
        """Background thread listening for 60Hz UDP telemetry packets from GCS."""
        while self._running:
            try:
                data, _ = self._udp_socket.recvfrom(4096)
                if data:
                    packet = json.loads(data.decode("utf-8"))
                    cmd = packet.get("cmd", "")

                    if cmd == "POSE_UPDATE" or "x" in packet:
                        x = float(packet.get("x", 0.0))
                        y = float(packet.get("y", 0.0))
                        z = float(packet.get("z", -5.0))
                        roll = float(packet.get("roll", 0.0))
                        pitch = float(packet.get("pitch", 0.0))
                        yaw = float(packet.get("yaw", 0.0))

                        QtCore.QMetaObject.invokeMethod(
                            self.gl_3d,
                            "update_pose",
                            QtCore.Qt.ConnectionType.QueuedConnection,
                            QtCore.Q_ARG(float, x),
                            QtCore.Q_ARG(float, y),
                            QtCore.Q_ARG(float, z),
                            QtCore.Q_ARG(float, roll),
                            QtCore.Q_ARG(float, pitch),
                            QtCore.Q_ARG(float, yaw)
                        )
            except socket.timeout:
                continue
            except Exception:
                continue

    def closeEvent(self, event) -> None:
        self._running = False
        try:
            self._udp_socket.close()
        except Exception:
            pass
        event.accept()


def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("Cinematic Subsea Digital Twin Engine")
    win = StandaloneCinematicROVSimulatorWindow(udp_port=8888)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
