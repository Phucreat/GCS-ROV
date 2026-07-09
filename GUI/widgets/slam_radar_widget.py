"""
slam_radar_widget.py - 2D SLAM Radar / Mini-map Widget
=======================================================
Widget vẽ bản đồ SLAM 2D theo tư thế ROV.
Nhúng vào frm_simulate_view_bottom (dưới compass trong guirov.py).

Thiết kế:
  - Nền: Polar grid (vòng tròn đồng tâm) — màu navy dark
  - Trung tâm: Biểu tượng tàu (hình tam giác) xoay theo Yaw
  - Điểm SLAM: Màu đỏ (gần) → Vàng → Xanh (xa)
  - FOV cone: Vệt sáng cyan mờ trước mũi tàu
  - Depth bar: Thanh hiển thị độ sâu bên trái
  - Heading: Vòng tròn la bàn bên ngoài
"""
import math
import numpy as np
from PyQt6 import QtCore, QtGui, QtWidgets


class SLAMRadarWidget(QtWidgets.QWidget):
    """
    2D SLAM Radar / Compass Mini-map.
    
    Cách dùng:
        self.slam_radar = SLAMRadarWidget(parent=self.frm_simulate_view_bottom)
        # Mỗi frame:
        self.slam_radar.set_attitude(roll_deg, pitch_deg, yaw_deg)
        self.slam_radar.set_depth(depth_m)
        self.slam_radar.set_slam_points(pts_array_Nx3)
    """

    # --- Màu sắc ---
    COLOR_BG         = QtGui.QColor(6, 11, 20)         # #060B14
    COLOR_GRID       = QtGui.QColor(23, 59, 102, 90)   # navy grid
    COLOR_GRID_LABEL = QtGui.QColor(50, 100, 170, 200)
    COLOR_ROV_FILL   = QtGui.QColor(0, 168, 255, 220)  # #00A8FF
    COLOR_ROV_EDGE   = QtGui.QColor(255, 255, 255, 220)
    COLOR_FOV        = QtGui.QColor(0, 200, 255, 35)
    COLOR_COMPASS    = QtGui.QColor(0, 168, 255, 180)
    COLOR_COMPASS_N  = QtGui.QColor(255, 70, 70, 255)  # Bắc = đỏ
    COLOR_DEPTH_BG   = QtGui.QColor(13, 23, 38, 180)
    COLOR_DEPTH_FG   = QtGui.QColor(0, 255, 102, 220)

    # --- Thông số radar ---
    RADAR_RINGS      = 4          # Số vòng tròn
    FOV_ANGLE_DEG    = 90.0       # Góc FOV camera

    def __init__(self, parent=None, range_m: float = 5.0):
        super().__init__(parent)
        self.range_m     = range_m  # Bán kính hiển thị (m)
        self._yaw_deg    = 0.0
        self._pitch_deg  = 0.0
        self._roll_deg   = 0.0
        self._depth_m    = 0.0
        self._max_depth  = 50.0     # m
        self._slam_pts   = None     # ndarray (N, 3) — tọa độ relative
        self._heading    = 0.0      # Heading la bàn (0-360°)

        self.setMinimumSize(200, 200)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding
        )

    # --------------------------------------------------------
    # API CẬP NHẬT DỮ LIỆU
    # --------------------------------------------------------
    def set_attitude(self, roll: float, pitch: float, yaw: float):
        """roll, pitch, yaw tính bằng độ."""
        self._roll_deg  = roll
        self._pitch_deg = pitch
        self._yaw_deg   = yaw
        self._heading   = yaw % 360.0
        self.update()

    def set_depth(self, depth_m: float):
        """Độ sâu (dương)."""
        self._depth_m = abs(depth_m)
        self.update()

    def set_slam_points(self, pts: np.ndarray):
        """
        pts: ndarray (N, 3) — tọa độ relative X(Forward), Y(Left), Z(Up)
        Chỉ hiển thị các điểm trong bán kính range_m.
        """
        self._slam_pts = pts
        self.update()

    def set_range(self, range_m: float):
        """Đổi bán kính hiển thị."""
        self.range_m = max(1.0, range_m)
        self.update()

    # --------------------------------------------------------
    # VẼ
    # --------------------------------------------------------
    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        sz = min(w, h)

        # --- Nền ---
        painter.fillRect(0, 0, w, h, self.COLOR_BG)

        # --- Vùng radar (hình tròn căn giữa) ---
        cx, cy = w // 2, h // 2
        r_radar = int(sz * 0.38)

        # Căn sang phải 1 chút để lấy chỗ cho depth bar bên trái
        cx = int(w * 0.52)

        # Clip vào vòng tròn radar
        clip_path = QtGui.QPainterPath()
        clip_path.addEllipse(cx - r_radar, cy - r_radar, r_radar*2, r_radar*2)

        # Nền radar
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(QtGui.QColor(6, 15, 30, 200))
        painter.drawEllipse(cx - r_radar, cy - r_radar, r_radar*2, r_radar*2)

        # Polar grid
        painter.setClipPath(clip_path)
        self._draw_grid(painter, cx, cy, r_radar)

        # SLAM points
        if self._slam_pts is not None and len(self._slam_pts) > 0:
            self._draw_slam_points(painter, cx, cy, r_radar)

        # FOV cone
        self._draw_fov(painter, cx, cy, r_radar)

        # Reset clip
        painter.setClipping(False)

        # Vòng tròn la bàn ngoài
        self._draw_compass_ring(painter, cx, cy, r_radar)

        # Biểu tượng ROV tại trung tâm
        self._draw_rov_icon(painter, cx, cy, r_radar)

        # Depth bar bên trái
        self._draw_depth_bar(painter, int(w * 0.08), cy, r_radar)

        # Attitude info góc dưới
        self._draw_attitude_text(painter, w, h)

        painter.end()

    def _draw_grid(self, p, cx, cy, r):
        """Vẽ lưới cực (vòng tròn + đường kẻ)."""
        pen = QtGui.QPen(self.COLOR_GRID, 1)
        p.setPen(pen)
        for i in range(1, self.RADAR_RINGS + 1):
            ri = int(r * i / self.RADAR_RINGS)
            p.drawEllipse(cx - ri, cy - ri, ri*2, ri*2)
            # Label khoảng cách
            dist_label = f"{self.range_m * i / self.RADAR_RINGS:.1f}m"
            p.setPen(self.COLOR_GRID_LABEL)
            p.setFont(QtGui.QFont("Rajdhani", 7))
            p.drawText(cx + ri + 2, cy - 2, dist_label)
            p.setPen(pen)
        # Đường chéo
        for a in range(0, 360, 45):
            rad = math.radians(a)
            p.drawLine(
                int(cx + r*math.cos(rad)), int(cy + r*math.sin(rad)),
                int(cx - r*math.cos(rad)), int(cy - r*math.sin(rad))
            )

    def _draw_slam_points(self, p, cx, cy, r):
        """Vẽ điểm SLAM, tô màu theo khoảng cách."""
        pts = self._slam_pts
        dists = np.linalg.norm(pts[:, :2], axis=1)
        max_d = max(self.range_m, 0.1)
        for i, pt in enumerate(pts):
            if dists[i] > self.range_m:
                continue
            # Chuyển tọa độ body → screen (X=Forward=Up, Y=Left)
            yaw_r = math.radians(-self._yaw_deg)
            rx =  pt[0] * math.cos(yaw_r) - pt[1] * math.sin(yaw_r)
            ry =  pt[0] * math.sin(yaw_r) + pt[1] * math.cos(yaw_r)
            sx = cx + int(rx / self.range_m * r)
            sy = cy - int(ry / self.range_m * r)   # Y lên = - trên screen
            t = min(dists[i] / max_d, 1.0)
            # gần → đỏ, xa → xanh
            qc = QtGui.QColor(
                int(255 * (1 - t)),
                int(255 * min(t * 1.5, 1)),
                int(100 * t),
                200
            )
            p.setPen(QtCore.Qt.PenStyle.NoPen)
            p.setBrush(qc)
            p.drawEllipse(sx - 2, sy - 2, 4, 4)

    def _draw_fov(self, p, cx, cy, r):
        """Vẽ vệt sáng FOV trước mũi tàu."""
        half = math.radians(self.FOV_ANGLE_DEG / 2)
        # Mũi tàu luôn hướng lên trên màn hình (−π/2)
        base_angle = -math.pi / 2
        grad = QtGui.QRadialGradient(cx, cy, r)
        grad.setColorAt(0.0, self.COLOR_FOV)
        grad.setColorAt(1.0, QtGui.QColor(0, 200, 255, 0))
        path = QtGui.QPainterPath()
        path.moveTo(cx, cy)
        # Vẽ cung quạt
        rect = QtCore.QRectF(cx - r, cy - r, r*2, r*2)
        start_deg = math.degrees(base_angle - half)
        span_deg  = self.FOV_ANGLE_DEG
        path.arcTo(rect, -start_deg, -span_deg)
        path.closeSubpath()
        p.setPen(QtCore.Qt.PenStyle.NoPen)
        p.setBrush(QtGui.QBrush(grad))
        p.drawPath(path)

    def _draw_compass_ring(self, p, cx, cy, r):
        """Vẽ vòng tròn la bàn và hướng la bàn."""
        r_out = r + 18
        pen_ring = QtGui.QPen(self.COLOR_COMPASS, 1)
        p.setPen(pen_ring)
        p.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        p.drawEllipse(cx - r_out, cy - r_out, r_out*2, r_out*2)

        # Cardinal points
        cardinals = {"N": 0, "E": 90, "S": 180, "W": 270}
        for label, deg in cardinals.items():
            a = math.radians(deg - 90)   # 0° = Bắc = trên
            px = cx + int((r_out + 10) * math.cos(a))
            py = cy + int((r_out + 10) * math.sin(a))
            color = self.COLOR_COMPASS_N if label == "N" else self.COLOR_COMPASS
            p.setPen(color)
            p.setFont(QtGui.QFont("Rajdhani", 8, QtGui.QFont.Weight.Bold))
            p.drawText(px - 5, py + 4, label)

        # Kim la bàn (heading)
        h_rad = math.radians(self._heading - 90)
        tip_x = cx + int(r * 0.55 * math.cos(h_rad))
        tip_y = cy + int(r * 0.55 * math.sin(h_rad))
        tail_x = cx - int(r * 0.25 * math.cos(h_rad))
        tail_y = cy - int(r * 0.25 * math.sin(h_rad))
        p.setPen(QtGui.QPen(self.COLOR_COMPASS_N, 2))
        p.drawLine(tail_x, tail_y, tip_x, tip_y)
        # Giá trị heading
        p.setPen(self.COLOR_COMPASS)
        p.setFont(QtGui.QFont("Rajdhani", 9, QtGui.QFont.Weight.Bold))
        p.drawText(cx - 22, cy + r + 30, f"HDG: {self._heading:05.1f}°")

    def _draw_rov_icon(self, p, cx, cy, r):
        """Vẽ biểu tượng ROV (hình tam giác nhỏ) tại trung tâm."""
        sz = int(r * 0.14)
        points = [
            QtCore.QPointF(0,    -sz * 1.6),    # mũi
            QtCore.QPointF(-sz,   sz),           # trái đuôi
            QtCore.QPointF(+sz,   sz),           # phải đuôi
        ]
        poly = QtGui.QPolygonF(points)
        p.save()
        p.translate(cx, cy)
        # ROV luôn hướng lên trên màn hình (không xoay theo yaw)
        p.setPen(QtGui.QPen(self.COLOR_ROV_EDGE, 1.5))
        p.setBrush(self.COLOR_ROV_FILL)
        p.drawPolygon(poly)
        p.restore()

    def _draw_depth_bar(self, p, bx, cy, r):
        """Thanh đo độ sâu dọc bên trái."""
        bh = r * 2
        bw = 14
        by = cy - r
        # Khung
        p.setPen(QtGui.QPen(QtGui.QColor(30, 60, 100), 1))
        p.setBrush(self.COLOR_DEPTH_BG)
        p.drawRoundedRect(int(bx - bw//2), int(by), bw, int(bh), 3, 3)
        # Thanh fill (% độ sâu)
        pct = min(self._depth_m / self._max_depth, 1.0)
        fill_h = int(bh * pct)
        p.setPen(QtCore.Qt.PenStyle.NoPen)
        p.setBrush(self.COLOR_DEPTH_FG)
        p.drawRoundedRect(
            int(bx - bw//2 + 2),
            int(by + bh - fill_h),
            bw - 4, fill_h, 2, 2
        )
        # Nhãn
        p.setPen(QtGui.QColor(200, 220, 240))
        p.setFont(QtGui.QFont("Rajdhani", 8, QtGui.QFont.Weight.Bold))
        p.drawText(int(bx - 22), int(by - 4), f"{self._depth_m:.1f}m")
        p.drawText(int(bx - 8), int(by + bh + 14), "▼")

    def _draw_attitude_text(self, p, w, h):
        """Hiển thị R/P/Y số bên dưới widget."""
        p.setPen(QtGui.QColor(90, 140, 190))
        p.setFont(QtGui.QFont("Rajdhani", 8))
        text = (f"R:{self._roll_deg:+6.1f}°  "
                f"P:{self._pitch_deg:+6.1f}°  "
                f"Y:{self._yaw_deg:+7.1f}°")
        p.drawText(10, h - 6, text)
