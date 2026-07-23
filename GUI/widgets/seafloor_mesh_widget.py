"""
seafloor_mesh_widget.py - 3D Seafloor Mesh OpenGL Widget
========================================================
Hien thi luoi do sau 3D voi colormap:
  - Luoi tam giac OpenGL (GL_TRIANGLES)
  - Colormap depth (do=nong, xanh=sau)
  - Contour lines (duong dang sau)
  - Scale bar + legend
  - Mouse rotate/zoom/pan
  - Export PNG

Kien truc:
  SeafloorMapper.sig_mesh_updated → SeafloorMeshWidget.on_mesh_updated()
  SeafloorMeshWidget ke thua QOpenGLWidget
"""

from __future__ import annotations

import math
from typing import List, Optional, Tuple

from PyQt6.QtCore import Qt, QPoint, QRect, QSize
from PyQt6.QtGui import (
    QColor, QPainter, QFont, QLinearGradient, QFontMetrics,
    QMouseEvent, QWheelEvent
)
from PyQt6.QtWidgets import QLabel, QSizePolicy, QWidget, QVBoxLayout

# ─────────────────────────────────────────────────────────────────────────────
# Lazy OpenGL import – graceful fallback
# ─────────────────────────────────────────────────────────────────────────────
_OPENGL_AVAILABLE = False
try:
    from PyQt6.QtOpenGLWidgets import QOpenGLWidget
    from OpenGL.GL import (
        glClearColor, glClear, glEnable, glDisable, glBlendFunc,
        glDepthFunc, glMatrixMode, glLoadIdentity, glTranslatef,
        glRotatef, glScalef, glBegin, glEnd, glVertex3f, glColor3f,
        glColor4f, glLineWidth, glPointSize, glViewport,
        glGetFloatv, glPushMatrix, glPopMatrix, glFrustum, glOrtho,
        glRasterPos3f,
        GL_COLOR_BUFFER_BIT, GL_DEPTH_BUFFER_BIT,
        GL_DEPTH_TEST, GL_BLEND, GL_LINES, GL_TRIANGLES, GL_QUADS,
        GL_POINTS, GL_LINE_LOOP, GL_TRIANGLE_FAN,
        GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA,
        GL_LESS, GL_MODELVIEW, GL_PROJECTION,
        GL_SMOOTH, GL_LIGHTING,
    )
    from OpenGL.GLU import gluPerspective, gluLookAt
    _OPENGL_AVAILABLE = True
except ImportError:
    # Define a stub base class so the class declaration doesn't crash
    class QOpenGLWidget(QWidget):  # type: ignore
        def __init__(self, parent=None):
            super().__init__(parent)
        def update(self): super().update()
        def grabFramebuffer(self): return None

# ─────────────────────────────────────────────────────────────────────────────
# Colour helpers
# ─────────────────────────────────────────────────────────────────────────────
# Depth → RGB colormap  (shallow=warm red, deep=cold blue)
# Uses a 5-stop gradient: red → orange → yellow → cyan → blue
_CMAP_STOPS: List[Tuple[float, Tuple[float, float, float]]] = [
    (0.00, (0.85, 0.10, 0.10)),   # shallow – red
    (0.25, (0.95, 0.55, 0.10)),   # orange
    (0.50, (0.97, 0.90, 0.10)),   # yellow
    (0.75, (0.10, 0.80, 0.90)),   # cyan
    (1.00, (0.05, 0.10, 0.75)),   # deep – blue
]


def depth_to_rgb(normalised: float) -> Tuple[float, float, float]:
    """Map a [0..1] normalised depth value to an RGB triple."""
    t = max(0.0, min(1.0, normalised))
    for i in range(len(_CMAP_STOPS) - 1):
        t0, c0 = _CMAP_STOPS[i]
        t1, c1 = _CMAP_STOPS[i + 1]
        if t0 <= t <= t1:
            f = (t - t0) / (t1 - t0) if (t1 - t0) > 0 else 0.0
            return (
                c0[0] + f * (c1[0] - c0[0]),
                c0[1] + f * (c1[1] - c0[1]),
                c0[2] + f * (c1[2] - c0[2]),
            )
    return _CMAP_STOPS[-1][1]


# ─────────────────────────────────────────────────────────────────────────────
# Main widget
# ─────────────────────────────────────────────────────────────────────────────
class SeafloorMeshWidget(QOpenGLWidget):
    """
    3-D seafloor mesh rendered with OpenGL.

    Connect SeafloorMapper.sig_mesh_updated  →  on_mesh_updated(vertices, colors, triangles)

    If PyOpenGL is unavailable the widget shows a friendly "not available" label.
    """

    # ── Default camera parameters ────────────────────────────────────────────
    _CAM_AZIMUTH_DEF   =  45.0    # degrees around vertical
    _CAM_ELEVATION_DEF =  30.0    # degrees above horizon
    _CAM_DISTANCE_DEF  =  20.0    # metres from origin
    _CAM_DIST_MIN      =   1.0
    _CAM_DIST_MAX      = 200.0

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Expanding)
        self.setMinimumSize(400, 300)

        # ── Camera state ─────────────────────────────────────────────────────
        self._azimuth   = self._CAM_AZIMUTH_DEF
        self._elevation = self._CAM_ELEVATION_DEF
        self._distance  = self._CAM_DISTANCE_DEF
        self._pan_x     = 0.0
        self._pan_y     = 0.0

        # ── Mouse drag state ─────────────────────────────────────────────────
        self._last_mouse: Optional[QPoint] = None
        self._mouse_btn: Optional[Qt.MouseButton] = None

        # ── Mesh data ────────────────────────────────────────────────────────
        # vertices: List[(x, y, z)]  –  NED coordinates (z positive down)
        # colors  : List[(r, g, b)]  –  per-vertex RGB [0..1]
        # triangles: List[(i, j, k)] –  vertex index triples
        self._vertices:  List[Tuple[float, float, float]] = []
        self._colors:    List[Tuple[float, float, float]] = []
        self._triangles: List[Tuple[int, int, int]]       = []

        # ── ROV position ─────────────────────────────────────────────────────
        self._rov_x: float = 0.0
        self._rov_y: float = 0.0
        self._rov_z: float = 0.0
        self._show_rov: bool = False

        # ── Depth range (updated on mesh load) ───────────────────────────────
        self._depth_min: float = 0.0
        self._depth_max: float = 10.0

        # ── Fallback label (no OpenGL) ────────────────────────────────────────
        if not _OPENGL_AVAILABLE:
            self._setup_fallback()

    # ─────────────────────────────────────────────────────────────────────────
    # Fallback (no OpenGL)
    # ─────────────────────────────────────────────────────────────────────────
    def _setup_fallback(self):
        layout = QVBoxLayout(self)
        lbl = QLabel(
            "⚠  OpenGL not available\n\n"
            "Install PyOpenGL:\n"
            "    pip install PyOpenGL PyOpenGL_accelerate"
        )
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet(
            "background:#0d1117; color:#8b949e; font-size:14px;"
            "border:1px solid #30363d; border-radius:8px; padding:24px;"
        )
        layout.addWidget(lbl)

    # ─────────────────────────────────────────────────────────────────────────
    # QOpenGLWidget overrides
    # ─────────────────────────────────────────────────────────────────────────
    def initializeGL(self):
        if not _OPENGL_AVAILABLE:
            return
        # Background: dark navy  (0.05, 0.07, 0.12, 1.0)
        glClearColor(0.05, 0.07, 0.12, 1.0)
        glEnable(GL_DEPTH_TEST)
        glDepthFunc(GL_LESS)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glDisable(GL_LIGHTING)   # we handle colour manually per vertex

    def resizeGL(self, w: int, h: int):
        if not _OPENGL_AVAILABLE:
            return
        glViewport(0, 0, w, h)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        aspect = w / max(h, 1)
        gluPerspective(45.0, aspect, 0.1, 2000.0)
        glMatrixMode(GL_MODELVIEW)

    def paintGL(self):
        if not _OPENGL_AVAILABLE:
            return
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()

        # ── Apply camera transform ────────────────────────────────────────────
        self._apply_camera()

        # ── Scene objects ─────────────────────────────────────────────────────
        self._draw_axes()
        self._draw_grid()
        if self._triangles:
            self._draw_mesh()
        if self._show_rov:
            self._draw_rov_position(self._rov_x, self._rov_y, self._rov_z)

    # Overlay legend is drawn via QPainter after OpenGL paint
    def paintEvent(self, event):
        super().paintEvent(event)
        if not _OPENGL_AVAILABLE:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._draw_legend(painter)
        self._draw_scale_bar(painter)
        painter.end()

    # ─────────────────────────────────────────────────────────────────────────
    # Camera
    # ─────────────────────────────────────────────────────────────────────────
    def _apply_camera(self):
        """Set up the model-view matrix from orbit camera parameters."""
        az  = math.radians(self._azimuth)
        el  = math.radians(self._elevation)
        d   = self._distance

        eye_x = d * math.cos(el) * math.sin(az) + self._pan_x
        eye_y = d * math.cos(el) * math.cos(az) + self._pan_y
        eye_z = d * math.sin(el)                             # Z-up for camera

        gluLookAt(
            eye_x, eye_y, -eye_z,   # eye  (negate Z for NED scene where Z=down)
            self._pan_x, self._pan_y, 0.0,   # centre (scene origin)
            0.0, 0.0, -1.0          # up vector (camera Z-up)
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Drawing routines
    # ─────────────────────────────────────────────────────────────────────────
    def _draw_mesh(self):
        """Render GL_TRIANGLES with per-vertex colour."""
        glBegin(GL_TRIANGLES)
        for tri in self._triangles:
            for idx in tri:
                if idx < len(self._colors):
                    r, g, b = self._colors[idx]
                    glColor3f(r, g, b)
                if idx < len(self._vertices):
                    x, y, z = self._vertices[idx]
                    glVertex3f(x, y, z)
        glEnd()

    def _draw_grid(self):
        """Draw a wireframe reference grid on the Z=0 plane (sea surface)."""
        size  = 20.0     # metres each side
        step  =  2.0     # grid spacing

        glLineWidth(0.5)
        glColor4f(0.2, 0.5, 0.8, 0.25)   # translucent blue
        glBegin(GL_LINES)

        n = int(size / step)
        for i in range(-n, n + 1):
            s = i * step
            # Lines parallel to Y axis
            glVertex3f(s, -size, 0.0)
            glVertex3f(s,  size, 0.0)
            # Lines parallel to X axis
            glVertex3f(-size, s, 0.0)
            glVertex3f( size, s, 0.0)

        glEnd()
        glLineWidth(1.0)

    def _draw_axes(self):
        """Draw XYZ axes with labels (X=North, Y=East, Z=Down)."""
        L = 5.0
        glLineWidth(2.0)

        glBegin(GL_LINES)
        # X – North – green
        glColor3f(0.2, 0.9, 0.2)
        glVertex3f(0, 0, 0); glVertex3f(L, 0, 0)
        # Y – East – red
        glColor3f(0.9, 0.2, 0.2)
        glVertex3f(0, 0, 0); glVertex3f(0, L, 0)
        # Z – Down – blue (rendered as negative Z for camera)
        glColor3f(0.2, 0.4, 0.9)
        glVertex3f(0, 0, 0); glVertex3f(0, 0, L)
        glEnd()

        glLineWidth(1.0)

    def _draw_rov_position(self, x: float, y: float, z: float):
        """Draw a small cross/diamond marker at the ROV position."""
        r = 0.4   # marker radius

        glLineWidth(3.0)
        glColor3f(1.0, 0.9, 0.0)   # bright yellow

        glBegin(GL_LINES)
        # Horizontal cross
        glVertex3f(x - r, y, z); glVertex3f(x + r, y, z)
        glVertex3f(x, y - r, z); glVertex3f(x, y + r, z)
        # Vertical spike
        glVertex3f(x, y, z - r); glVertex3f(x, y, z + r)
        glEnd()

        # Outer diamond ring (in XY plane at ROV depth)
        glBegin(GL_LINE_LOOP)
        segs = 16
        for i in range(segs):
            a = 2 * math.pi * i / segs
            glVertex3f(x + r * 1.5 * math.cos(a),
                       y + r * 1.5 * math.sin(a),
                       z)
        glEnd()

        glLineWidth(1.0)

    # ─────────────────────────────────────────────────────────────────────────
    # 2-D overlay (QPainter)
    # ─────────────────────────────────────────────────────────────────────────
    def _draw_legend(self, painter: QPainter):
        """Draw the colour-bar depth legend on the right side."""
        W   = self.width()
        H   = self.height()
        bw  = 16    # bar width
        bh  = min(200, H - 80)
        bx  = W - 50
        by  = (H - bh) // 2

        # Gradient bar
        grad = QLinearGradient(bx, by, bx, by + bh)
        # Top = shallow (warm), bottom = deep (cold)
        stops = [
            (0.00, QColor(217,  25,  25)),
            (0.25, QColor(242, 140,  25)),
            (0.50, QColor(247, 230,  25)),
            (0.75, QColor(25,  204, 230)),
            (1.00, QColor(12,   25, 191)),
        ]
        for pos, colour in stops:
            grad.setColorAt(pos, colour)

        painter.fillRect(QRect(bx, by, bw, bh), grad)

        # Border
        painter.setPen(QColor(48, 54, 61))
        painter.drawRect(QRect(bx, by, bw, bh))

        # Labels
        font = QFont("Segoe UI", 8)
        painter.setFont(font)
        painter.setPen(QColor(139, 148, 158))
        painter.drawText(bx - 2, by + 4,           f"{self._depth_min:.0f} m")
        painter.drawText(bx - 2, by + bh // 2 + 4, f"{(self._depth_min + self._depth_max)/2:.0f} m")
        painter.drawText(bx - 2, by + bh - 2,      f"{self._depth_max:.0f} m")

        # Title
        painter.setPen(QColor(230, 237, 243))
        painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        painter.drawText(bx - 4, by - 8, "Depth")

    def _draw_scale_bar(self, painter: QPainter):
        """Draw a simple horizontal scale bar at the bottom-left."""
        W = self.width()
        H = self.height()

        # Estimate scene width in metres visible at current distance
        # Very rough: field ~= distance * 2 * tan(22.5°)
        scene_width = self._distance * 2 * math.tan(math.radians(22.5))
        # Choose a round scale
        raw = scene_width * 0.25   # ~quarter of view
        mag = 10 ** math.floor(math.log10(max(raw, 0.01)))
        scale_m = round(raw / mag) * mag
        px_per_m = (W * 0.25) / max(scene_width, 0.01)
        bar_px = int(scale_m * px_per_m)
        bar_px = max(20, min(bar_px, 200))

        bx = 20
        by = H - 30
        bh = 4

        painter.fillRect(QRect(bx, by, bar_px, bh), QColor(139, 148, 158))
        # Endcaps
        painter.fillRect(QRect(bx, by - 4, 2, bh + 8), QColor(139, 148, 158))
        painter.fillRect(QRect(bx + bar_px - 2, by - 4, 2, bh + 8), QColor(139, 148, 158))

        painter.setPen(QColor(230, 237, 243))
        painter.setFont(QFont("Segoe UI", 9))
        label = f"{scale_m:.0f} m" if scale_m >= 1 else f"{scale_m*100:.0f} cm"
        painter.drawText(bx, by - 6, label)

    # ─────────────────────────────────────────────────────────────────────────
    # Mouse event handlers – orbit camera
    # ─────────────────────────────────────────────────────────────────────────
    def mousePressEvent(self, event: QMouseEvent):
        self._last_mouse = event.pos()
        self._mouse_btn  = event.button()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._last_mouse is None:
            return
        dx = event.pos().x() - self._last_mouse.x()
        dy = event.pos().y() - self._last_mouse.y()
        self._last_mouse = event.pos()

        if self._mouse_btn == Qt.MouseButton.LeftButton:
            # Orbit
            self._azimuth   = (self._azimuth   + dx * 0.5) % 360.0
            self._elevation = max(-89.0, min(89.0, self._elevation + dy * 0.3))

        elif self._mouse_btn == Qt.MouseButton.MiddleButton:
            # Pan (crude, not scale-corrected)
            scale = self._distance * 0.002
            self._pan_x -= dx * scale
            self._pan_y -= dy * scale

        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._last_mouse = None
        self._mouse_btn  = None

    def wheelEvent(self, event: QWheelEvent):
        delta = event.angleDelta().y()
        factor = 0.9 if delta > 0 else 1.1
        self._distance = max(self._CAM_DIST_MIN,
                             min(self._CAM_DIST_MAX, self._distance * factor))
        self.update()

    # ─────────────────────────────────────────────────────────────────────────
    # Public API / slots
    # ─────────────────────────────────────────────────────────────────────────
    def on_mesh_updated(
        self,
        vertices:  List[Tuple[float, float, float]],
        colors:    List[Tuple[float, float, float]],
        triangles: List[Tuple[int, int, int]],
    ):
        """
        Slot – receive new mesh data.

        vertices  : list of (x, y, z) NED positions (z positive = down)
        colors    : list of (r, g, b) per vertex [0..1]
        triangles : list of (i, j, k) index triples
        """
        self._vertices  = vertices
        self._colors    = colors
        self._triangles = triangles

        # Update depth range from Z values
        if vertices:
            zs = [v[2] for v in vertices]
            self._depth_min = min(zs)
            self._depth_max = max(zs)

        self.update()

    def on_mesh_updated_from_depths(
        self,
        vertices: List[Tuple[float, float, float]],
        triangles: List[Tuple[int, int, int]],
    ):
        """
        Convenience overload: auto-generate colours from Z depth.
        Calls on_mesh_updated() internally.
        """
        if not vertices:
            self.on_mesh_updated([], [], [])
            return

        zs = [v[2] for v in vertices]
        z_min, z_max = min(zs), max(zs)
        span = z_max - z_min or 1.0

        colors = [depth_to_rgb((z - z_min) / span) for _, _, z in vertices]
        self.on_mesh_updated(vertices, colors, triangles)

    def set_rov_position(self, x: float, y: float, z: float):
        """Update ROV marker position and trigger a repaint."""
        self._rov_x = x
        self._rov_y = y
        self._rov_z = z
        self._show_rov = True
        self.update()

    def reset_camera(self):
        """Reset camera to default orbit position."""
        self._azimuth   = self._CAM_AZIMUTH_DEF
        self._elevation = self._CAM_ELEVATION_DEF
        self._distance  = self._CAM_DISTANCE_DEF
        self._pan_x     = 0.0
        self._pan_y     = 0.0
        self.update()

    def export_png(self, filename: str) -> bool:
        """
        Save the current framebuffer to a PNG file.

        Returns True on success, False on failure.
        """
        if not _OPENGL_AVAILABLE:
            return False
        fb = self.grabFramebuffer()
        if fb is None:
            return False
        return fb.save(filename, "PNG")

    # ─────────────────────────────────────────────────────────────────────────
    # Size hint
    # ─────────────────────────────────────────────────────────────────────────
    def sizeHint(self) -> QSize:
        return QSize(640, 480)


# ─────────────────────────────────────────────────────────────────────────────
# Quick standalone test
# ─────────────────────────────────────────────────────────────────────────────
def _generate_demo_mesh(
    rows: int = 30, cols: int = 30, scale: float = 15.0
) -> Tuple[
    List[Tuple[float, float, float]],
    List[Tuple[float, float, float]],
    List[Tuple[int, int, int]],
]:
    """Generate a sine-wave seabed surface for demo purposes."""
    import math

    vertices  = []
    colors    = []
    triangles = []

    for r in range(rows):
        for c in range(cols):
            x = (c / (cols - 1) - 0.5) * scale
            y = (r / (rows - 1) - 0.5) * scale
            # Depth: combination of two sine waves (positive = deeper)
            z = (
                3.0 * math.sin(x * 0.4)
                + 2.0 * math.cos(y * 0.5)
                + 0.5 * math.sin(x * 0.9 + y * 0.6)
                + 5.0
            )
            vertices.append((x, y, z))

    z_vals = [v[2] for v in vertices]
    z_min, z_max = min(z_vals), max(z_vals)
    span = z_max - z_min or 1.0
    colors = [depth_to_rgb((z - z_min) / span) for _, _, z in vertices]

    for r in range(rows - 1):
        for c in range(cols - 1):
            tl = r * cols + c
            tr = tl + 1
            bl = tl + cols
            br = bl + 1
            triangles.append((tl, bl, tr))
            triangles.append((tr, bl, br))

    return vertices, colors, triangles


if __name__ == "__main__":
    import sys
    from PyQt6.QtWidgets import QApplication, QMainWindow, QToolBar, QPushButton

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    win = QMainWindow()
    win.setWindowTitle("SeafloorMeshWidget – Demo")
    win.resize(900, 650)

    widget = SeafloorMeshWidget()
    win.setCentralWidget(widget)

    # Toolbar with demo controls
    tb = QToolBar("Controls")
    win.addToolBar(tb)

    def load_demo():
        v, c, t = _generate_demo_mesh(40, 40)
        widget.on_mesh_updated(v, c, t)
        widget.set_rov_position(0, 0, 5.0)

    def reset_cam():
        widget.reset_camera()

    def do_export():
        widget.export_png("seafloor_export.png")
        print("Exported: seafloor_export.png")

    tb.addAction("Load Demo Mesh", load_demo)
    tb.addAction("Reset Camera",   reset_cam)
    tb.addAction("Export PNG",     do_export)

    win.show()
    load_demo()
    sys.exit(app.exec())
