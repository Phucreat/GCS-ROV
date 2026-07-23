"""
ar_hud_widget.py - Augmented Reality HUD Overlay Widget
=======================================================
Ve du lieu telemetry tren luong video thuc te bang OpenCV.
Hot tro:
  - Artificial horizon (roll ladder + pitch lines)
  - Depth tape (thuoc cuon ben phai)
  - Heading tape (thuoc cuon ben tren)
  - Battery + signal corners
  - Speed vector indicator
  - Warning flash overlay
  - Crosshair + target lock indicator
  - Detection boxes tu AI (neu co)

Kien truc:
  VideoReceiver.sig_frame → ARHUDWidget.set_frame()
  ARHUDWidget ve HUD len frame bang OpenCV
  ARHUDWidget hien thi qua QLabel.setPixmap()
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QSizePolicy

# ---------------------------------------------------------------------------
# Lazy OpenCV import helper
# ---------------------------------------------------------------------------
_cv2_available: Optional[bool] = None


def _get_cv2():
    """Lazy-import cv2 and cache the result. Returns module or None."""
    global _cv2_available
    if _cv2_available is None:
        try:
            import cv2 as _cv2  # noqa: F401
            _cv2_available = True
        except ImportError:
            _cv2_available = False
    if _cv2_available:
        import cv2
        return cv2
    return None


# ---------------------------------------------------------------------------
# Detection dataclass
# ---------------------------------------------------------------------------
@dataclass
class Detection:
    """Represents a single AI detection result."""
    class_name: str          # e.g. "diver", "pipe", "debris"
    conf: float              # 0.0 – 1.0 confidence
    x1: int                  # bounding box top-left x
    y1: int                  # bounding box top-left y
    x2: int                  # bounding box bottom-right x
    y2: int                  # bounding box bottom-right y
    track_id: int = -1       # -1 means not tracked
    # Computed after __init__ — normalized center (0-1) relative to frame
    center_x: float = field(default=0.0, init=False)
    center_y: float = field(default=0.0, init=False)
    # Frame dimensions used for normalisation (set by ARHUDWidget)
    _frame_w: int = field(default=640, init=False, repr=False)
    _frame_h: int = field(default=480, init=False, repr=False)

    def __post_init__(self):
        # Mid-point in pixel space; normalise assuming default 640×480.
        # ARHUDWidget calls _update_detection_centers() after receiving frame.
        mid_x = (self.x1 + self.x2) / 2.0
        mid_y = (self.y1 + self.y2) / 2.0
        self.center_x = mid_x / max(self._frame_w, 1)
        self.center_y = mid_y / max(self._frame_h, 1)

    def update_frame_size(self, w: int, h: int):
        """Re-compute normalised centres after frame dimensions are known."""
        self._frame_w = w
        self._frame_h = h
        self.__post_init__()


# ---------------------------------------------------------------------------
# Color palette  (BGR convention for OpenCV)
# ---------------------------------------------------------------------------
class _C:
    WHITE        = (255, 255, 255)
    BLACK        = (0,   0,   0)
    GREEN        = (0,   255, 100)
    LIME         = (0,   255, 0)
    YELLOW       = (0,   220, 255)
    ORANGE       = (0,   165, 255)
    RED          = (0,   50,  220)
    RED_BRIGHT   = (40,  40,  230)
    CYAN         = (255, 230, 0)
    BLUE_SKY     = (255, 180, 100)
    BROWN        = (30,  80,  140)   # earth/water color
    DARK_PANEL   = (10,  10,  10)
    SEMI_BLACK   = (20,  20,  20)
    GRAY         = (160, 160, 160)
    DARK_GRAY    = (60,  60,  60)
    HEADING_N    = (60,  60,  220)   # Red → North
    HEADING_S    = (220, 180, 60)    # Blue → South
    HEADING_E    = (60,  200, 60)    # Green → East
    HEADING_W    = (60,  200, 220)   # Yellow → West

    # Detection class colors
    DIVER        = (60,  200, 60)    # green
    PIPE         = (0,   200, 240)   # yellow
    DEBRIS       = (40,  40,  220)   # red

    @staticmethod
    def detection_color(class_name: str):
        lc = class_name.lower()
        if "diver" in lc:
            return _C.DIVER
        if "pipe" in lc:
            return _C.PIPE
        return _C.DEBRIS


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------
def _draw_text_with_bg(
    img: np.ndarray,
    text: str,
    pos,  # (x, y) bottom-left of text
    font,
    scale: float,
    color,
    thickness: int = 1,
    bg_color=None,
    padding: int = 3,
    alpha: float = 0.6,
):
    """Draw text with optional semi-transparent background."""
    cv2 = _get_cv2()
    if cv2 is None:
        return

    (tw, th), baseline = cv2.getTextSize(text, font, scale, thickness)
    x, y = int(pos[0]), int(pos[1])

    if bg_color is not None:
        x0 = x - padding
        y0 = y - th - padding
        x1 = x + tw + padding
        y1 = y + baseline + padding

        h, w = img.shape[:2]
        x0c, y0c = max(0, x0), max(0, y0)
        x1c, y1c = min(w, x1), min(h, y1)
        if x1c > x0c and y1c > y0c:
            roi = img[y0c:y1c, x0c:x1c]
            overlay = roi.copy()
            overlay[:] = bg_color
            cv2.addWeighted(overlay, alpha, roi, 1 - alpha, 0, roi)
            img[y0c:y1c, x0c:x1c] = roi

    cv2.putText(img, text, (x, y), font, scale, color, thickness, cv2.LINE_AA)


def _overlay_alpha(img: np.ndarray, overlay: np.ndarray, alpha: float):
    """Blend overlay onto img in-place."""
    cv2 = _get_cv2()
    if cv2 is None:
        return
    cv2.addWeighted(overlay, alpha, img, 1.0 - alpha, 0, img)


def _draw_rounded_rect(img, pt1, pt2, color, radius=6, thickness=1):
    """Draw a rectangle with rounded corners using OpenCV."""
    cv2 = _get_cv2()
    if cv2 is None:
        return
    x1, y1 = pt1
    x2, y2 = pt2
    r = min(radius, (x2 - x1) // 2, (y2 - y1) // 2)
    # Sides
    cv2.line(img, (x1 + r, y1), (x2 - r, y1), color, thickness)
    cv2.line(img, (x1 + r, y2), (x2 - r, y2), color, thickness)
    cv2.line(img, (x1, y1 + r), (x1, y2 - r), color, thickness)
    cv2.line(img, (x2, y1 + r), (x2, y2 - r), color, thickness)
    # Corners
    cv2.ellipse(img, (x1 + r, y1 + r), (r, r), 180, 0, 90, color, thickness)
    cv2.ellipse(img, (x2 - r, y1 + r), (r, r), 270, 0, 90, color, thickness)
    cv2.ellipse(img, (x1 + r, y2 - r), (r, r), 90, 0, 90, color, thickness)
    cv2.ellipse(img, (x2 - r, y2 - r), (r, r), 0, 0, 90, color, thickness)


# ---------------------------------------------------------------------------
# Main Widget
# ---------------------------------------------------------------------------
class ARHUDWidget(QWidget):
    """
    Augmented Reality HUD overlay drawn on top of video frames using OpenCV.

    Signals flow:
        VideoReceiver.sig_frame  →  self.set_frame(frame)
        Telemetry source         →  self.update_telemetry(...)
        AI pipeline              →  self.set_detections(detections)
    """

    # Telemetry defaults
    _TELEM_DEFAULTS = dict(
        roll=0.0, pitch=0.0, yaw=0.0,
        depth=0.0, heading=0.0, speed=0.0,
        voltage=0.0, current=0.0, pct=0.0,
        signal_pct=0.0, mode="MANUAL", armed=False,
    )

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        # --- Telemetry state ---
        self._roll: float = 0.0       # degrees
        self._pitch: float = 0.0      # degrees
        self._yaw: float = 0.0        # degrees
        self._depth: float = 0.0      # metres
        self._heading: float = 0.0    # degrees 0-360
        self._speed: float = 0.0      # m/s
        self._voltage: float = 0.0    # V
        self._current: float = 0.0    # A
        self._pct: float = 0.0        # battery %
        self._signal_pct: float = 0.0 # link %
        self._mode: str = "MANUAL"
        self._armed: bool = False

        # --- AI detections ---
        self._detections: List[Detection] = []

        # --- Warning state ---
        self._warning_msg: str = ""
        self._warning_level: str = ""   # "warn" | "critical" | ""
        self._warning_until: float = 0.0

        # --- HUD toggle ---
        self._hud_enabled: bool = True

        # --- Last frame (BGR numpy array) ---
        self._last_frame: Optional[np.ndarray] = None

        # --- Build UI ---
        self._build_ui()

    # ------------------------------------------------------------------
    # UI Setup
    # ------------------------------------------------------------------
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # Primary video display label
        self._video_label = QLabel(self)
        self._video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._video_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._video_label.setStyleSheet(
            "background-color: #0a0a0a;"
            "border: 1px solid #1e3a4a;"
        )
        self._video_label.setMinimumSize(320, 240)
        layout.addWidget(self._video_label, stretch=1)

        # Secondary info bar below video (AI summary)
        self._info_label = QLabel("AI: No detections", self)
        self._info_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._info_label.setFixedHeight(22)
        self._info_label.setStyleSheet(
            "background-color: #0d1b22;"
            "color: #7ecfff;"
            "font-family: 'Consolas', monospace;"
            "font-size: 11px;"
            "padding-left: 6px;"
            "border-top: 1px solid #1e3a4a;"
        )
        layout.addWidget(self._info_label, stretch=0)

        self.setLayout(layout)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def set_frame(self, frame: np.ndarray):
        """
        Receive a BGR frame from the video receiver.
        Draws HUD overlay and displays via QPixmap.
        Thread-safe: must be called from main thread (Qt slot).
        """
        if frame is None or frame.size == 0:
            return

        # Work on a copy so we don't mutate source
        frame_copy = frame.copy()
        self._last_frame = frame_copy

        if self._hud_enabled:
            rendered = self._draw_hud(frame_copy)
        else:
            rendered = frame_copy

        self._display_frame(rendered)
        self._update_info_bar()

    def update_telemetry(
        self,
        roll: float = 0.0,
        pitch: float = 0.0,
        yaw: float = 0.0,
        depth: float = 0.0,
        heading: float = 0.0,
        speed: float = 0.0,
        voltage: float = 0.0,
        current: float = 0.0,
        pct: float = 0.0,
        signal_pct: float = 0.0,
        mode: str = "MANUAL",
        armed: bool = False,
    ):
        """Update all telemetry values (call from telemetry thread via signal)."""
        self._roll = float(roll)
        self._pitch = float(pitch)
        self._yaw = float(yaw)
        self._depth = float(depth)
        self._heading = float(heading) % 360.0
        self._speed = float(speed)
        self._voltage = float(voltage)
        self._current = float(current)
        self._pct = max(0.0, min(100.0, float(pct)))
        self._signal_pct = max(0.0, min(100.0, float(signal_pct)))
        self._mode = str(mode).upper()
        self._armed = bool(armed)

    def set_detections(self, detections: List[Detection]):
        """Update AI detection list. Pass empty list to clear."""
        self._detections = list(detections) if detections else []

    def set_warning(self, message: str, level: str = "warn", duration: float = 5.0):
        """
        Display a warning overlay.

        Args:
            message:  Text to display
            level:    "warn" (yellow border blink) or "critical" (red fill)
            duration: Seconds to show the warning (0 = indefinite until cleared)
        """
        self._warning_msg = str(message)
        self._warning_level = str(level).lower()
        self._warning_until = (time.monotonic() + duration) if duration > 0 else float("inf")

    def clear_warning(self):
        """Remove current warning."""
        self._warning_msg = ""
        self._warning_level = ""
        self._warning_until = 0.0

    def set_hud_enabled(self, enabled: bool):
        """Toggle HUD overlay on/off."""
        self._hud_enabled = bool(enabled)

    # ------------------------------------------------------------------
    # Internal: Display helpers
    # ------------------------------------------------------------------
    def _display_frame(self, bgr_frame: np.ndarray):
        """Convert BGR numpy array → QPixmap and display in QLabel."""
        cv2 = _get_cv2()
        if cv2 is not None:
            rgb = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2RGB)
        else:
            # Fallback: assume it might already be RGB or just display raw
            rgb = bgr_frame

        h, w, ch = rgb.shape
        bytes_per_line = ch * w
        qimg = QImage(rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(qimg)

        # Scale to label keeping aspect ratio
        label_size = self._video_label.size()
        scaled = pixmap.scaled(
            label_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._video_label.setPixmap(scaled)

    def _update_info_bar(self):
        """Update the small AI summary bar below the video."""
        if not self._detections:
            self._info_label.setText("AI: No detections")
            return

        # Summarise detections
        counts: dict = {}
        for d in self._detections:
            counts[d.class_name] = counts.get(d.class_name, 0) + 1

        parts = [f"{name.upper()} ×{n}" for name, n in counts.items()]
        tracked = [d for d in self._detections if d.track_id >= 0]
        track_str = f"  |  Tracking ID {tracked[0].track_id}" if tracked else ""
        self._info_label.setText(f"AI: {', '.join(parts)}{track_str}")

    # ------------------------------------------------------------------
    # Main HUD drawing
    # ------------------------------------------------------------------
        # --- Full telemetry overlay toggle (False = Clean AI-Only Mode) ---
        self._show_full_telemetry: bool = False

    def set_show_full_telemetry(self, show: bool):
        """Enable or disable full telemetry HUD overlays on top of video."""
        self._show_full_telemetry = bool(show)

    def _draw_hud(self, frame: np.ndarray) -> np.ndarray:
        """
        Draw AI detections & image analysis results onto the BGR frame.
        Telemetry overlays (horizon, depth tape, heading tape, battery, status)
        are hidden by default to keep the camera view clean and uncluttered.
        """
        cv2 = _get_cv2()
        if cv2 is None:
            # No OpenCV: return frame unchanged
            return frame

        h, w = frame.shape[:2]
        cx, cy = w // 2, h // 2

        # Check / clear expired warning
        if self._warning_msg and time.monotonic() > self._warning_until:
            self.clear_warning()

        # 1. Subtle centre crosshair for target orientation
        self._draw_crosshair(frame, cv2, cx, cy)

        # 2. AI Detections & Image Analysis (Bounding boxes, class labels, conf %, track IDs)
        self._draw_detections(frame, cv2, h, w)

        # 3. Warning overlay (if active warning)
        self._draw_warning_overlay(frame, cv2, w, h, cx, cy)

        # 4. Optional full telemetry overlays (only if explicitly enabled)
        if getattr(self, '_show_full_telemetry', False):
            roll_rad  = math.radians(self._roll)
            pitch_rad = math.radians(self._pitch)
            self._draw_artificial_horizon(frame, cv2, cx, cy, roll_rad, pitch_rad)
            self._draw_depth_tape(frame, cv2, w, h)
            self._draw_heading_tape(frame, cv2, w, h)
            self._draw_status_panel(frame, cv2, w, h)
            self._draw_power_panel(frame, cv2, w, h)
            self._draw_timestamp(frame, cv2, w, h)

        return frame

    # ------------------------------------------------------------------
    # Element: Artificial Horizon
    # ------------------------------------------------------------------
    def _draw_artificial_horizon(
        self,
        img: np.ndarray,
        cv2,
        cx: int, cy: int,
        roll_rad: float,
        pitch_rad: float,
    ):
        """Draw rolling/pitching artificial horizon in the centre region."""
        h, w = img.shape[:2]
        horizon_w = min(w, h) // 2    # half-width of horizon area
        horizon_h = min(w, h) // 2    # half-height of horizon area

        # ── Sky / Ground fill using rotated trapezoids ──────────────────
        # We create a mask canvas the size of the horizon region
        canvas = np.zeros((horizon_h * 2, horizon_w * 2, 3), dtype=np.uint8)
        can_cx = horizon_w
        can_cy = horizon_h

        # Pixel offset for pitch (each degree = ~3 pixels at this scale)
        pitch_px = int(pitch_rad * (horizon_h / (math.pi / 3)))  # 60° = full height

        # Horizon line midpoint displaced by pitch
        mid_y = can_cy + pitch_px

        # Draw ground (brown) below horizon, sky (near-black) above
        cos_r = math.cos(roll_rad)
        sin_r = math.sin(roll_rad)

        # Horizon line endpoints (in canvas)
        line_len = horizon_w + horizon_h  # long enough to span
        hx1 = int(can_cx - line_len * cos_r)
        hy1 = int(mid_y + line_len * sin_r)
        hx2 = int(can_cx + line_len * cos_r)
        hy2 = int(mid_y - line_len * sin_r)

        # Fill ground (below horizon in rotated space)
        # Use fillConvexPoly with a computed ground polygon
        ground_pts = _rotated_fill_polygon(
            can_cx, mid_y, roll_rad, line_len, horizon_w * 2, horizon_h * 2, above=False
        )
        sky_pts = _rotated_fill_polygon(
            can_cx, mid_y, roll_rad, line_len, horizon_w * 2, horizon_h * 2, above=True
        )

        if sky_pts is not None and len(sky_pts) >= 3:
            cv2.fillPoly(canvas, [sky_pts], (25, 15, 5))        # dark sky
        if ground_pts is not None and len(ground_pts) >= 3:
            cv2.fillPoly(canvas, [ground_pts], _C.BROWN)        # brown water

        # Draw horizon line
        cv2.line(canvas, (hx1, hy1), (hx2, hy2), _C.WHITE, 2, cv2.LINE_AA)

        # ── Pitch ladder lines ──────────────────────────────────────────
        for deg in range(-30, 31, 5):
            if deg == 0:
                continue
            offset_px = int(math.radians(deg) * (horizon_h / (math.pi / 3)))
            # Rotate this offset by roll
            px = int(can_cx - offset_px * sin_r)
            py = int(mid_y + offset_px * cos_r)

            tick_half = horizon_w // 5 if abs(deg) % 10 == 0 else horizon_w // 8
            dx = int(tick_half * cos_r)
            dy = int(-tick_half * sin_r)

            pt1 = (px - dx, py - dy)
            pt2 = (px + dx, py + dy)
            color = _C.WHITE if abs(deg) % 10 == 0 else _C.GRAY
            thick = 1
            cv2.line(canvas, pt1, pt2, color, thick, cv2.LINE_AA)

            # Degree labels on major ticks
            if abs(deg) % 10 == 0:
                label = f"{abs(deg)}°"
                lx = px + dx + 4
                ly = py + dy + 5
                cv2.putText(canvas, label, (lx, ly),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.28, _C.WHITE, 1, cv2.LINE_AA)

        # ── Blend canvas onto main frame ──────────────────────────────
        # Region of interest on main frame
        x0 = cx - horizon_w
        y0 = cy - horizon_h
        x1 = cx + horizon_w
        y1 = cy + horizon_h

        # Clamp
        fx0 = max(0, x0)
        fy0 = max(0, y0)
        fx1 = min(w, x1)
        fy1 = min(h, y1)
        cx0 = fx0 - x0
        cy0 = fy0 - y0
        cx1 = cx0 + (fx1 - fx0)
        cy1 = cy0 + (fy1 - fy0)

        if fx1 > fx0 and fy1 > fy0 and cx1 > cx0 and cy1 > cy0:
            roi = img[fy0:fy1, fx0:fx1]
            can_roi = canvas[cy0:cy1, cx0:cx1]
            # Only blend where canvas is not zero (black = transparent)
            mask = (can_roi.sum(axis=2) > 0).astype(np.uint8)[:, :, np.newaxis]
            blended = (can_roi * mask * 0.45 + roi * (1 - mask * 0.45)).astype(np.uint8)
            img[fy0:fy1, fx0:fx1] = blended

        # ── Roll indicator (bank angle arc at top centre) ─────────────
        arc_r = horizon_w // 2 + 10
        arc_cx, arc_cy = cx, cy - arc_r - 5
        # Triangle pointer
        tri_angle = -self._roll  # degrees
        tri_rad = math.radians(tri_angle - 90)
        tip_x = int(cx + arc_r * math.cos(math.radians(-self._roll - 90)))
        tip_y = int(cy - arc_r * math.sin(math.radians(-self._roll + 90)) - 5)
        # Draw arc from -60 to +60 degrees
        cv2.ellipse(img, (cx, cy), (arc_r, arc_r), 0, 210, 330, _C.WHITE, 1, cv2.LINE_AA)
        # Tick marks at 0, ±10, ±20, ±30, ±45, ±60
        for deg_t in (-60, -45, -30, -20, -10, 0, 10, 20, 30, 45, 60):
            angle_rad = math.radians(deg_t - 90)
            outer_x = int(cx + arc_r * math.cos(angle_rad))
            outer_y = int(cy + arc_r * math.sin(angle_rad))
            inner_r = arc_r - (8 if deg_t % 30 == 0 else 4)
            inner_x = int(cx + inner_r * math.cos(angle_rad))
            inner_y = int(cy + inner_r * math.sin(angle_rad))
            cv2.line(img, (inner_x, inner_y), (outer_x, outer_y), _C.WHITE, 1, cv2.LINE_AA)

        # Roll pointer triangle
        roll_angle_rad = math.radians(-self._roll - 90)
        tip = (
            int(cx + arc_r * math.cos(roll_angle_rad)),
            int(cy + arc_r * math.sin(roll_angle_rad)),
        )
        perp = roll_angle_rad + math.pi / 2
        base1 = (
            int(tip[0] - 6 * math.cos(roll_angle_rad) + 5 * math.cos(perp)),
            int(tip[1] - 6 * math.sin(roll_angle_rad) + 5 * math.sin(perp)),
        )
        base2 = (
            int(tip[0] - 6 * math.cos(roll_angle_rad) - 5 * math.cos(perp)),
            int(tip[1] - 6 * math.sin(roll_angle_rad) - 5 * math.sin(perp)),
        )
        pts = np.array([tip, base1, base2], dtype=np.int32)
        cv2.fillPoly(img, [pts], _C.YELLOW)
        cv2.polylines(img, [pts], True, _C.WHITE, 1, cv2.LINE_AA)

    # ------------------------------------------------------------------
    # Element: Depth Tape (right side)
    # ------------------------------------------------------------------
    def _draw_depth_tape(self, img: np.ndarray, cv2, w: int, h: int):
        """Draw a vertical scrolling depth tape on the right side."""
        tape_x     = w - 70
        tape_w     = 55
        tape_top   = h // 6
        tape_bot   = h * 5 // 6
        tape_h     = tape_bot - tape_top
        centre_y   = (tape_top + tape_bot) // 2

        # Background
        overlay = img.copy()
        cv2.rectangle(overlay, (tape_x, tape_top), (tape_x + tape_w, tape_bot),
                      (15, 20, 25), -1)
        cv2.addWeighted(overlay, 0.55, img, 0.45, 0, img)

        # Border
        cv2.rectangle(img, (tape_x, tape_top), (tape_x + tape_w, tape_bot),
                      _C.DARK_GRAY, 1)

        # Title
        cv2.putText(img, "DEPTH", (tape_x + 4, tape_top - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.30, _C.CYAN, 1, cv2.LINE_AA)

        # Pixels per metre
        px_per_m = tape_h / 10.0   # show 10 m range

        # Draw tick marks
        depth_start = self._depth - 5.0  # top of tape
        for i in range(-6, 8):
            d = round(depth_start + i)
            py = int(centre_y + (d - self._depth) * px_per_m)
            if tape_top <= py <= tape_bot:
                tick_len = 12 if d % 5 == 0 else 6
                cv2.line(img, (tape_x, py), (tape_x + tick_len, py), _C.GRAY, 1)
                if d % 1 == 0:
                    label = f"{d}m" if d >= 0 else f"{d}m"
                    cv2.putText(img, label, (tape_x + tick_len + 2, py + 4),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.28, _C.GRAY, 1, cv2.LINE_AA)

        # 0.5m sub-ticks
        for i in range(-12, 16):
            d = depth_start + i * 0.5
            py = int(centre_y + (d - self._depth) * px_per_m)
            if tape_top <= py <= tape_bot:
                cv2.line(img, (tape_x, py), (tape_x + 4, py), _C.DARK_GRAY, 1)

        # Current depth indicator box
        box_h = 22
        box_y  = centre_y - box_h // 2
        cv2.rectangle(img, (tape_x - 2, box_y),
                      (tape_x + tape_w + 2, box_y + box_h), (20, 30, 40), -1)
        cv2.rectangle(img, (tape_x - 2, box_y),
                      (tape_x + tape_w + 2, box_y + box_h), _C.CYAN, 1)
        depth_txt = f"{self._depth:.2f}"
        _draw_text_with_bg(img, depth_txt,
                           (tape_x + 4, box_y + 15),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.42, _C.CYAN, 1)

        # Centre line (pointer)
        cv2.line(img, (tape_x - 5, centre_y), (tape_x, centre_y), _C.CYAN, 2)

    # ------------------------------------------------------------------
    # Element: Heading Tape (top)
    # ------------------------------------------------------------------
    def _draw_heading_tape(self, img: np.ndarray, cv2, w: int, h: int):
        """Draw a horizontal scrolling heading tape across the top."""
        tape_y   = 8
        tape_h   = 40
        tape_x0  = 90
        tape_x1  = w - 90
        tape_w   = tape_x1 - tape_x0
        centre_x = w // 2

        # Background
        overlay = img.copy()
        cv2.rectangle(overlay, (tape_x0, tape_y),
                      (tape_x1, tape_y + tape_h), (15, 20, 25), -1)
        cv2.addWeighted(overlay, 0.60, img, 0.40, 0, img)
        cv2.rectangle(img, (tape_x0, tape_y),
                      (tape_x1, tape_y + tape_h), _C.DARK_GRAY, 1)

        # Pixels per degree
        px_per_deg = tape_w / 60.0   # 60° visible range

        cardinals = {0: ("N", _C.HEADING_N), 90: ("E", _C.HEADING_E),
                     180: ("S", _C.HEADING_S), 270: ("W", _C.HEADING_W)}

        for i in range(-35, 36):
            deg = (int(self._heading) + i) % 360
            px = int(centre_x + i * px_per_deg)
            if tape_x0 <= px <= tape_x1:
                if deg % 10 == 0:
                    tick_len = 16 if deg % 30 == 0 else 8
                    cv2.line(img, (px, tape_y + tape_h - tick_len),
                             (px, tape_y + tape_h), _C.GRAY, 1)
                    if deg % 30 == 0:
                        if deg in cardinals:
                            label, col = cardinals[deg]
                        else:
                            label, col = str(deg), _C.WHITE
                        (tw, _), _ = cv2.getTextSize(
                            label, cv2.FONT_HERSHEY_SIMPLEX, 0.32, 1)
                        cv2.putText(img, label, (px - tw // 2, tape_y + tape_h - 18),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.32, col, 1, cv2.LINE_AA)
                elif deg % 5 == 0:
                    cv2.line(img, (px, tape_y + tape_h - 5),
                             (px, tape_y + tape_h), _C.DARK_GRAY, 1)

        # Centre triangle pointer
        tri_pts = np.array([
            (centre_x, tape_y + tape_h),
            (centre_x - 6, tape_y + tape_h - 10),
            (centre_x + 6, tape_y + tape_h - 10),
        ], dtype=np.int32)
        cv2.fillPoly(img, [tri_pts], _C.CYAN)

        # Current heading box
        hdg_txt = f"{int(self._heading):03d}°"
        (tw, th), _ = cv2.getTextSize(hdg_txt, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
        bx0 = centre_x - tw // 2 - 6
        bx1 = centre_x + tw // 2 + 6
        by0 = tape_y
        by1 = tape_y + th + 10
        cv2.rectangle(img, (bx0, by0), (bx1, by1), (20, 30, 40), -1)
        cv2.rectangle(img, (bx0, by0), (bx1, by1), _C.CYAN, 1)
        cv2.putText(img, hdg_txt, (centre_x - tw // 2, by0 + th + 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, _C.CYAN, 1, cv2.LINE_AA)

    # ------------------------------------------------------------------
    # Element: Status Panel (top-left)
    # ------------------------------------------------------------------
    def _draw_status_panel(self, img: np.ndarray, cv2, w: int, h: int):
        """Draw mode, armed state, depth, speed in top-left corner."""
        px, py = 8, 58    # start below heading tape

        font = cv2.FONT_HERSHEY_SIMPLEX

        # Panel background
        panel_w, panel_h = 180, 80
        overlay = img.copy()
        cv2.rectangle(overlay, (px - 4, py - 4),
                      (px + panel_w, py + panel_h), (10, 15, 20), -1)
        cv2.addWeighted(overlay, 0.60, img, 0.40, 0, img)
        _draw_rounded_rect(img, (px - 4, py - 4),
                           (px + panel_w, py + panel_h), _C.DARK_GRAY, 4, 1)

        # Mode badge
        mode_col = _C.GREEN if self._mode == "AUTO" else _C.YELLOW
        mode_txt = f"[{self._mode}]"
        cv2.putText(img, mode_txt, (px, py + 14),
                    font, 0.42, mode_col, 1, cv2.LINE_AA)

        # Armed badge
        arm_col = _C.RED_BRIGHT if self._armed else _C.DARK_GRAY
        arm_txt = "ARMED" if self._armed else "DISARMED"
        (mw, _), _ = cv2.getTextSize(mode_txt, font, 0.42, 1)
        cv2.putText(img, arm_txt, (px + mw + 6, py + 14),
                    font, 0.38, arm_col, 1, cv2.LINE_AA)

        # Depth
        cv2.putText(img, f"DEPTH: {self._depth:.2f} m",
                    (px, py + 38), font, 0.40, _C.CYAN, 1, cv2.LINE_AA)

        # Speed
        cv2.putText(img, f"SPD:   {self._speed:.2f} m/s",
                    (px, py + 58), font, 0.40, _C.WHITE, 1, cv2.LINE_AA)

        # Pitch / Roll readout
        cv2.putText(img, f"R:{self._roll:+.1f}° P:{self._pitch:+.1f}°",
                    (px, py + 76), font, 0.32, _C.GRAY, 1, cv2.LINE_AA)

    # ------------------------------------------------------------------
    # Element: Power Panel (top-right)
    # ------------------------------------------------------------------
    def _draw_power_panel(self, img: np.ndarray, cv2, w: int, h: int):
        """Draw battery, current, and signal in top-right corner."""
        panel_w = 190
        px = w - panel_w - 75   # leave room for depth tape
        py = 58

        font = cv2.FONT_HERSHEY_SIMPLEX

        # Background
        overlay = img.copy()
        cv2.rectangle(overlay, (px - 4, py - 4),
                      (px + panel_w, py + 84), (10, 15, 20), -1)
        cv2.addWeighted(overlay, 0.60, img, 0.40, 0, img)
        _draw_rounded_rect(img, (px - 4, py - 4),
                           (px + panel_w, py + 84), _C.DARK_GRAY, 4, 1)

        # Battery bar
        bar_full_w = 80
        bar_h = 11
        bar_x = px + 44
        bar_y = py + 4
        filled = int(bar_full_w * self._pct / 100.0)

        # Choose bar colour by percentage
        if self._pct > 50:
            bar_col = _C.GREEN
        elif self._pct > 20:
            bar_col = _C.YELLOW
        else:
            # Blink red when low
            bar_col = _C.RED_BRIGHT if time.monotonic() % 1.0 < 0.5 else _C.DARK_GRAY

        cv2.putText(img, "BAT:", (px, bar_y + bar_h - 1),
                    font, 0.38, _C.GRAY, 1, cv2.LINE_AA)
        cv2.rectangle(img, (bar_x, bar_y), (bar_x + bar_full_w, bar_y + bar_h),
                      _C.DARK_GRAY, -1)
        if filled > 0:
            cv2.rectangle(img, (bar_x, bar_y), (bar_x + filled, bar_y + bar_h),
                          bar_col, -1)
        cv2.rectangle(img, (bar_x, bar_y), (bar_x + bar_full_w, bar_y + bar_h),
                      _C.GRAY, 1)

        pct_txt = f"{int(self._pct)}%"
        cv2.putText(img, pct_txt, (bar_x + bar_full_w + 4, bar_y + bar_h - 1),
                    font, 0.38, bar_col, 1, cv2.LINE_AA)

        # Voltage
        cv2.putText(img, f"{self._voltage:.1f}V",
                    (px + 140, bar_y + bar_h - 1),
                    font, 0.38, _C.WHITE, 1, cv2.LINE_AA)

        # Current
        cv2.putText(img, f"CURR: {self._current:.1f}A",
                    (px, py + 36), font, 0.38, _C.WHITE, 1, cv2.LINE_AA)

        # Signal bar
        sig_bar_w = 50
        sig_x = px + 100
        sig_y = py + 26
        sig_filled = int(sig_bar_w * self._signal_pct / 100.0)
        sig_col = _C.GREEN if self._signal_pct > 60 else (
            _C.YELLOW if self._signal_pct > 30 else _C.RED_BRIGHT
        )
        cv2.putText(img, "LINK:", (px, py + 56),
                    font, 0.38, _C.GRAY, 1, cv2.LINE_AA)
        cv2.rectangle(img, (px + 44, py + 46),
                      (px + 44 + sig_bar_w, py + 46 + 9), _C.DARK_GRAY, -1)
        if sig_filled > 0:
            cv2.rectangle(img, (px + 44, py + 46),
                          (px + 44 + sig_filled, py + 46 + 9), sig_col, -1)
        cv2.rectangle(img, (px + 44, py + 46),
                      (px + 44 + sig_bar_w, py + 46 + 9), _C.GRAY, 1)
        cv2.putText(img, f"{int(self._signal_pct)}%",
                    (px + 44 + sig_bar_w + 4, py + 55),
                    font, 0.38, sig_col, 1, cv2.LINE_AA)

        # YAW readout
        cv2.putText(img, f"YAW: {self._yaw:.1f}°",
                    (px, py + 76), font, 0.35, _C.GRAY, 1, cv2.LINE_AA)

    # ------------------------------------------------------------------
    # Element: Crosshair
    # ------------------------------------------------------------------
    def _draw_crosshair(self, img: np.ndarray, cv2, cx: int, cy: int):
        """Draw fixed centre crosshair."""
        size = 18
        gap  = 5
        col  = _C.WHITE
        thick = 1

        # Horizontal
        cv2.line(img, (cx - size, cy), (cx - gap, cy), col, thick, cv2.LINE_AA)
        cv2.line(img, (cx + gap, cy), (cx + size, cy), col, thick, cv2.LINE_AA)
        # Vertical
        cv2.line(img, (cx, cy - size), (cx, cy - gap), col, thick, cv2.LINE_AA)
        cv2.line(img, (cx, cy + gap), (cx, cy + size), col, thick, cv2.LINE_AA)
        # Centre dot
        cv2.circle(img, (cx, cy), 2, _C.CYAN, -1, cv2.LINE_AA)

    # ------------------------------------------------------------------
    # Element: AI Detection Boxes
    # ------------------------------------------------------------------
    def _draw_detections(self, img: np.ndarray, cv2, h: int, w: int):
        """Draw bounding boxes for AI detections."""
        if not self._detections:
            return

        font = cv2.FONT_HERSHEY_SIMPLEX

        for det in self._detections:
            color = _C.detection_color(det.class_name)
            x1, y1, x2, y2 = int(det.x1), int(det.y1), int(det.x2), int(det.y2)

            # Clamp to frame
            x1 = max(0, min(w - 1, x1))
            y1 = max(0, min(h - 1, y1))
            x2 = max(0, min(w - 1, x2))
            y2 = max(0, min(h - 1, y2))

            if x2 <= x1 or y2 <= y1:
                continue

            # Bounding box
            cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)

            # Corner accent lines (top-left, bottom-right)
            corner_len = min(20, (x2 - x1) // 4, (y2 - y1) // 4)
            # TL
            cv2.line(img, (x1, y1), (x1 + corner_len, y1), _C.WHITE, 2)
            cv2.line(img, (x1, y1), (x1, y1 + corner_len), _C.WHITE, 2)
            # TR
            cv2.line(img, (x2, y1), (x2 - corner_len, y1), _C.WHITE, 2)
            cv2.line(img, (x2, y1), (x2, y1 + corner_len), _C.WHITE, 2)
            # BL
            cv2.line(img, (x1, y2), (x1 + corner_len, y2), _C.WHITE, 2)
            cv2.line(img, (x1, y2), (x1, y2 - corner_len), _C.WHITE, 2)
            # BR
            cv2.line(img, (x2, y2), (x2 - corner_len, y2), _C.WHITE, 2)
            cv2.line(img, (x2, y2), (x2, y2 - corner_len), _C.WHITE, 2)

            # Label
            label = f"{det.class_name.upper()} {int(det.conf * 100)}%"
            if det.track_id >= 0:
                label += f" #{det.track_id}"

            lx = x1
            ly = y1 - 6 if y1 > 20 else y2 + 16
            _draw_text_with_bg(img, label, (lx, ly), font, 0.40,
                               _C.WHITE, 1, bg_color=(15, 20, 25), padding=3, alpha=0.7)

            # Tracked detection: centre dot + scan circle
            if det.track_id >= 0:
                bx = (x1 + x2) // 2
                by = (y1 + y2) // 2
                cv2.circle(img, (bx, by), 4, color, -1, cv2.LINE_AA)
                # Animated scan radius
                t = time.monotonic()
                scan_r = int(10 + 6 * math.sin(t * 3))
                cv2.circle(img, (bx, by), scan_r, color, 1, cv2.LINE_AA)

                # Offset arrow from centre frame to detection centre
                cx_frame = w // 2
                cy_frame = h // 2
                dx = bx - cx_frame
                dy = by - cy_frame
                if abs(dx) > 5 or abs(dy) > 5:
                    ang = math.atan2(dy, dx)
                    arrow_len = 25
                    ax = int(cx_frame + arrow_len * math.cos(ang))
                    ay = int(cy_frame + arrow_len * math.sin(ang))
                    cv2.arrowedLine(img, (cx_frame, cy_frame), (ax, ay),
                                    color, 1, cv2.LINE_AA, tipLength=0.4)

    # ------------------------------------------------------------------
    # Element: Warning Overlay
    # ------------------------------------------------------------------
    def _draw_warning_overlay(
        self,
        img: np.ndarray,
        cv2,
        w: int, h: int,
        cx: int, cy: int,
    ):
        """Draw flashing warning border and/or critical red overlay."""
        if not self._warning_msg:
            return

        blink_on = time.monotonic() % 1.0 < 0.5
        level = self._warning_level

        if level == "critical":
            # 30% red overlay
            overlay = img.copy()
            overlay[:] = (0, 0, 180)   # red fill (BGR)
            cv2.addWeighted(overlay, 0.28, img, 0.72, 0, img)

            # Central message
            font = cv2.FONT_HERSHEY_SIMPLEX
            msg = f"!! {self._warning_msg.upper()} !!"
            scale = 0.9
            (tw, th), _ = cv2.getTextSize(msg, font, scale, 2)
            tx = cx - tw // 2
            ty = cy + th // 2
            # Drop shadow
            cv2.putText(img, msg, (tx + 2, ty + 2), font, scale,
                        _C.BLACK, 3, cv2.LINE_AA)
            cv2.putText(img, msg, (tx, ty), font, scale,
                        _C.RED_BRIGHT, 2, cv2.LINE_AA)

            # Pulsing border
            if blink_on:
                border = 5
                cv2.rectangle(img, (border, border), (w - border, h - border),
                              _C.RED_BRIGHT, border, cv2.LINE_AA)

        elif level == "warn":
            # Yellow blinking border
            if blink_on:
                border = 4
                cv2.rectangle(img, (border, border), (w - border, h - border),
                              _C.YELLOW, border, cv2.LINE_AA)

            # Warning text top-centre
            font = cv2.FONT_HERSHEY_SIMPLEX
            msg = f"WARN: {self._warning_msg}"
            scale = 0.55
            (tw, _), _ = cv2.getTextSize(msg, font, scale, 1)
            tx = cx - tw // 2
            ty = 55
            _draw_text_with_bg(img, msg, (tx, ty), font, scale,
                               _C.YELLOW, 1, bg_color=(30, 20, 0), padding=4)

    # ------------------------------------------------------------------
    # Element: Timestamp
    # ------------------------------------------------------------------
    def _draw_timestamp(self, img: np.ndarray, cv2, w: int, h: int):
        """Draw UTC timestamp in bottom-right corner."""
        import datetime
        ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        font = cv2.FONT_HERSHEY_SIMPLEX
        scale = 0.32
        (tw, th), _ = cv2.getTextSize(ts, font, scale, 1)
        tx = w - tw - 8
        ty = h - 8
        _draw_text_with_bg(img, ts, (tx, ty), font, scale,
                           _C.GRAY, 1, bg_color=(10, 10, 10), padding=2, alpha=0.5)


# ---------------------------------------------------------------------------
# Helper: rotated fill polygon for artificial horizon
# ---------------------------------------------------------------------------
def _rotated_fill_polygon(
    cx: int, cy: int,
    roll_rad: float,
    line_len: int,
    canvas_w: int, canvas_h: int,
    above: bool,
) -> Optional[np.ndarray]:
    """
    Compute polygon points to fill the region above or below the
    horizon line in a rotated canvas.
    """
    cos_r = math.cos(roll_rad)
    sin_r = math.sin(roll_rad)

    # Horizon end points
    hx1 = int(cx - line_len * cos_r)
    hy1 = int(cy + line_len * sin_r)
    hx2 = int(cx + line_len * cos_r)
    hy2 = int(cy - line_len * sin_r)

    if above:
        # Corners that are above the horizon
        corners = [(0, 0), (canvas_w, 0), (canvas_w, canvas_h), (0, canvas_h)]
    else:
        corners = [(0, 0), (canvas_w, 0), (canvas_w, canvas_h), (0, canvas_h)]

    # Perpendicular direction (from horizon, pointing "up" or "down")
    perp_x = sin_r
    perp_y = cos_r

    def side(px, py):
        """Returns positive if point is on 'above' side, negative if below."""
        # Vector from horizon midpoint to point
        vx = px - cx
        vy = py - cy
        # Dot with perpendicular
        return vx * perp_x + vy * perp_y

    sign = 1 if above else -1

    # Collect canvas corners on the correct side
    selected = [(x, y) for x, y in corners if sign * side(x, y) >= 0]

    if not selected:
        return None

    # Build polygon: horizon endpoints + selected corners
    # Sort corners in a convex order (simple approach: use convex hull)
    pts_raw = [(hx1, hy1), (hx2, hy2)] + selected

    # Convex hull
    pts_arr = np.array(pts_raw, dtype=np.float32)
    # Compute centroid and sort by angle
    centroid = pts_arr.mean(axis=0)
    angles = np.arctan2(pts_arr[:, 1] - centroid[1], pts_arr[:, 0] - centroid[0])
    order = np.argsort(angles)
    pts_sorted = pts_arr[order].astype(np.int32)

    return pts_sorted


# ---------------------------------------------------------------------------
# Quick standalone test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    from PyQt6.QtWidgets import QApplication, QMainWindow, QPushButton, QHBoxLayout

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    win = QMainWindow()
    win.setWindowTitle("AR HUD Widget – Test")
    win.resize(900, 560)

    central = QWidget()
    win.setCentralWidget(central)
    layout = QVBoxLayout(central)
    layout.setContentsMargins(0, 0, 0, 0)

    hud = ARHUDWidget()
    layout.addWidget(hud)

    # Controls
    btn_row = QWidget()
    btn_layout = QHBoxLayout(btn_row)
    btn_layout.setContentsMargins(4, 4, 4, 4)

    btn_warn = QPushButton("⚠ WARN")
    btn_warn.clicked.connect(lambda: hud.set_warning("LOW BATTERY", "warn", 10))
    btn_crit = QPushButton("🔴 CRITICAL")
    btn_crit.clicked.connect(lambda: hud.set_warning("DEPTH LIMIT EXCEEDED", "critical", 10))
    btn_clear = QPushButton("Clear Warning")
    btn_clear.clicked.connect(hud.clear_warning)
    btn_toggle = QPushButton("Toggle HUD")
    btn_toggle.clicked.connect(lambda: hud.set_hud_enabled(not hud._hud_enabled))

    for b in (btn_warn, btn_crit, btn_clear, btn_toggle):
        b.setFixedHeight(28)
        b.setStyleSheet("QPushButton{background:#1e3a4a;color:#7ecfff;"
                        "border:1px solid #2a5a6a;border-radius:4px;padding:0 8px;}"
                        "QPushButton:hover{background:#2a5a6a;}")
        btn_layout.addWidget(b)

    layout.addWidget(btn_row)

    # Fake telemetry update loop
    from PyQt6.QtCore import QTimer
    _t = 0.0

    def _tick():
        global _t
        _t += 0.05

        hud.update_telemetry(
            roll    = 20 * math.sin(_t * 0.4),
            pitch   = 10 * math.sin(_t * 0.3),
            yaw     = (_t * 15) % 360,
            depth   = 3.0 + 1.5 * math.sin(_t * 0.2),
            heading = (_t * 20) % 360,
            speed   = max(0, 0.5 + 0.3 * math.sin(_t)),
            voltage = 14.8 - 0.002 * _t,
            current = 8.0 + 2.0 * math.sin(_t * 0.7),
            pct     = max(5, 100 - _t * 0.5),
            signal_pct = max(10, 95 - _t * 0.2),
            mode    = "AUTO" if math.sin(_t * 0.1) > 0 else "MANUAL",
            armed   = True,
        )

        # Fake AI detections
        import random
        if int(_t * 2) % 5 == 0:
            det = Detection(
                class_name="diver",
                conf=0.87 + 0.1 * random.random(),
                x1=200, y1=120, x2=330, y2=260,
                track_id=42,
            )
            hud.set_detections([det])
        elif int(_t * 2) % 5 == 2:
            hud.set_detections([
                Detection("pipe",   0.91, 50,  200, 400, 240),
                Detection("debris", 0.73, 500, 150, 620, 280),
            ])
        else:
            hud.set_detections([])

        # Fake frame (gradient + noise)
        import numpy as np
        fh, fw = 480, 640
        frame = np.zeros((fh, fw, 3), dtype=np.uint8)
        # Underwater gradient
        for row in range(fh):
            val = int(20 + 40 * row / fh)
            frame[row, :] = (val, val + 10, val + 20)
        # Add noise
        noise = np.random.randint(0, 25, (fh, fw, 3), dtype=np.uint8)
        frame = np.clip(frame.astype(np.int16) + noise, 0, 255).astype(np.uint8)

        hud.set_frame(frame)

    timer = QTimer()
    timer.timeout.connect(_tick)
    timer.start(33)   # ~30 fps

    win.show()
    sys.exit(app.exec())
