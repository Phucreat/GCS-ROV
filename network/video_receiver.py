"""
video_receiver.py - Multi-source Video Receiver
===============================================
Ho tro:
  1. UDP H.264 stream tu ROV (port 5620) - CHINH THUC
  2. RTSP stream tu Raspberry Pi
  3. Local webcam (index 0, 1, 2...)
  4. Video file (cho testing)

ROV Pipeline (Pi / GStreamer):
  Pi phat:
    gst-launch-1.0 v4l2src ! video/x-raw,width=640,height=480,framerate=30/1 \\
      ! videoconvert ! x264enc tune=zerolatency bitrate=2000 \\
      ! rtph264pay config-interval=1 pt=96 \\
      ! udpsink host=<GCS_IP> port=5620

  hoac dung raspivid:
    raspivid -n -t 0 -w 640 -h 480 -fps 30 -b 2000000 -pf baseline -o - \\
      | gst-launch-1.0 fdsrc ! h264parse ! rtph264pay config-interval=1 ! udpsink host=<GCS_IP> port=5620

GCS nhan (video_receiver):
  GStreamer pipeline: udpsrc port=5620 ! application/x-rtp,payload=96
    ! rtph264depay ! h264parse ! avdec_h264 ! videoconvert ! appsink
  Fallback FFmpeg:   udp://@:5620

Auto-reconnect khi mat ket noi RTSP/UDP.
Resize frame xuong target resolution truoc khi emit signal.

Tich hop:
  receiver = VideoReceiver(
      source_type=VideoSource.UDP_H264,
      url_or_index=5620,
      target_fps=30, target_w=640, target_h=480,
  )
  receiver.sig_frame.connect(my_slot)
  receiver.sig_connected.connect(on_connected)
  receiver.sig_error.connect(on_error)
  receiver.start()
  ...
  receiver.stop()
"""


from __future__ import annotations

import threading
import time
from enum import Enum
from typing import Optional, Union

import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_RTSP_RECONNECT_DELAY_S: float = 2.0
"""Seconds to wait between RTSP reconnection attempts."""

_RTSP_MAX_RECONNECTS: int = 10
"""Maximum consecutive RTSP reconnection attempts before giving up."""

_OPEN_TIMEOUT_S: float = 5.0
"""Seconds to wait for cv2.VideoCapture to open successfully."""

_CAP_OPEN_POLL_S: float = 0.1
"""Polling interval while waiting for VideoCapture.open()."""

_SOURCE_SWITCH_RETRY_S: float = 1.0
"""Seconds to wait between retries when switching source fails."""

_SOURCE_SWITCH_MAX_RETRIES: int = 5
"""Maximum retries when switching to a new source fails."""


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class VideoSource(str, Enum):
    """Supported video source types."""

    UDP_H264 = "udp_h264"
    """UDP H.264 RTP stream tu ROV (port 5620). Dung GStreamer hoac FFmpeg."""

    RTSP = "rtsp"
    """RTSP network stream (e.g. from Raspberry Pi / GStreamer)."""

    WEBCAM = "webcam"
    """Local USB / built-in camera, addressed by integer index."""

    FILE = "file"
    """Local video file - useful for offline testing."""


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------


class VideoReceiver(QThread):
    """
    Background thread that continuously reads frames from a video source
    and emits them as numpy arrays.

    Supports live RTSP streams, local webcams, and video files.
    RTSP sources are automatically reconnected on failure.

    Signals
    -------
    sig_frame : np.ndarray
        Emitted for every successfully decoded frame (BGR, uint8).
    sig_connected : bool
        ``True`` when the source opens successfully, ``False`` when it closes
        or fails.
    sig_error : str
        Human-readable error / warning messages.
    """

    sig_frame = pyqtSignal(np.ndarray)
    sig_connected = pyqtSignal(bool)
    sig_error = pyqtSignal(str)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def __init__(
        self,
        source_type: VideoSource,
        url_or_index: Union[str, int],
        target_fps: int = 30,
        target_w: int = 640,
        target_h: int = 480,
        parent=None,
    ) -> None:
        """
        Parameters
        ----------
        source_type : VideoSource
            Where to get video from - RTSP, WEBCAM, or FILE.
        url_or_index : str | int
            RTSP URL string, webcam integer index, or file path string.
        target_fps : int
            Target frame rate for the read loop (default 30).
        target_w : int
            Output frame width in pixels (default 640).
        target_h : int
            Output frame height in pixels (default 480).
        parent : QObject | None
            Optional Qt parent.
        """
        super().__init__(parent)

        self._lock = threading.Lock()

        # Source configuration (protected by _lock for set_source)
        self._source_type: VideoSource = source_type
        self._url_or_index: Union[str, int] = url_or_index

        # Output parameters
        self._target_fps: int = max(1, target_fps)
        self._target_w: int = max(1, target_w)
        self._target_h: int = max(1, target_h)

        # Control flags
        self._running: bool = False
        self._source_changed: bool = False  # signals run() to reinitialise cap

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_source(
        self,
        source_type: VideoSource,
        url_or_index: Union[str, int],
    ) -> None:
        """
        Switch to a different video source while the thread is running.

        Thread-safe: can be called from the GUI thread at any time.
        The change takes effect on the next reconnection cycle inside
        ``run()``.

        Parameters
        ----------
        source_type : VideoSource
            New source type.
        url_or_index : str | int
            New URL / index / path.
        """
        with self._lock:
            self._source_type = source_type
            self._url_or_index = url_or_index
            self._source_changed = True

    def stop(self) -> None:
        """
        Signal the thread to exit and wait for it to finish.

        Blocks the caller for up to 3 seconds; if the thread has not
        stopped by then it is forcibly terminated.
        """
        self._running = False
        if not self.wait(3000):  # 3-second graceful timeout
            self.terminate()
            self.wait()

    # ------------------------------------------------------------------
    # QThread entry point
    # ------------------------------------------------------------------

    def run(self) -> None:
        """
        Main thread body.

        Lazily imports ``cv2`` so that the module can be *imported* even
        when OpenCV is not installed (the error is only surfaced at
        runtime when video is actually needed).
        """
        # ---- Lazy-load cv2 -------------------------------------------
        try:
            import cv2  # noqa: PLC0415
        except ImportError:
            self.sig_error.emit(
                "opencv not installed - run: pip install opencv-python"
            )
            return

        self._running = True
        frame_interval_s: float = 1.0 / self._target_fps

        while self._running:
            # Snapshot current source config (thread-safe)
            with self._lock:
                source_type = self._source_type
                url_or_index = self._url_or_index
                self._source_changed = False

            cap = self._open_capture(cv2, source_type, url_or_index)

            if cap is None or not cap.isOpened():
                # Could not open at all
                if not self._running:
                    break
                self.sig_connected.emit(False)

                # Kiểm tra xem có đang chờ chuyển nguồn không
                with self._lock:
                    if self._source_changed:
                        continue   # Có nguồn mới → thử lại ngay

                # Mọi loại nguồn đều retry (không bail out nữa)
                self.sig_error.emit(
                    f"Không thể mở nguồn: {url_or_index!r} — thử lại sau {_SOURCE_SWITCH_RETRY_S}s..."
                )
                self._interruptible_sleep(cv2, _SOURCE_SWITCH_RETRY_S)
                continue

            self.sig_connected.emit(True)
            reconnect_count: int = 0

            # ---- Inner read loop ------------------------------------
            while self._running:
                # Check if source was switched from outside
                with self._lock:
                    changed = self._source_changed

                if changed:
                    print(
                        "[VideoReceiver] Source changed - reinitialising capture."
                    )
                    break  # Break inner loop → outer loop reopens

                t_start = time.monotonic()
                ret, frame = cap.read()

                if not ret or frame is None:
                    # Read failure — release cap ngay lập tức
                    self._safe_release(cap)
                    cap = None
                    self.sig_connected.emit(False)

                    # Kiểm tra nguồn có đổi không
                    with self._lock:
                        if self._source_changed:
                            break  # → outer loop sẽ mở nguồn mới

                    if source_type is VideoSource.RTSP or source_type is VideoSource.UDP_H264:
                        reconnect_count += 1
                        if reconnect_count > _RTSP_MAX_RECONNECTS:
                            self.sig_error.emit(
                                f"RTSP: exceeded {_RTSP_MAX_RECONNECTS} "
                                "reconnect attempts - giving up."
                            )
                            # KHÔNG đặt _running = False, để có thể chuyển nguồn mới
                            break

                        print(
                            f"[VideoReceiver] RTSP read failed "
                            f"(attempt {reconnect_count}/{_RTSP_MAX_RECONNECTS}). "
                            f"Retrying in {_RTSP_RECONNECT_DELAY_S:.1f}s…"
                        )
                        self._interruptible_sleep(cv2, _RTSP_RECONNECT_DELAY_S)

                        cap = self._open_capture(cv2, source_type, url_or_index)
                        if cap is not None and cap.isOpened():
                            reconnect_count = 0
                            self.sig_connected.emit(True)
                            print("[VideoReceiver] RTSP reconnected successfully.")
                        continue  # restart inner loop with new cap

                    elif source_type is VideoSource.FILE:
                        # Video file kết thúc → loop lại từ đầu thay vì die
                        self.sig_error.emit(
                            f"Video file ended: {url_or_index!r} — restarting..."
                        )
                        self._interruptible_sleep(cv2, 0.5)
                        break  # → outer loop sẽ reopen cùng file

                    else:
                        # Webcam / other — retry mở lại
                        self.sig_error.emit(
                            f"Stream ended for source: {url_or_index!r} — retrying..."
                        )
                        self._interruptible_sleep(cv2, _SOURCE_SWITCH_RETRY_S)
                        break  # → outer loop reopens

                else:
                    reconnect_count = 0  # Reset on successful read

                # ---- Resize and emit --------------------------------
                resized = self._resize_frame(cv2, frame)
                self.sig_frame.emit(resized)

                # ---- Frame-rate throttling --------------------------
                elapsed = time.monotonic() - t_start
                sleep_s = frame_interval_s - elapsed
                if sleep_s > 0:
                    # Use cv2.waitKey for accurate multimedia timing;
                    # fall back to time.sleep for headless environments.
                    time.sleep(sleep_s)

            # End of inner loop — release capture an toàn
            self._safe_release(cap)
            cap = None

        # Thread is exiting
        self.sig_connected.emit(False)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _safe_release(self, cap) -> None:
        """
        Release cv2.VideoCapture an toàn, không block GUI.
        Đặc biệt quan trọng cho DirectShow (webcam Windows).
        """
        if cap is None:
            return
        try:
            if cap.isOpened():
                cap.release()
        except Exception as exc:
            print(f"[VideoReceiver] Warning during cap.release(): {exc}")

    def _open_capture(
        self,
        cv2,
        source_type: VideoSource,
        url_or_index: Union[str, int],
    ):
        """
        Create and configure a ``cv2.VideoCapture`` for the given source.

        Returns the opened capture object, or ``None`` on failure.

        Parameters
        ----------
        cv2 :
            The imported ``cv2`` module (passed in to avoid re-importing).
        source_type : VideoSource
            Source kind.
        url_or_index : str | int
            URL string, webcam index, or file path.
        """
        try:
            if source_type is VideoSource.UDP_H264:
                # ── UDP H.264 RTP stream (ROV → GCS) ──────────────────
                port = int(url_or_index) if str(url_or_index).isdigit() else 5620
                # Thử GStreamer pipeline trước (latency thấp hơn)
                gst_pipeline = (
                    f"udpsrc port={port} caps=\"application/x-rtp,media=video,"
                    f"clock-rate=90000,encoding-name=H264,payload=96\" "
                    f"! rtph264depay ! h264parse ! avdec_h264 "
                    f"! videoconvert ! video/x-raw,format=BGR "
                    f"! appsink drop=1 max-buffers=1 sync=false"
                )
                cap = cv2.VideoCapture(gst_pipeline, cv2.CAP_GSTREAMER)
                if not cap.isOpened():
                    # Fallback: FFmpeg UDP
                    print(
                        "[VideoReceiver] GStreamer unavailable - "
                        f"falling back to FFmpeg udp://@:{port}"
                    )
                    ffmpeg_url = f"udp://@:{port}"
                    cap = cv2.VideoCapture(ffmpeg_url, cv2.CAP_FFMPEG)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            elif source_type is VideoSource.RTSP:
                # Use FFMPEG backend for RTSP - most reliable cross-platform
                cap = cv2.VideoCapture(str(url_or_index), cv2.CAP_FFMPEG)
                # Keep internal buffer at 1 frame to minimise latency
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            elif source_type is VideoSource.WEBCAM:
                index = int(url_or_index)
                # Try CAP_DSHOW for faster/reliable capture on Windows
                cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
                if not cap.isOpened():
                    cap = cv2.VideoCapture(index)
                # Request desired resolution from the driver
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._target_w)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._target_h)
                cap.set(cv2.CAP_PROP_FPS, self._target_fps)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            elif source_type is VideoSource.FILE:
                path = str(url_or_index)
                if not path:
                    self.sig_error.emit("Video file path is empty!")
                    return None
                import os
                if not os.path.isfile(path):
                    self.sig_error.emit(f"Video file not found: {path}")
                    return None
                cap = cv2.VideoCapture(path)

            else:
                self.sig_error.emit(f"Unknown VideoSource type: {source_type!r}")
                return None

            # Brief open-check with timeout
            deadline = time.monotonic() + _OPEN_TIMEOUT_S
            while not cap.isOpened() and time.monotonic() < deadline:
                # Kiểm tra source_changed trong lúc chờ
                with self._lock:
                    if self._source_changed:
                        cap.release()
                        return None
                time.sleep(_CAP_OPEN_POLL_S)

            if not cap.isOpened():
                cap.release()
                self.sig_error.emit(
                    f"Timed out opening source: {url_or_index!r}"
                )
                return None

            return cap

        except Exception as exc:  # noqa: BLE001
            self.sig_error.emit(f"Error opening capture: {exc}")
            return None

    def _resize_frame(self, cv2, frame: np.ndarray) -> np.ndarray:
        """
        Resize *frame* to the target resolution if necessary.

        Uses ``cv2.INTER_LINEAR`` for speed; falls back to the original
        frame if resizing fails.

        Parameters
        ----------
        cv2 :
            Imported ``cv2`` module.
        frame : np.ndarray
            Raw BGR frame from ``cap.read()``.

        Returns
        -------
        np.ndarray
            Resized (or original, on failure) BGR frame.
        """
        h, w = frame.shape[:2]
        if w == self._target_w and h == self._target_h:
            return frame  # Already correct size - no copy needed
        try:
            return cv2.resize(
                frame,
                (self._target_w, self._target_h),
                interpolation=cv2.INTER_LINEAR,
            )
        except Exception as exc:  # noqa: BLE001
            self.sig_error.emit(f"Frame resize failed: {exc}")
            return frame

    def _interruptible_sleep(self, cv2, duration_s: float) -> None:
        """
        Sleep for *duration_s* seconds in small increments so that
        ``self._running = False`` or ``self._source_changed`` is noticed
        promptly during waits.

        Parameters
        ----------
        cv2 :
            Imported ``cv2`` module (unused but kept for signature symmetry).
        duration_s : float
            Total sleep duration in seconds.
        """
        end = time.monotonic() + duration_s
        while self._running and time.monotonic() < end:
            # Thoát sleep sớm nếu có lệnh chuyển nguồn
            with self._lock:
                if self._source_changed:
                    return
            time.sleep(0.05)
