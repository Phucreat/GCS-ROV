"""
ue5_udp_sender.py - High-Speed UDP Telemetry & Environment Sync for Unreal Engine 5
===================================================================================
Chuyển tiếp tọa độ 6-DOF ROV [x, y, z, roll, pitch, yaw] tốc độ 60Hz và truyền phát
lệnh biến đổi môi trường (Level Streaming, Độ đục nước, Ánh sáng theo độ sâu)
sang Unreal Engine 5 Digital Twin qua cổng UDP (Mặc định 8888).
"""

from __future__ import annotations

import json
import socket
import threading
import time
from typing import Any, Dict, Optional


class UE5UDPSender:
    """
    High-performance non-blocking UDP telemetry & environment controller for Unreal Engine 5.
    """

    def __init__(
        self,
        target_ip: str = "127.0.0.1",
        target_port: int = 8888,
        send_rate_hz: int = 60,
    ) -> None:
        self.target_ip = target_ip
        self.target_port = target_port
        self.send_rate_hz = send_rate_hz
        self._interval = 1.0 / send_rate_hz

        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # Current telemetry buffer state
        self._telemetry_state: Dict[str, Any] = {
            "cmd": "POSE_UPDATE",
            "timestamp": time.time(),
            "x": 0.0,
            "y": 0.0,
            "z": 0.0,
            "roll": 0.0,
            "pitch": 0.0,
            "yaw": 0.0,
            "lights_pct": 100,
            "armed": False,
            "mode": "ALT_HOLD",
            "depth_m": 0.0,
            "turbidity": 0.2,
        }

    def start(self) -> None:
        """Start background 60Hz UDP telemetry sender thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._send_loop, daemon=True)
        self._thread.start()
        print(f"[UE5UDPSender] 60Hz UDP Telemetry loop started for UE5 at {self.target_ip}:{self.target_port}")

    def stop(self) -> None:
        """Stop background sender thread."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        try:
            self._socket.close()
        except Exception:
            pass
        print("[UE5UDPSender] Stopped.")

    def update_pose(
        self,
        x: float,
        y: float,
        z: float,
        roll: float,
        pitch: float,
        yaw: float,
        lights_pct: int = 100,
        armed: bool = False,
        mode: str = "ALT_HOLD",
        depth_m: float = 0.0,
    ) -> None:
        """Thread-safe update of 6-DOF ROV pose."""
        with self._lock:
            self._telemetry_state["timestamp"] = time.time()
            self._telemetry_state["x"] = round(float(x), 3)
            self._telemetry_state["y"] = round(float(y), 3)
            self._telemetry_state["z"] = round(float(z), 3)
            self._telemetry_state["roll"] = round(float(roll), 2)
            self._telemetry_state["pitch"] = round(float(pitch), 2)
            self._telemetry_state["yaw"] = round(float(yaw), 2)
            self._telemetry_state["lights_pct"] = int(lights_pct)
            self._telemetry_state["armed"] = bool(armed)
            self._telemetry_state["mode"] = str(mode)
            self._telemetry_state["depth_m"] = round(float(depth_m), 2)

    def send_environment_preset(self, map_preset: str) -> bool:
        """
        Send Level Streaming command to UE5.
        Presets: 'POOL', 'RESERVOIR', 'OFFSHORE_OCEAN', 'SHIPWRECK'
        """
        payload = {
            "cmd": "CHANGE_MAP",
            "map_preset": map_preset.upper(),
            "timestamp": time.time(),
        }
        return self._send_packet(payload)

    def send_water_turbidity(self, turbidity_val: float) -> bool:
        """
        Send Water Turbidity command to UE5 (0.0 = crystal clear, 1.0 = muddy/foggy).
        Adjusts Exponential Height Fog & Water Absorption in UE5 Blueprint.
        """
        val = max(0.0, min(1.0, float(turbidity_val)))
        with self._lock:
            self._telemetry_state["turbidity"] = round(val, 2)
        payload = {
            "cmd": "SET_TURBIDITY",
            "turbidity": round(val, 2),
            "timestamp": time.time(),
        }
        return self._send_packet(payload)

    def send_depth_lighting_sync(self, depth_m: float, auto_spotlight: bool = True) -> bool:
        """
        Send Depth & Solar Lighting Sync command to UE5.
        Dimmers Directional Sunlight as depth increases, and triggers Subsea Spotlight.
        """
        depth = max(0.0, float(depth_m))
        # Solar attenuation factor (1.0 at surface, 0.05 at >30m)
        solar_factor = max(0.02, 1.0 - (depth / 35.0))
        payload = {
            "cmd": "SET_DEPTH_LIGHTING",
            "depth_m": round(depth, 2),
            "solar_factor": round(solar_factor, 3),
            "auto_spotlight": auto_spotlight,
            "timestamp": time.time(),
        }
        return self._send_packet(payload)

    def _send_packet(self, data_dict: dict) -> bool:
        """Send a JSON payload over UDP."""
        try:
            raw_bytes = json.dumps(data_dict).encode("utf-8")
            self._socket.sendto(raw_bytes, (self.target_ip, self.target_port))
            return True
        except Exception as exc:
            print(f"[UE5UDPSender] Packet send error: {exc}")
            return False

    def _send_loop(self) -> None:
        """60Hz continuous UDP telemetry broadcast loop."""
        while self._running:
            start_t = time.time()
            with self._lock:
                packet = dict(self._telemetry_state)

            self._send_packet(packet)

            elapsed = time.time() - start_t
            sleep_t = max(0.001, self._interval - elapsed)
            time.sleep(sleep_t)
