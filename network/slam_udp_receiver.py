"""
slam_udp_receiver.py - SLAM Point Cloud UDP Receiver Thread
============================================================
Lắng nghe cổng UDP riêng (mặc định 5010) để nhận đám mây điểm
từ thuật toán SLAM chạy dưới tàu (ORB-SLAM3 / RTAB-Map).
Không dùng MAVLink để tránh nghẽn băng thông.

Protocol (JSON hoặc Binary):
  JSON : {"pts": [[x,y,z], ...], "ts": timestamp}
  Binary: 4 bytes N_points + N * 12 bytes (3x float32)
"""
import json
import socket
import struct
import time
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal


class SLAMUDPReceiver(QThread):
    """
    Thread lắng nghe UDP nhận point cloud từ SLAM node dưới tàu.
    Emit sig_slam_points mỗi khi nhận được batch mới.
    """

    sig_slam_points = pyqtSignal(object)   # np.ndarray (N, 3)

    def __init__(self, host: str = "0.0.0.0", port: int = 5010,
                 parent=None):
        super().__init__(parent)
        self.host     = host
        self.port     = port
        self._running = False
        self._sock    = None

    def start_worker(self):
        self._running = True
        self.start()

    def stop_worker(self):
        self._running = False
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
        self.quit()
        self.wait(2000)

    def run(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.settimeout(1.0)
        try:
            self._sock.bind((self.host, self.port))
            print(f"[SLAM UDP] Listening on {self.host}:{self.port}")
        except Exception as e:
            print(f"[SLAM UDP] Bind error: {e}")
            return

        while self._running:
            try:
                data, addr = self._sock.recvfrom(65535)
                pts = self._parse(data)
                if pts is not None and len(pts) > 0:
                    self.sig_slam_points.emit(pts)
            except socket.timeout:
                continue
            except Exception as e:
                if self._running:
                    print(f"[SLAM UDP] Receive error: {e}")
                break

    def _parse(self, data: bytes) -> np.ndarray:
        """Thử parse JSON, nếu lỗi thì thử Binary."""
        try:
            # JSON mode
            obj = json.loads(data.decode('utf-8'))
            pts = np.array(obj["pts"], dtype=np.float32)
            return pts
        except (json.JSONDecodeError, UnicodeDecodeError, KeyError):
            pass
        try:
            # Binary mode: N (int32) + N*3 float32
            n = struct.unpack_from('<I', data, 0)[0]
            if 4 + n * 12 <= len(data):
                flat = struct.unpack_from(f'<{n*3}f', data, 4)
                return np.array(flat, dtype=np.float32).reshape(n, 3)
        except Exception:
            pass
        return None
