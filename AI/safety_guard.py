"""
safety_guard.py - Human-in-the-Loop Safety Validator
=====================================================
Nguyên tắc An toàn Sống còn:
  - Lệnh An toàn (Read-Only / Minor): Tự động thực thi ngay.
  - Lệnh Nguy hiểm (Critical Control): BẮT BUỘC hỏi lại qua giọng nói
    ("Xác nhận ngắt động cơ khẩn cấp, đúng không?") và CHỈ thực thi khi
    người lái trả lời "Xác nhận" hoặc bấm nút xác nhận trên UI.
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Dict, Optional, Tuple


class CommandCategory(str, Enum):
    READ_ONLY = "read_only"
    CRITICAL = "critical"


# Categorization Registry
CRITICAL_COMMANDS = {
    "arm_thrusters": "Khởi động toàn bộ động cơ chân vịt (ARM)",
    "disarm_thrusters": "Ngắt toàn bộ động cơ chân vịt (DISARM)",
    "emergency_stop": "Ngắt khẩn cấp toàn bộ hệ thống (EMERGENCY STOP)",
    "open_grappler": "Mở tay gắp cơ khí dưới nước",
    "close_grappler": "Đóng tay gắp cơ khí",
    "set_flight_mode": "Chuyển đổi chế độ lái tự động",
}

READ_ONLY_COMMANDS = {
    "set_lights": "Bật/Tắt điều chỉnh đèn rọi",
    "set_camera_tilt": "Điều chỉnh góc quay camera",
    "get_telemetry": "Đọc thông số cảm biến độ sâu, điện áp, heading",
    "read_sop": "Truy xuất quy trình thao tác chuẩn SOP",
    "take_snapshot": "Chụp ảnh Snapshot",
    "record_toggle": "Bật/Tắt ghi hình MP4",
    "move_forward": "Tiến lên phía trước",
    "move_backward": "Lùi lại",
    "move_left": "Dạt sang trái",
    "move_right": "Dạt sang phải",
    "dive_down": "Lặn xuống sâu",
    "surface_up": "Nổi lên mặt nước",
    "turn_left": "Quay mũi tàu sang trái",
    "turn_right": "Quay mũi tàu sang phải",
    "stop_motion": "Dừng chuyển động chân vịt",
    "speed_up": "Tăng độ nhạy vận tốc",
    "speed_down": "Giảm độ nhạy vận tốc",
    "set_mode": "Chuyển chế độ bay",
    "reset_origin": "Đặt lại gốc toạ độ",
    "goto_depth": "Tự động lặn đến độ sâu mục tiêu",
    "relative_move": "Di chuyển tương đối theo toạ độ thân tàu",
    "execute_pattern": "Chạy bài bay tự động (vòng tròn/quét 360/quét đáy)",
    "return_to_home": "Tự động quay về điểm xuất phát (RTH)",
    "toggle_recording": "Bật/Tắt ghi video màn hình & camera",
    "switch_3d_camera": "Đổi góc nhìn camera 3D",
    "switch_3d_map": "Đổi môi trường bản đồ 3D",
    "switch_telemetry_view": "Đổi giao diện viễn trắc Cockpit / Raw Table",
    "open_gps_map": "Mở bản đồ Google Maps định vị",
    "export_report": "Xuất báo cáo kiểm tra lặn",
}

CONFIRMATION_KEYWORDS = {"xác nhận", "đồng ý", "chấp nhận", "ok", "confirm", "có"}
CANCELLATION_KEYWORDS = {"hủy", "hủy bỏ", "không", "cancel", "stop", "dừng lại"}


class SafetyGuard:
    """
    Manages action authorization, verification tokens, and confirmation state machines.
    """

    def __init__(self, confirmation_timeout_s: float = 15.0) -> None:
        self._timeout_s = confirmation_timeout_s
        self._pending_action: Optional[Dict] = None
        self._pending_timestamp: float = 0.0

    def categorize_action(self, action_name: str) -> CommandCategory:
        """Classify action as READ_ONLY or CRITICAL."""
        if action_name in CRITICAL_COMMANDS:
            return CommandCategory.CRITICAL
        return CommandCategory.READ_ONLY

    def request_execution(
        self, action_name: str, params: dict
    ) -> Tuple[bool, str, Optional[Dict]]:
        """
        Request execution of an action.
        Returns:
          - (allowed_immediately: bool, prompt_message: str, pending_data: Optional[Dict])
        """
        category = self.categorize_action(action_name)

        if category == CommandCategory.READ_ONLY:
            return True, f"Thực thi lệnh an toàn: {action_name}", None

        # Critical Command -> Requires Confirmation
        desc = CRITICAL_COMMANDS.get(action_name, action_name)
        prompt = f"CẢNH BÁO AN TOÀN: Bạn đang yêu cầu '{desc}'. Vui lòng nói 'Xác nhận' hoặc bấm nút trên màn hình để thực thi."

        self._pending_action = {
            "action": action_name,
            "params": params,
            "description": desc,
        }
        self._pending_timestamp = time.time()

        return False, prompt, self._pending_action

    def process_pilot_voice_reply(self, text: str) -> Tuple[bool, str, Optional[Dict]]:
        """
        Process pilot's voice response to a pending confirmation request.
        Returns:
          - (confirmed_and_approved: bool, message: str, action_data: Optional[Dict])
        """
        if not self.has_pending_confirmation():
            return False, "Không có lệnh nào đang chờ xác nhận.", None

        text_clean = text.strip().lower()

        # Check for cancellation
        if any(word in text_clean for word in CANCELLATION_KEYWORDS):
            cancelled = self._pending_action
            self.clear_pending()
            return False, f"Đã hủy lệnh nguy hiểm '{cancelled.get('description')}' theo yêu cầu.", None

        # Check for confirmation
        if any(word in text_clean for word in CONFIRMATION_KEYWORDS):
            approved = self._pending_action
            self.clear_pending()
            return True, f"Đã xác nhận! Đang thực thi lệnh '{approved.get('description')}'.", approved

        return False, "Vui lòng nói rõ 'Xác nhận' để thực hiện hoặc 'Hủy' để bỏ qua.", None

    def has_pending_confirmation(self) -> bool:
        """Check if a pending action is waiting for confirmation and has not expired."""
        if self._pending_action is None:
            return False
        if time.time() - self._pending_timestamp > self._timeout_s:
            self.clear_pending()
            return False
        return True

    def get_pending_action(self) -> Optional[Dict]:
        if self.has_pending_confirmation():
            return self._pending_action
        return None

    def clear_pending(self) -> None:
        self._pending_action = None
        self._pending_timestamp = 0.0
