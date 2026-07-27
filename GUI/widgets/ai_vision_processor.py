"""
ai_vision_processor.py - AI Edge Vision with YOLOv8 + Auto-Track
================================================================
QThread chay YOLOv8 inference tren luong video.
Ho tro:
  - Object detection: diver, pipe, debris, ROV
  - Multi-object tracking (ByteTrack built-in ultralytics)
  - Auto-track mode: tinh do lech tam → generate yaw/pitch offset
  - Custom model path
  - Confidence + NMS threshold controls

Tich hop:
  ar_hud_widget.set_detections() → ve bbox len video
  main.py._on_track_error() → gui lenh MAVLink
"""

from __future__ import annotations

import queue
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

try:
    from PyQt6.QtCore import QThread, pyqtSignal
except ImportError:
    from PyQt5.QtCore import QThread, pyqtSignal

# ---------------------------------------------------------------------------
# Class colour palette (BGR for OpenCV drawing)
# ---------------------------------------------------------------------------
CLASS_COLORS: Dict[str, tuple] = {
    "diver":  (0, 255, 0),    # Green
    "pipe":   (0, 255, 255),  # Yellow
    "debris": (0, 0, 255),    # Red
    "rov":    (255, 128, 0),  # Orange
}

# Default colour for unknown classes
_DEFAULT_COLOR = (200, 200, 200)

# Dead-zone threshold (normalised distance from frame centre)
_DEAD_ZONE = 0.05

# Sliding-window size for FPS calculation
_FPS_WINDOW = 10

# Frame queue capacity – old frames are dropped when inference is slow
_QUEUE_SIZE = 2


# ---------------------------------------------------------------------------
# Detection dataclass
# ---------------------------------------------------------------------------
@dataclass
class Detection:
    """Single detection result from one inference frame."""

    class_name: str
    confidence: float
    x1: int
    y1: int
    x2: int
    y2: int
    track_id: int = -1
    center_x: float = field(init=False)   # normalised [0, 1]
    center_y: float = field(init=False)   # normalised [0, 1]

    # Frame dimensions are needed to compute normalised centres.
    # We store them transiently so the dataclass can compute them
    # in __post_init__.
    _frame_w: int = field(default=1, repr=False, compare=False)
    _frame_h: int = field(default=1, repr=False, compare=False)

    def __post_init__(self) -> None:
        self.center_x = ((self.x1 + self.x2) / 2.0) / max(self._frame_w, 1)
        self.center_y = ((self.y1 + self.y2) / 2.0) / max(self._frame_h, 1)

    @property
    def color(self) -> tuple:
        """Return BGR draw colour for this class."""
        return CLASS_COLORS.get(self.class_name.lower(), _DEFAULT_COLOR)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"Detection(class={self.class_name!r}, conf={self.confidence:.2f}, "
            f"id={self.track_id}, cx={self.center_x:.3f}, cy={self.center_y:.3f})"
        )


# ---------------------------------------------------------------------------
# AIVisionProcessor  –  QThread
# ---------------------------------------------------------------------------
class AIVisionProcessor(QThread):
    """
    Background thread that runs YOLOv8 inference on submitted video frames.

    Usage
    -----
    processor = AIVisionProcessor(model_path='yolov8n.pt', conf=0.5)
    processor.sig_detections.connect(hud_widget.set_detections)
    processor.sig_track_error.connect(main_window._on_track_error)
    processor.sig_fps.connect(fps_label.setText)
    processor.start()

    # From the capture thread / timer:
    processor.submit_frame(frame_bgr)
    """

    # ------------------------------------------------------------------ #
    #  Qt signals                                                          #
    # ------------------------------------------------------------------ #
    sig_detections: pyqtSignal = pyqtSignal(list)        # List[Detection]
    sig_track_error: pyqtSignal = pyqtSignal(float, float)  # dx_norm, dy_norm
    sig_fps: pyqtSignal = pyqtSignal(float)             # inference FPS
    sig_model_loaded: pyqtSignal = pyqtSignal(bool, str)  # (success, message)

    # ------------------------------------------------------------------ #
    #  Constructor                                                         #
    # ------------------------------------------------------------------ #
    def __init__(
        self,
        model_path: str = "yolov8n.pt",
        target_classes: Optional[List[str]] = None,
        conf: float = 0.5,
        device: str = "cpu",
        parent=None,
    ) -> None:
        super().__init__(parent)

        self._model_path: str = model_path
        self._target_classes: Optional[List[str]] = (
            [c.lower() for c in target_classes] if target_classes else None
        )
        self._conf: float = float(np.clip(conf, 0.01, 1.0))
        self._device: str = device

        # Thread control
        self._running: bool = False

        # Frame queue  (maxsize prevents unbounded memory growth)
        self._frame_queue: queue.Queue = queue.Queue(maxsize=_QUEUE_SIZE)

        # Auto-track state
        self._auto_track: bool = False
        self._tracking_class: Optional[str] = None   # class to auto-track
        # Auto-track state
        self._auto_track: bool = False
        self._tracking_class: Optional[str] = None   # class to auto-track
        self._locked_track_id: int = -1              # ByteTrack ID being followed

        # Non-blocking busy flag to prevent frame queue buildup & video stalling
        self._is_busy: bool = False

        # Model ready flag — frames are dropped until model finishes loading
        self._model_ready: bool = False

        # FPS sliding window (timestamps of the last N completed inferences)
        self._ts_window: deque = deque(maxlen=_FPS_WINDOW)

        # Lazy-loaded model handle
        self._model = None

    # ------------------------------------------------------------------ #
    #  Public API (thread-safe setters)                                    #
    # ------------------------------------------------------------------ #
    def submit_frame(self, frame: np.ndarray) -> None:
        """
        Put a frame into the inference queue.
        Non-blocking & drop-if-busy: if the AI is currently processing a frame
        or the queue is full, the incoming frame is instantly skipped.
        This guarantees the video stream stays at 30 FPS without freezing.
        """
        if not self._running or not self._model_ready or self._is_busy:
            return
        if self._frame_queue.empty():
            try:
                self._frame_queue.put_nowait(frame.copy())
            except Exception:
                pass

    def set_tracking_target(self, class_name: str) -> None:
        """Select the class to auto-track (single class only)."""
        self._tracking_class = class_name.lower() if class_name else None
        self._locked_track_id = -1          # reset lock when target changes

    def set_auto_track(self, enabled: bool) -> None:
        """Enable or disable auto-track mode."""
        self._auto_track = bool(enabled)
        if not enabled:
            self._locked_track_id = -1

    def set_confidence(self, conf: float) -> None:
        """Update the confidence threshold (0-1)."""
        self._conf = float(np.clip(conf, 0.01, 1.0))

    def set_model_path(self, path: str) -> None:
        """Request a model reload on next run() cycle (restart thread to apply)."""
        self._model_path = path
        self._model = None  # force reload

    def set_target_classes(self, classes: Optional[List[str]]) -> None:
        """Update the list of target classes to detect (None = all)."""
        self._target_classes = (
            [c.lower() for c in classes] if classes else None
        )

    def stop(self) -> None:
        """Signal the run loop to exit and wait for thread to finish."""
        self._running = False
        self._model_ready = False
        # Unblock the queue.get() call so the thread can exit promptly
        try:
            self._frame_queue.put_nowait(None)   # sentinel value
        except Exception:
            pass
        self.wait(2000)

    # ------------------------------------------------------------------ #
    #  QThread.run()                                                       #
    # ------------------------------------------------------------------ #
    def run(self) -> None:  # noqa: C901
        """Main inference loop – executed in a separate OS thread."""
        self._running = True

        # Limit PyTorch CPU threads so inference doesn't saturate all cores & freeze GUI/video
        try:
            import torch
            torch.set_num_threads(2)
        except Exception:
            pass

        # ── Lazy import of ultralytics ────────────────────────────────── #
        if self._model is None:
            try:
                from ultralytics import YOLO  # type: ignore
                self._model = YOLO(self._model_path)
                # Warm-up run to JIT-compile and pre-allocate memory
                dummy = np.zeros((320, 320, 3), dtype=np.uint8)
                self._model.predict(dummy, verbose=False, device=self._device, imgsz=320)
                self._model_ready = True
                self.sig_model_loaded.emit(True, f"Model loaded: {self._model_path}")
            except ImportError:
                self.sig_model_loaded.emit(
                    False,
                    "ultralytics not installed – pip install ultralytics",
                )
                self._running = False
                return
            except Exception as exc:  # model file not found etc.
                self.sig_model_loaded.emit(False, f"Model load error: {exc}")
                self._running = False
                return

        # ── Inference loop ────────────────────────────────────────────── #
        while self._running:
            try:
                frame = self._frame_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            # Sentinel check
            if frame is None:
                break

            self._is_busy = True
            t_start = time.perf_counter()

            try:
                detections = self._infer(frame)
                t_end = time.perf_counter()

                # ── FPS tracking ──────────────────────────────────────────── #
                self._ts_window.append(t_end - t_start)
                if len(self._ts_window) >= 2:
                    avg_dt = sum(self._ts_window) / len(self._ts_window)
                    fps = 1.0 / avg_dt if avg_dt > 0 else 0.0
                else:
                    fps = 0.0
                self.sig_fps.emit(fps)

                # ── Emit detections ──────────────────────────────────────── #
                self.sig_detections.emit(detections)

                # ── Auto-track error ─────────────────────────────────────── #
                if self._auto_track:
                    dx, dy = self._compute_track_error(detections)
                    self.sig_track_error.emit(dx, dy)

            except Exception as exc:  # noqa: BLE001
                print(f"[AIVisionProcessor] Inference error: {exc}")
            finally:
                self._is_busy = False

        self._running = False

    # ------------------------------------------------------------------ #
    #  Private helpers                                                     #
    # ------------------------------------------------------------------ #
    def _infer(self, frame: np.ndarray) -> List[Detection]:
        """
        Run YOLOv8 inference (with ByteTrack when auto-track is enabled).
        Returns a list of Detection objects.
        """
        h, w = frame.shape[:2]

        if self._auto_track:
            # ByteTrack (persist=True keeps track IDs across calls)
            results = self._model.track(
                frame,
                persist=True,
                conf=self._conf,
                device=self._device,
                imgsz=320,
                verbose=False,
            )
        else:
            results = self._model.predict(
                frame,
                conf=self._conf,
                device=self._device,
                imgsz=320,
                verbose=False,
            )

        detections: List[Detection] = []
        if not results:
            return detections

        result = results[0]
        boxes = result.boxes

        if boxes is None or len(boxes) == 0:
            return detections

        # Extract tensors/arrays
        xyxy = boxes.xyxy.cpu().numpy().astype(int)
        confs = boxes.conf.cpu().numpy()
        class_ids = boxes.cls.cpu().numpy().astype(int)

        has_tracks = (boxes.id is not None)
        track_ids = boxes.id.cpu().numpy().astype(int) if has_tracks else None

        names = result.names  # dict {int: str}

        for i in range(len(xyxy)):
            cls_id = int(class_ids[i])
            class_name = names.get(cls_id, f"class_{cls_id}")

            # Filter by target classes (if set)
            if (
                self._target_classes is not None
                and class_name.lower() not in self._target_classes
            ):
                continue

            track_id = int(track_ids[i]) if has_tracks else -1

            det = Detection(
                class_name=class_name,
                confidence=float(confs[i]),
                x1=int(xyxy[i][0]),
                y1=int(xyxy[i][1]),
                x2=int(xyxy[i][2]),
                y2=int(xyxy[i][3]),
                track_id=track_id,
                _frame_w=w,
                _frame_h=h,
            )
            detections.append(det)

        return detections

    def _compute_track_error(
        self, detections: List[Detection]
    ) -> tuple[float, float]:
        """
        Compute the normalised tracking error for the selected target class.

        Strategy
        --------
        1. If we have a locked track_id, follow that specific object.
        2. Otherwise, pick the most-confident detection of the tracking class
           and lock onto its track_id.
        3. Error = (center_x - 0.5,  center_y - 0.5) → range [-0.5, +0.5].
        4. Dead-zone: if |dx| < DEAD_ZONE and |dy| < DEAD_ZONE → emit (0, 0).

        Returns
        -------
        (dx_norm, dy_norm) each in [-0.5, +0.5]; (0, 0) inside dead zone.
        """
        if not self._tracking_class or not detections:
            return 0.0, 0.0

        target_class = self._tracking_class
        candidate: Optional[Detection] = None

        # 1. Try to find the locked-on track ID
        if self._locked_track_id >= 0:
            for det in detections:
                if (
                    det.track_id == self._locked_track_id
                    and det.class_name.lower() == target_class
                ):
                    candidate = det
                    break

        # 2. Fall back to highest-confidence detection of target class
        if candidate is None:
            class_dets = [
                d for d in detections if d.class_name.lower() == target_class
            ]
            if class_dets:
                candidate = max(class_dets, key=lambda d: d.confidence)
                if candidate.track_id >= 0:
                    self._locked_track_id = candidate.track_id

        if candidate is None:
            # Target lost – release lock after a few missed frames
            # (simple implementation: release immediately)
            self._locked_track_id = -1
            return 0.0, 0.0

        dx = candidate.center_x - 0.5
        dy = candidate.center_y - 0.5

        # Dead-zone suppression
        if abs(dx) < _DEAD_ZONE:
            dx = 0.0
        if abs(dy) < _DEAD_ZONE:
            dy = 0.0

        return dx, dy

    # ------------------------------------------------------------------ #
    #  Properties                                                          #
    # ------------------------------------------------------------------ #
    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def current_fps(self) -> float:
        if len(self._ts_window) < 2:
            return 0.0
        avg = sum(self._ts_window) / len(self._ts_window)
        return 1.0 / avg if avg > 0 else 0.0

    @property
    def model_path(self) -> str:
        return self._model_path

    @property
    def conf_threshold(self) -> float:
        return self._conf
