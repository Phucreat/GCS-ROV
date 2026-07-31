"""
input_handler.py - Gamepad / Joystick Controller Worker for GCS ROV
====================================================================
Hỗ trợ cắm-là-chạy (Plug & Play) tất cả các loại tay cầm Gamepad (Xbox 360/One/Series,
PlayStation DualShock/DualSense, Logitech, 8BitDo, tay cầm USB / Bluetooth).

Sơ đồ điều khiển:
  - Left Stick Y: Surge (Tiến / Lùi)
  - Left Stick X: Sway (Băng ngang Trái / Phải)
  - Right Stick X: Yaw (Xoay hướng Trái / Phải)
  - Right Stick Y: Heave (Lặn xuống / Nổi lên)
  - D-Pad: Phím điều hướng nhanh
  - Button A (0): Snapshot (Chụp ảnh)
  - Button B (1): Record Toggle (Bật / Tắt Ghi video MP4)
  - Button X (2): Arm / Disarm Động cơ ROV
  - Button Y (3): Đèn LED Toggle
  - LB / RB (4, 5): Giảm / Tăng tốc độ (Speed Scale)
"""

from __future__ import annotations

import time
from typing import Optional, Dict

from PyQt6.QtCore import QThread, pyqtSignal

# ---------------------------------------------------------------------------
# Lazy Pygame Import Helper
# ---------------------------------------------------------------------------
_pygame = None
_pygame_available: Optional[bool] = None


def _get_pygame():
    global _pygame, _pygame_available
    if _pygame_available is None:
        try:
            import pygame  # type: ignore
            pygame.init()
            pygame.joystick.init()
            _pygame = pygame
            _pygame_available = True
        except Exception:
            _pygame_available = False
    return _pygame if _pygame_available else None


class GamepadWorker(QThread):
    """
    Background worker thread running at ~60Hz polling gamepad axes & buttons.
    Emits Qt Signals to update ROV telemetry and trigger actions.
    """

    sig_gamepad_connected = pyqtSignal(bool, str)   # (connected, gamepad_name)
    sig_axis_moved = pyqtSignal(dict)               # {surge, sway, heave, yaw, roll, pitch}
    sig_button_pressed = pyqtSignal(str)            # action_name

    def __init__(
        self,
        deadzone: float = 0.15,
        poll_interval_ms: int = 20,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._deadzone: float = max(0.05, min(0.5, deadzone))
        self._poll_interval_s: float = max(0.01, poll_interval_ms / 1000.0)
        self._running: bool = False
        self._connected: bool = False
        self._joystick_name: str = ""
        self._joystick_obj = None

        # Last emitted ctrl state to avoid redundant signals
        self._last_ctrl = dict(surge=0.0, sway=0.0, heave=0.0, yaw=0.0, roll=0.0, pitch=0.0)
        self._last_buttons: Dict[int, bool] = {}

    def stop(self) -> None:
        self._running = False
        if not self.wait(2000):
            self.terminate()
            self.wait()

    def run(self) -> None:
        pygame = _get_pygame()
        if pygame is None:
            print("[GamepadWorker] Pygame not available — gamepad support disabled.")
            return

        self._running = True
        print("[GamepadWorker] Polling thread started.")

        while self._running:
            try:
                # Pump pygame events to update joystick state
                pygame.event.pump()

                count = pygame.joystick.get_count()

                if count == 0:
                    if self._connected:
                        self._connected = False
                        self._joystick_name = ""
                        self._joystick_obj = None
                        self.sig_gamepad_connected.emit(False, "")
                        print("[GamepadWorker] Gamepad disconnected.")
                    time.sleep(0.5)  # Check for re-connect
                    continue

                # Lock to first active joystick
                if not self._connected or self._joystick_obj is None:
                    try:
                        js = pygame.joystick.Joystick(0)
                        js.init()
                        self._joystick_obj = js
                        self._joystick_name = js.get_name()
                        self._connected = True
                        self.sig_gamepad_connected.emit(True, self._joystick_name)
                        print(f"[GamepadWorker] Connected Gamepad: {self._joystick_name}")
                    except Exception as e:
                        print(f"[GamepadWorker] Error initializing joystick: {e}")
                        time.sleep(1.0)
                        continue

                js = self._joystick_obj

                # Read Axes based on controller type (XInput vs DirectInput)
                num_axes = js.get_numaxes()
                if num_axes >= 6:
                    # Xbox 360 / Xbox One / XInput controller (6 axes)
                    # Axis 0: Left Stick X (Sway)
                    # Axis 1: Left Stick Y (Surge - push up is negative)
                    # Axis 3: Right Stick X (Yaw)
                    # Axis 4: Right Stick Y (Heave - push up is negative)
                    surge = self._apply_deadzone(-js.get_axis(1))
                    sway  = self._apply_deadzone(js.get_axis(0))
                    yaw   = self._apply_deadzone(js.get_axis(3))
                    heave = self._apply_deadzone(-js.get_axis(4))
                elif num_axes >= 4:
                    # Standard 4-axis DirectInput controller
                    surge = self._apply_deadzone(-js.get_axis(1))
                    sway  = self._apply_deadzone(js.get_axis(0))
                    yaw   = self._apply_deadzone(js.get_axis(2))
                    heave = self._apply_deadzone(-js.get_axis(3))
                else:
                    surge = self._apply_deadzone(-js.get_axis(1)) if num_axes > 1 else 0.0
                    sway  = self._apply_deadzone(js.get_axis(0)) if num_axes > 0 else 0.0
                    yaw   = 0.0
                    heave = 0.0

                # Check D-Pad (Hat 0)
                if js.get_numhats() > 0:
                    hat_x, hat_y = js.get_hat(0)
                    if hat_y == 1:
                        surge = 1.0
                    elif hat_y == -1:
                        surge = -1.0
                    if hat_x == 1:
                        sway = 1.0
                    elif hat_x == -1:
                        sway = -1.0

                ctrl = dict(
                    surge=round(surge, 3),
                    sway=round(sway, 3),
                    heave=round(heave, 3),
                    yaw=round(yaw, 3),
                    roll=0.0,
                    pitch=0.0,
                )

                # Emit axis signal continuously if non-zero or when returning to zero
                is_active = any(abs(v) > 0.001 for v in ctrl.values())
                was_active = any(abs(v) > 0.001 for v in self._last_ctrl.values())
                if is_active or was_active or ctrl != self._last_ctrl:
                    self._last_ctrl = ctrl
                    self.sig_axis_moved.emit(ctrl)

                # Read Buttons
                num_buttons = js.get_numbuttons()
                for b_idx in range(num_buttons):
                    is_down = js.get_button(b_idx)
                    was_down = self._last_buttons.get(b_idx, False)

                    if is_down and not was_down:
                        # Rising edge (button press event)
                        action = self._map_button_action(b_idx)
                        if action:
                            self.sig_button_pressed.emit(action)

                    self._last_buttons[b_idx] = is_down

            except Exception as exc:
                print(f"[GamepadWorker] Error in poll loop: {exc}")
                self._connected = False
                time.sleep(0.5)

            time.sleep(self._poll_interval_s)

    def _apply_deadzone(self, val: float) -> float:
        """Apply deadzone threshold to analog axis values."""
        if abs(val) < self._deadzone:
            return 0.0
        # Re-scale [deadzone, 1.0] -> [0.0, 1.0]
        sign = 1.0 if val > 0 else -1.0
        scaled = (abs(val) - self._deadzone) / (1.0 - self._deadzone)
        return sign * min(1.0, scaled)

    def _map_button_action(self, b_idx: int) -> Optional[str]:
        """
        Map button index to action string.
        0: A / Cross -> Snapshot
        1: B / Circle -> Record Toggle
        2: X / Square -> Arm Toggle
        3: Y / Triangle -> Lights Toggle
        4: LB -> Speed Down
        5: RB -> Speed Up
        6: Back -> Emergency Stop
        7: Start -> Arm Toggle
        """
        mapping = {
            0: "snapshot",
            1: "record",
            2: "arm",
            3: "lights",
            4: "speed_down",
            5: "speed_up",
            6: "emergency_stop",
            7: "arm",
        }
        return mapping.get(b_idx)
