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
# Dedicated Real-time Frame Grabber Thread (Zero-Latency RTSP / Live Stream)
# ---------------------------------------------------------------------------


class _LiveStreamGrabber(threading.Thread):
    """
    Dedicated background worker that continuously drains frames from cv2.VideoCapture.

    Why this is essential for RTSP / live network streams:
    OpenCV's FFmpeg demuxer buffers packets/frames in an internal queue whenever read()
    is not called at the exact camera broadcast rate. If the main thread or GUI spends
    even a few milliseconds rendering, frames accumulate in the buffer, causing latency
    to drift from milliseconds to several seconds over time.

    By running cap.read() continuously in this tight loop:
    1. The OS network socket and FFmpeg internal packet buffer are kept at 0 queue size.
    2. Only the single latest frame is retained in memory.
    3. Intermediate unread frames are dropped immediately before reaching Qt.
    4. Latency is locked to real-time (< 100ms) with zero frame stutter or drift.
    """

    def __init__(self, cap) -> None:
        super().__init__(daemon=True)
        self.cap = cap
        self.running: bool = True
        self.lock = threading.Lock()
        self.latest_frame: Optional[np.ndarray] = None
        self.has_new_frame: bool = False
        self.read_failed: bool = False

    def run(self) -> None:
        consecutive_fails: int = 0
        while self.running:
            if self.cap is None or not self.cap.isOpened():
                self.read_failed = True
                break

            # 1. Grab nhanh để xả sạch socket/FFmpeg packet buffer (<0.2ms)
            if not self.cap.grab():
                consecutive_fails += 1
                if consecutive_fails > 30:
                    self.read_failed = True
                    break
                time.sleep(0.002)
                continue

            # 2. Decode khung hình mới nhất tức thì
            ret, frame = self.cap.retrieve()
            if not ret or frame is None:
                consecutive_fails += 1
                if consecutive_fails > 30:
                    self.read_failed = True
                    break
                time.sleep(0.002)
                continue

            consecutive_fails = 0
            with self.lock:
                self.latest_frame = frame
                self.has_new_frame = True

    def get_latest_frame(self) -> Optional[np.ndarray]:
        with self.lock:
            if not self.has_new_frame:
                return None
            self.has_new_frame = False
            return self.latest_frame

    def stop(self) -> None:
        self.running = False


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
            Output frame width in pixels (default 640). 0 = preserve native resolution.
        target_h : int
            Output frame height in pixels (default 480). 0 = preserve native resolution.
        parent : QObject | None
            Optional Qt parent.
        """
        super().__init__(parent)

        self._lock = threading.Lock()

        # Source configuration (protected by _lock for set_source)
        self._source_type: VideoSource = source_type
        self._url_or_index: Union[str, int] = url_or_index

        # Output parameters (0 = native resolution, no downscaling)
        self._target_fps: int = max(1, target_fps)
        self._target_w: int = max(0, target_w)
        self._target_h: int = max(0, target_h)

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
            if source_type in (VideoSource.RTSP, VideoSource.UDP_H264, VideoSource.WEBCAM):
                # ── Luồng mạng / Camera thực: sử dụng Dedicated Fast Grabber để triệt tiêu độ trễ ──
                grabber = _LiveStreamGrabber(cap)
                grabber.start()
                last_emit_t: float = 0.0
                min_interval: float = 1.0 / max(1, self._target_fps) if self._target_fps > 0 else 0.0

                while self._running:
                    # Kiểm tra xem có chuyển nguồn video từ bên ngoài không
                    with self._lock:
                        changed = self._source_changed

                    if changed:
                        print("[VideoReceiver] Video source changed - recreating stream.")
                        grabber.stop()
                        grabber.join(timeout=0.3)
                        break

                    if grabber.read_failed:
                        grabber.stop()
                        grabber.join(timeout=0.3)
                        self._safe_release(cap)
                        cap = None
                        self.sig_connected.emit(False)

                        with self._lock:
                            if self._source_changed:
                                break

                        reconnect_count += 1
                        if reconnect_count % 5 == 1:
                            self.sig_error.emit(
                                f"Waiting for video ({url_or_index}). Reconnecting (attempt {reconnect_count})..."
                            )

                        print(
                            f"[VideoReceiver] Read failed (retry {reconnect_count}). Reconnecting in {_RTSP_RECONNECT_DELAY_S:.1f}s..."
                        )
                        self._interruptible_sleep(cv2, _RTSP_RECONNECT_DELAY_S)

                        cap = self._open_capture(cv2, source_type, url_or_index)
                        if cap is not None and cap.isOpened():
                            reconnect_count = 0
                            self.sig_connected.emit(True)
                            print("[VideoReceiver] Video reconnected successfully.")
                            grabber = _LiveStreamGrabber(cap)
                            grabber.start()
                        continue

                    # Throttle FPS nếu cấu hình (VD: luồng AI ngầm chạy ở 10-15 FPS để tối ưu CPU)
                    now_t = time.monotonic()
                    if min_interval > 0 and (now_t - last_emit_t) < min_interval:
                        time.sleep(0.002)
                        continue

                    # Lấy khung hình MỚI NHẤT từ Grabber (không tồn đọng buffer trong hàng đợi)
                    frame = grabber.get_latest_frame()
                    if frame is None:
                        time.sleep(0.002)
                        continue

                    last_emit_t = now_t
                    reconnect_count = 0

                    # Resize (nếu cấu hình) và phát signal hiển thị
                    resized = self._resize_frame(cv2, frame)
                    self.sig_frame.emit(resized)

                grabber.stop()
                grabber.join(timeout=0.3)
                self._safe_release(cap)
                cap = None

            else:
                # ── Nguồn Video File (Offline Testing): Đọc tuần tự có throttle FPS ──
                while self._running:
                    with self._lock:
                        changed = self._source_changed

                    if changed:
                        break

                    t_start = time.monotonic()
                    ret, frame = cap.read()

                    if not ret or frame is None:
                        self._safe_release(cap)
                        cap = None
                        self.sig_connected.emit(False)
                        self.sig_error.emit(
                            f"Hết video file: {url_or_index!r} — phát lại từ đầu..."
                        )
                        self._interruptible_sleep(cv2, 0.5)
                        break

                    resized = self._resize_frame(cv2, frame)
                    self.sig_frame.emit(resized)

                    elapsed = time.monotonic() - t_start
                    sleep_s = frame_interval_s - elapsed
                    if sleep_s > 0:
                        time.sleep(sleep_s)

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

    def _is_tcp_port_open(self, host: str, port: int, timeout: float = 0.35) -> bool:
        """Kiểm tra nhanh kết nối TCP tới host:port mà không làm block/treo ứng dụng."""
        try:
            import socket
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except Exception:
            return False

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
                # ── UDP / RTP H.264 Stream (ROV → GCS) ────────
                url_str = str(url_or_index).strip()
                cap = None

                import os
                os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
                    "fflags;nobuffer|"
                    "flags;low_delay|"
                    "framedrop;1"
                )

                if url_str.startswith("http://") or url_str.startswith("https://"):
                    cap = cv2.VideoCapture(url_str)
                else:
                    port = int(url_or_index) if url_str.isdigit() else 5600
                    # Thử lần lượt RTP H.264 (chuẩn BlueOS/QGC) và UDP MPEG-TS
                    endpoints = [
                        f"rtp://0.0.0.0:{port}",
                        f"udp://0.0.0.0:{port}?overrun_nonfatal=1&fifo_size=2097152",
                    ]
                    for ep in endpoints:
                        try:
                            temp_cap = cv2.VideoCapture(ep, cv2.CAP_FFMPEG)
                            if temp_cap is not None:
                                # Chờ tối đa 2.5s để nhận keyframe H.264 đầu tiên
                                end_t = time.monotonic() + 2.5
                                while not temp_cap.isOpened() and time.monotonic() < end_t:
                                    time.sleep(0.05)

                                if temp_cap.isOpened():
                                    cap = temp_cap
                                    print(f"[VideoReceiver] UDP/RTP đã mở thành công trên {ep}")
                                    break
                                else:
                                    self._safe_release(temp_cap)
                        except Exception as e:
                            print(f"[VideoReceiver] UDP open error {ep}: {e}")

                if cap:
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            elif source_type is VideoSource.RTSP:
                # Cấu hình FFmpeg độ trễ cực thấp (<100ms) qua TCP:
                # Ép TCP transport (khớp Cockpit 100%), loại bỏ probesize;32 gây lỗi giải mã SPS/PPS
                import os
                os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
                    "rtsp_transport;udp|"
                    "fflags;nobuffer|"
                    "flags;low_delay|"
                    "max_delay;0|"
                    "buffer_size;65536"
                )
                rtsp_url = str(url_or_index).strip()
                if "?" in rtsp_url and ("fflags=" in rtsp_url or "flags=" in rtsp_url):
                    rtsp_url = rtsp_url.split("?")[0]

                # Danh sách ứng viên URL để tự động bắt đúng luồng camera trên BlueOS/Pi
                candidates = [rtsp_url]
                if "192.168.2.2" in rtsp_url or "8554" in rtsp_url or "8555" in rtsp_url:
                    for fallback_url in [
                        "rtsp://192.168.2.2:8555/cam",
                        "rtsp://192.168.2.2:8554/video",
                        "rtsp://192.168.2.2:8554/cam",
                        "rtsp://192.168.2.2:8554/video_0",
                    ]:
                        if fallback_url not in candidates:
                            candidates.append(fallback_url)

                cap = None
                for cand_url in candidates:
                    try:
                        from urllib.parse import urlparse
                        parsed = urlparse(cand_url)
                        h = parsed.hostname or "192.168.2.2"
                        p = parsed.port or (8555 if "8555" in cand_url else 8554)
                        # Đối với các URL dự phòng, kiểm tra socket 0.8s tránh bị FFmpeg treo
                        if cand_url != rtsp_url and not self._is_tcp_port_open(h, p, timeout=0.8):
                            continue

                        temp_cap = cv2.VideoCapture(cand_url, cv2.CAP_FFMPEG)
                        if temp_cap is not None and temp_cap.isOpened():
                            cap = temp_cap
                            print(f"[VideoReceiver] RTSP connected: {cand_url}")
                            if cand_url != rtsp_url:
                                with self._lock:
                                    self._url_or_index = cand_url
                            break
                        else:
                            self._safe_release(temp_cap)
                    except Exception as e:
                        print(f"[VideoReceiver] RTSP candidate error {cand_url}: {e}")

                if cap is not None:
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

            if cap is None:
                return None

            # Brief open-check with timeout
            deadline = time.monotonic() + _OPEN_TIMEOUT_S
            while cap is not None and not cap.isOpened() and time.monotonic() < deadline:
                # Kiểm tra source_changed trong lúc chờ
                with self._lock:
                    if self._source_changed:
                        self._safe_release(cap)
                        return None
                time.sleep(_CAP_OPEN_POLL_S)

            if cap is None or not cap.isOpened():
                self._safe_release(cap)
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
        frame if resizing fails or target dimensions are 0 (Native mode).

        Parameters
        ----------
        cv2 :
            Imported ``cv2`` module.
        frame : np.ndarray
            Raw BGR frame from ``cap.read()``.

        Returns
        -------
        np.ndarray
            Resized (or original, on failure/native) BGR frame.
        """
        if self._target_w <= 0 or self._target_h <= 0:
            return frame  # Native resolution: không tốn CPU resize
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
