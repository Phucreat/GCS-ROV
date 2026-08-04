"""
ipc_bus.py - ZeroMQ & Qt Signal IPC Event Bus
=============================================
Quản lý luồng giao tiếp bất đồng bộ đa tiến trình (Asynchronous Multi-Process IPC)
và đa luồng (Multi-Threading) giữa:
  - Task 1: CV Engine Process
  - Task 2: Voice Co-Pilot Agent Process (STT -> SLM -> TTS)
  - Main GCS PyQt6 UI Thread
"""

from __future__ import annotations

import json
import threading
import time
from typing import Callable, Dict, List, Optional

try:
    from PyQt6.QtCore import QObject, pyqtSignal
except ImportError:
    from PyQt5.QtCore import QObject, pyqtSignal

# ZeroMQ Lazy Import
_zmq = None
try:
    import zmq
    _zmq = zmq
except ImportError:
    _zmq = None


class IPCBus(QObject):
    """
    Unified Event Bus supporting Qt Signals for in-process thread communication
    and optional ZeroMQ PUB/SUB for multi-process IPC.
    """

    sig_cv_event = pyqtSignal(dict)         # {event_type, class_name, confidence, bbox}
    sig_voice_event = pyqtSignal(dict)      # {text, intent, confidence}
    sig_agent_action = pyqtSignal(dict)     # {action, parameters, requires_confirmation}
    sig_tts_speak = pyqtSignal(str, bool)   # (text, is_emergency)
    sig_system_log = pyqtSignal(str, str)   # (message, level)

    def __init__(
        self,
        pub_port: int = 5555,
        sub_port: int = 5556,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._pub_port = pub_port
        self._sub_port = sub_port
        self._zmq_ctx = None
        self._pub_socket = None
        self._sub_socket = None
        self._running = False
        self._sub_thread: Optional[threading.Thread] = None

        self._init_zmq()

    def _init_zmq(self) -> None:
        """Khởi tạo ZeroMQ sockets nếu có thư viện pyzmq."""
        if _zmq is None:
            print("[IPCBus] pyzmq not installed — running in Qt Signal mode.")
            return

        try:
            self._zmq_ctx = _zmq.Context()
            self._pub_socket = self._zmq_ctx.socket(_zmq.PUB)
            self._pub_socket.bind(f"tcp://127.0.0.1:{self._pub_port}")

            self._sub_socket = self._zmq_ctx.socket(_zmq.SUB)
            self._sub_socket.connect(f"tcp://127.0.0.1:{self._pub_port}")
            self._sub_socket.setsockopt_string(_zmq.SUBSCRIBE, "")

            self._running = True
            self._sub_thread = threading.Thread(target=self._zmq_poll_loop, daemon=True)
            self._sub_thread.start()
            print(f"[IPCBus] ZeroMQ IPC Bus bound to ports {self._pub_port}/{self._pub_port}.")
        except Exception as exc:
            print(f"[IPCBus] Error initializing ZeroMQ: {exc}")

    def publish_cv_event(self, event_type: str, class_name: str, confidence: float, bbox: List[int]) -> None:
        """Phát sự kiện từ CV Module (ví dụ: rò rỉ ống, thợ lặn đến gần)."""
        data = {
            "topic": "CV_EVENT",
            "event_type": event_type,
            "class_name": class_name,
            "confidence": round(confidence, 3),
            "bbox": bbox,
            "timestamp": time.time(),
        }
        self.sig_cv_event.emit(data)
        self._zmq_send("CV_EVENT", data)

    def publish_voice_command(self, raw_text: str, intent: str) -> None:
        """Phát lệnh giọng nói nhận diện từ STT."""
        data = {
            "topic": "VOICE_CMD",
            "raw_text": raw_text,
            "intent": intent,
            "timestamp": time.time(),
        }
        self.sig_voice_event.emit(data)
        self._zmq_send("VOICE_CMD", data)

    def publish_agent_action(self, action: str, params: dict, requires_confirmation: bool = False) -> None:
        """Phát lệnh điều khiển từ Agent Brain."""
        data = {
            "topic": "AGENT_ACTION",
            "action": action,
            "params": params,
            "requires_confirmation": requires_confirmation,
            "timestamp": time.time(),
        }
        self.sig_agent_action.emit(data)
        self._zmq_send("AGENT_ACTION", data)

    def publish_tts(self, text: str, is_emergency: bool = False) -> None:
        """Yêu cầu đọc thông báo TTS."""
        self.sig_tts_speak.emit(text, is_emergency)
        self._zmq_send("TTS_SPEECH", {"text": text, "is_emergency": is_emergency})

    def _zmq_send(self, topic: str, data: dict) -> None:
        if self._pub_socket is not None:
            try:
                msg = f"{topic} {json.dumps(data)}"
                self._pub_socket.send_string(msg, flags=_zmq.NOBLOCK)
            except Exception:
                pass

    def _zmq_poll_loop(self) -> None:
        while self._running and self._sub_socket:
            try:
                if self._sub_socket.poll(timeout=100):
                    raw = self._sub_socket.recv_string()
                    # Handle ZMQ message
                    parts = raw.split(" ", 1)
                    if len(parts) == 2:
                        topic, payload_str = parts
                        payload = json.loads(payload_str)
                        # Route internally if needed
            except Exception:
                pass
            time.sleep(0.01)

    def close(self) -> None:
        self._running = False
        if self._pub_socket:
            self._pub_socket.close()
        if self._sub_socket:
            self._sub_socket.close()
        if self._zmq_ctx:
            self._zmq_ctx.term()
