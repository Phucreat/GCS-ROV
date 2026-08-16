"""
ue5_auto_launcher.py - Commercial One-Click Auto-Launcher for Unreal Engine 5 Simulator
========================================================================================
Quản lý tự động khởi chạy file thực thi mô phỏng (.exe) của Unreal Engine 5 và máy chủ
Signaling Server ngầm dưới nền. Đảm bảo trải nghiệm 0-Config cho người dùng cuối:
- Tự động phát hiện file .exe mô phỏng trong thư mục `sim/`, `ue5_sim/` hoặc cài đặt.
- Tự động kích hoạt luồng background process và mở cổng Pixel Streaming WebRTC.
- Tự động đóng ngầm process UE5 khi thoát ứng dụng GCS.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
from typing import Optional, List


class UE5AutoLauncher:
    """
    Commercial Zero-Config Auto-Launcher for Unreal Engine 5 Standalone Simulators.
    """

    DEFAULT_SEARCH_PATHS = [
        "sim/ROV_Subsea_Sim.exe",
        "sim/Subsea_Sim.exe",
        "ue5_sim/ROV_Subsea_Sim.exe",
        "ue5/ROV_Subsea_Sim.exe",
        "bin/ue5/ROV_Subsea_Sim.exe",
        "sim/SignallingWebServer/platform_scripts/cmd/run.bat",
    ]

    def __init__(self, custom_exe_path: str = "", web_port: int = 80) -> None:
        self.custom_exe_path = custom_exe_path
        self.web_port = web_port
        self._process: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()

    def discover_exe_path(self) -> str:
        """Find valid UE5 executable in custom path or default search directories."""
        if self.custom_exe_path and os.path.exists(self.custom_exe_path):
            return os.path.abspath(self.custom_exe_path)

        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for rel_p in self.DEFAULT_SEARCH_PATHS:
            abs_p = os.path.join(base_dir, rel_p)
            if os.path.exists(abs_p):
                return abs_p

        return ""

    def is_server_listening(self, host: str = "127.0.0.1", port: int = 80) -> bool:
        """Check if WebRTC signaling server is listening on target HTTP port."""
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except (socket.timeout, ConnectionRefusedError, OSError):
            return False

    def launch_simulator(self, exe_path: str = "") -> bool:
        """
        Launch the UE5 standalone executable in background with Pixel Streaming flags.
        """
        target_path = exe_path or self.discover_exe_path()
        if not target_path or not os.path.exists(target_path):
            print(f"[UE5AutoLauncher] Executable not found at: '{target_path}'")
            return False

        if self.is_server_listening(port=self.web_port):
            print(f"[UE5AutoLauncher] Signaling server is ALREADY listening on port {self.web_port}.")
            return True

        with self._lock:
            if self._process and self._process.poll() is None:
                print("[UE5AutoLauncher] UE5 process is already running.")
                return True

            try:
                cmd: List[str] = [target_path]
                # If it's a standalone .exe, pass standard Unreal Engine Pixel Streaming CLI flags
                if target_path.lower().endswith(".exe"):
                    cmd.extend([
                        "-AudioMixer",
                        "-PixelStreamingIP=127.0.0.1",
                        f"-PixelStreamingPort={self.web_port}",
                        "-RenderOffscreen",
                        "-ResX=1280",
                        "-ResY=720",
                        "-windowed"
                    ])

                print(f"[UE5AutoLauncher] Launching background UE5 simulator: {' '.join(cmd)}")
                self._process = subprocess.Popen(
                    cmd,
                    cwd=os.path.dirname(target_path),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                )
                return True
            except Exception as exc:
                print(f"[UE5AutoLauncher] Failed to launch UE5 process: {exc}")
                return False

    def stop_simulator(self) -> None:
        """Terminate the background UE5 process cleanly."""
        with self._lock:
            if self._process and self._process.poll() is None:
                print("[UE5AutoLauncher] Terminating background UE5 process...")
                try:
                    self._process.terminate()
                    self._process.wait(timeout=2.0)
                except Exception:
                    try:
                        self._process.kill()
                    except Exception:
                        pass
                self._process = None
                print("[UE5AutoLauncher] UE5 process terminated.")
