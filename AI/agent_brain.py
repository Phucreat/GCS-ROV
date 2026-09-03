"""
agent_brain.py - Local SLM & LangGraph Agent Orchestrator (Task 2)
====================================================================
Bộ não Agent Cục bộ (Local SLM & Agent Orchestrator):
  - Model: Qwen2.5-3B-Instruct / Qwen2.5-7B-Instruct qua Ollama (localhost:11434)
  - Framework: LangGraph StateGraph concept & Pydantic Structured Output
  - Tích hợp Safety Guard (Human-in-the-Loop Validation)
  - Tra cứu quy trình thao tác chuẩn SOP (RAG siêu nhẹ)
"""

from __future__ import annotations

import json
import os
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from AI.safety_guard import CommandCategory, SafetyGuard


# ---------------------------------------------------------------------------
# Pydantic Structured Output Model
# ---------------------------------------------------------------------------
class AgentToolCall(BaseModel):
    action: Optional[str] = Field(default="read_sop", description="Tên hàm điều khiển (vd: set_lights, arm_thrusters, emergency_stop, read_sop, take_snapshot)")
    params: Dict[str, Any] = Field(default_factory=dict, description="Tham số truyền cho hàm")


class AgentOutputSchema(BaseModel):
    intent: str = Field(description="Loại ý định: 'control', 'query_telemetry', 'query_sop', 'emergency_alert', 'chat'")
    tool_call: Optional[AgentToolCall] = Field(default=None, description="Thông tin lệnh điều khiển")
    speech_response: str = Field(description="Câu trả lời bằng giọng nói tiếng Việt ngắn gọn để Piper TTS đọc")
    requires_confirmation: bool = Field(default=False, description="True nếu là lệnh nguy hiểm cần phi công xác nhận")


# ---------------------------------------------------------------------------
# Local SLM Engine via Ollama API
# ---------------------------------------------------------------------------
class LocalSLMEngine:
    """
    Connects to local Ollama server running Qwen2.5-3B-Instruct or Qwen2.5-7B-Instruct.
    Falls back to fast rule-based parser if Ollama is unreachable.
    """

    def __init__(
        self,
        ollama_url: str = "http://localhost:11434",
        model_name: str = "qwen2.5:3b-instruct",
    ) -> None:
        self._url = ollama_url.rstrip("/")
        self._model = model_name
        self._available: Optional[bool] = None

    def check_availability(self) -> bool:
        """Kiểm tra máy chủ Ollama và tự động chọn model Qwen tốt nhất đang có."""
        if self._available is not None:
            return self._available
        try:
            req = urllib.request.Request(f"{self._url}/api/tags", headers={"User-Agent": "GCS_ROV"})
            with urllib.request.urlopen(req, timeout=1.2) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    installed = [m.get("name", "") for m in data.get("models", [])]
                    
                    # Thứ tự ưu tiên model thông minh nhất (Qwen 2.5, Phi-3.5 3.8B, Gemma 2, Llama 3.1)
                    preference = [
                        "qwen2.5:14b-instruct", "qwen2.5:14b",
                        "qwen2.5:7b-instruct", "qwen2.5:7b", "qwen2.5-coder:7b",
                        "gemma2:9b", "llama3.1:8b",
                        "phi3.5", "phi3:3.8b", "phi3:mini",
                        "qwen2.5:3b-instruct", "qwen2.5:3b", "qwen2.5:1.5b"
                    ]
                    for cand in preference:
                        matched = [m for m in installed if cand in m]
                        if matched:
                            self._model = matched[0]
                            break

                    print(f"[LocalSLM] Ollama online. Mô hình tốt nhất được chọn: '{self._model}'")
                    self._available = True
                    return True
        except Exception:
            pass
        self._available = False
        return False

    def generate_agent_response(
        self, prompt: str, system_context: str
    ) -> Optional[Dict[str, Any]]:
        """Call Ollama /api/generate with JSON format schema."""
        if not self.check_availability():
            return None

        system_instruction = (
            "Bạn là Nexos - Trợ lý ảo AI chuyên nghiệp đồng hành cùng người vận hành Robot lặn ngầm Nexos trên Trạm điều khiển mặt đất (GCS).\n\n"
            f"TRẠNG THÁI VIỄN TRẮC THỜI GIAN THỰC (REAL-TIME TELEMETRY):\n{system_context}\n\n"
            "QUY TẮC PHẢN HỒI NGUYÊN TẮC:\n"
            "1. NĂNG LỰC TRẢ LỜI: Trả lời ngắn gọn (1 - 3 câu), súc tích, tự nhiên để đọc ra loa qua Text-to-Speech (TTS).\n"
            "2. TÂM SỰ & TRÒ CHUYỆN (Nhiệm vụ 1): Thân thiện, hóm hỉnh, khích lệ tinh thần người lái khi lặn biển. KHÔNG gọi bất kỳ Tool nào khi người dùng chỉ trò chuyện phiếm ('bạn tên gì', 'sóng to quá', 'mệt quá', 'lặn sợ quá').\n"
            "3. ĐIỀU KHIỂN PHẦN CỨNG & Ý ĐỊNH NGẦM (Nhiệm vụ 2): Nhận biết cả lệnh trực tiếp ('Bật đèn 80%') lẫn ý định ngầm ('Tối quá' -> set_lights 100, 'Lặn sâu hơn chút' -> depth control). Gọi đúng Tool tương ứng (set_lights, arm_thrusters, disarm_thrusters, emergency_stop, take_snapshot). Với các lệnh nguy hiểm (ARM, DISARM, Ngắt khẩn cấp), yêu cầu xác nhận trước.\n"
            "4. TRUY XUẤT THÔNG SỐ & CẢNH BÁO (Nhiệm vụ 3): Trả lời ngay các câu hỏi viễn trắc ('Đang lặn sâu bao nhiêu?', 'Pin còn bao nhiêu?', 'Nhiệt độ cabin sao rồi?') từ thông số viễn trắc thời gian thực ở trên. Nếu rò rỉ nước hoặc pin thấp, đưa ra cảnh báo an toàn.\n"
            "5. HƯỚNG DẪN QUY TRÌNH & GCS (Nhiệm vụ 4): Sử dụng Tool read_sop(topic=...) khi người dùng hỏi quy trình kiểm tra SOP hoặc cách dùng giao diện GCS.\n\n"
            "ĐỊNH DẠNG JSON BẮT BUỘC (Trường 'intent' bắt buộc phải là một trong: 'control', 'chat', 'query_telemetry', 'query_sop'):\n"
            '{"intent": "chat", "tool_call": null, "speech_response": "Sóng gió trên mặt nước không làm khó được Nexos đâu! Tớ vẫn đang giám sát độ sâu 12.4m rất ổn định, bạn cứ yên tâm giữ vững tay lái nhé!", "requires_confirmation": false}\n'
            '{"intent": "control", "tool_call": {"action": "set_lights", "params": {"value": 100}}, "speech_response": "Tớ đã tăng đèn rọi Subsea lên 100% độ sáng cho bạn quan sát rõ hơn rồi nhé.", "requires_confirmation": false}'
        )

        payload = {
            "model": self._model,
            "prompt": prompt,
            "system": system_instruction,
            "format": "json",
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 250},
        }

        if len(prompt.strip()) < 2 or any(prompt.count(w) >= 4 for w in prompt.split()):
            return None

        try:
            req = urllib.request.Request(
                f"{self._url}/api/generate",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json", "User-Agent": "GCS_ROV"},
            )
            with urllib.request.urlopen(req, timeout=3.5) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    res_text = data.get("response", "")
                    return json.loads(res_text)
        except Exception as exc:
            print(f"[LocalSLM] Ollama generate fallback ({exc}). Using high-speed rule engine.")
        return None


# ---------------------------------------------------------------------------
# LangGraph Concept StateGraph Orchestrator
# ---------------------------------------------------------------------------
class ROVAgentBrain:
    """
    Agent Orchestrator applying LangGraph StateGraph flow & Human-in-the-Loop Safety.
    """

    def __init__(
        self,
        sop_json_path: str = "AI/sop_rules.json",
        ollama_url: str = "http://localhost:11434",
        model_name: str = "qwen2.5:3b-instruct",
    ) -> None:
        self.safety_guard = SafetyGuard(confirmation_timeout_s=15.0)
        self.slm_engine = LocalSLMEngine(ollama_url=ollama_url, model_name=model_name)
        self.sop_rules = self._load_sop_rules(sop_json_path)

    def _load_sop_rules(self, path: str) -> List[Dict]:
        try:
            from utils.path_utils import get_resource_path
            resolved_path = get_resource_path(path)
        except Exception:
            resolved_path = path

        if os.path.exists(resolved_path):
            try:
                with open(resolved_path, "r", encoding="utf-8") as f:
                    return json.load(f).get("sop_procedures", [])
            except Exception as e:
                print(f"[AgentBrain] Error loading SOP rules: {e}")
        return []

    WAKE_WORD_ALIASES = [
        "hey nexos", "nexos ơi", "trợ lý nexos", "nexos",
        "hey nexo", "nexo ơi", "nexo",
        "hey vic", "vic ơi", "cnx vic", "vic"
    ]

    def extract_wake_word(self, text: str) -> Tuple[bool, str]:
        """
        Check if text contains Wake Word ("Hey Nexos", "Nexos ơi", "Hey VIC").
        Returns (has_wake_word, clean_command_without_wake_word).
        """
        text_clean = text.strip()
        text_lower = text_clean.lower()
        has_wake = False
        command = text_clean

        for wake in self.WAKE_WORD_ALIASES:
            if wake in text_lower:
                has_wake = True
                import re
                pattern = re.compile(re.escape(wake), re.IGNORECASE)
                command = pattern.sub("", command).strip(" ,.!?:;-")
                break

        return has_wake, command

    def process_pilot_input(
        self, text: str, telemetry_context: Dict[str, Any], is_ptt: bool = True
    ) -> Tuple[Optional[AgentOutputSchema], Optional[Dict]]:
        """
        Process pilot voice text input.
        Strips optional Wake Word prefix ("Hey Nexos", "Nexos ơi") if present, and executes command.
        """
        text_clean = text.strip()
        if not text_clean:
            return None, None

        has_wake, command_text = self.extract_wake_word(text_clean)

        if command_text:
            text_clean = command_text
        elif has_wake and not command_text:
            # User just called the assistant name ("Hey Nexos" / "Nexos ơi")
            speech = "Nexos nghe đây! Bạn cần hỗ trợ gì?"
            out = AgentOutputSchema(intent="chat", speech_response=speech)
            return out, None

        # Step 1: Check if pilot is replying to a PENDING SAFETY CONFIRMATION
        if self.safety_guard.has_pending_confirmation():
            confirmed, msg, pending = self.safety_guard.process_pilot_voice_reply(text_clean)
            if confirmed and pending:
                output = AgentOutputSchema(
                    intent="control",
                    tool_call=AgentToolCall(action=pending["action"], params=pending.get("params", {})),
                    speech_response=msg,
                    requires_confirmation=False,
                )
                return output, pending
            else:
                output = AgentOutputSchema(
                    intent="confirmation_response",
                    tool_call=None,
                    speech_response=msg,
                    requires_confirmation=False,
                )
                return output, None

        # Step 2: High-Precision Deterministic Hardware & Telemetry Engine (0ms Latency Priority)
        text_lower = text_clean.lower()
        is_hardware_or_telemetry = any(k in text_lower for k in [
            "đèn", "bật", "tắt", "rọi", "tối", "sáng", "mờ", "nhìn", "arm", "disarm", "động cơ", "ngắt", "khẩn cấp",
            "độ sâu", "điện áp", "pin", "dung lượng", "nhiệt độ", "thông số", "cảm biến", "viễn trắc",
            "quy trình", "hướng dẫn", "sop", "chụp ảnh", "lưu ảnh", "snapshot", "chuyển", "bảng",
            "tiến", "lùi", "trái", "phải", "lặn", "nổi", "quay", "rẽ", "dừng", "hãm", "di chuyển",
            "giữ độ sâu", "thủ công", "ổn định", "gốc toạ độ", "reset", "tăng tốc", "giảm tốc",
            "vòng tròn", "360", "video", "ghi hình", "camera", "map", "bản đồ", "báo cáo", "cockpit", "table", "rth", "home"
        ])

        if is_hardware_or_telemetry:
            return self._rule_based_fallback(text_clean, telemetry_context)

        # Step 3: Local SLM (Qwen2.5 via Ollama) for Casual Chat & Morale Support
        ctx_str = f"Depth={telemetry_context.get('depth', 0.0)}m, Voltage={telemetry_context.get('voltage', 0.0)}V, Mode={telemetry_context.get('mode', 'MANUAL')}"
        slm_res = self.slm_engine.generate_agent_response(text_clean, ctx_str)

        if slm_res is not None:
            try:
                out = AgentOutputSchema(**slm_res)
                if out.tool_call and out.tool_call.action == "read_sop":
                    topic = str(out.tool_call.params.get("topic", text_clean))
                    sop_text = self._search_sop(topic if topic != text_clean else text_clean)
                    if sop_text:
                        out.speech_response = sop_text
                return self._evaluate_safety_and_build(out)
            except Exception as exc:
                print(f"[AgentBrain] Pydantic parsing error: {exc}")

        # Fallback to rule engine if Ollama is offline or unparseable
        return self._rule_based_fallback(text_clean, telemetry_context)

    def process_emergency_event(self, event_type: str, details: str) -> AgentOutputSchema:
        """Handle proactive critical alerts (e.g. LEAK_DETECTED or Diver Hazard)."""
        if event_type == "pipeline_leak":
            speech = "CẢNH BÁO KHẨN CẤP! Phát hiện RÒ RỈ ĐƯỜNG ỐNG bên dưới ROV! Hãy chuẩn bị chụp ảnh ghi lại vị trí."
        elif event_type == "diver_danger":
            speech = "CẢNH BÁO AN TOÀN! Phát hiện thợ lặn ở quá gần khu vực chân vịt! Yêu cầu giảm tốc ngay lập tức."
        else:
            speech = f"CẢNH BÁO SỰ CỐ KHẨN CẤP: {details}"

        return AgentOutputSchema(
            intent="emergency_alert",
            tool_call=None,
            speech_response=speech,
            requires_confirmation=False,
        )

    def _evaluate_safety_and_build(
        self, out: AgentOutputSchema
    ) -> Tuple[AgentOutputSchema, Optional[Dict]]:
        """Validate action with SafetyGuard."""
        if out.tool_call and out.tool_call.action:
            action_name = out.tool_call.action
            params = out.tool_call.params

            allowed, msg, pending = self.safety_guard.request_execution(action_name, params)
            if not allowed:
                out.requires_confirmation = True
                out.speech_response = msg
                return out, None
            else:
                return out, {"action": action_name, "params": params}

        return out, None

    def set_language(self, lang_code: str) -> None:
        """Dynamically set Agent persona response language ('vi', 'en', 'ja', 'zh', etc.)."""
        self._language = lang_code.lower()
        print(f"[AgentBrain] Persona language updated to: '{self._language}'")

    def _rule_based_fallback(
        self, text: str, telemetry: Dict[str, Any]
    ) -> Tuple[AgentOutputSchema, Optional[Dict]]:
        """High-speed offline keyword parser for voice commands & SOP RAG."""
        text_lower = (
            text.lower()
            .replace("bậc", "bật").replace("đền", "đèn").replace("đen", "đèn")
            .replace("tắc", "tắt").replace("gát", "ngắt").replace("gắt", "ngắt")
        )
        depth = telemetry.get("depth", 0.0)
        lang = getattr(self, "_language", "vi")

        # 0. Agent Identity & Friendly Morale Chat
        if any(k in text_lower for k in ["tên gì", "tên là gì", "bạn là ai", "ai đây", "who are you", "who r u", "introduce", "giới thiệu"]):
            speech = "I am Nexos, professional AI Co-Pilot supporting ROV subsea operations." if lang == "en" else "Tôi là Nexos, trợ lý ảo AI chuyên nghiệp hỗ trợ vận hành robot lặn ngầm."
            out = AgentOutputSchema(intent="chat", speech_response=speech)
            return out, None

        elif any(k in text_lower for k in ["sóng to", "rợn tóc gáy", "sợ quá", "biển xấu", "rough sea", "heavy waves"]):
            speech = f"Heavy waves can't stop Nexos! System depth is stable at {depth:.1f}m." if lang == "en" else f"Sóng lớn không làm khó được Nexos đâu! Hệ thống đang giữ độ sâu {depth:.1f}m rất ổn định."
            out = AgentOutputSchema(intent="chat", speech_response=speech)
            return out, None

        elif any(k in text_lower for k in ["mệt quá", "căng thẳng", "đuối quá", "tired", "exhausted"]):
            speech = "Take a short break, Nexos is monitoring all ROV subsystems." if lang == "en" else "Bạn nghỉ tay một chút nhé, Nexos đang giám sát toàn bộ hệ thống."
            out = AgentOutputSchema(intent="chat", speech_response=speech)
            return out, None

        # 1. Direct Control & Implicit Intents
        import re

        def _extract_num(t: str, default: float = 1.0) -> float:
            match = re.search(r'(\d+(?:[\.,]\d+)?)\s*(?:m\b|mét|met|giây|s\b|%|độ|deg)', t, re.IGNORECASE)
            if match:
                val_str = match.group(1).replace(',', '.')
                try:
                    return float(val_str)
                except ValueError:
                    pass
            nums = re.findall(r'\d+(?:[\.,]\d+)?', t)
            if nums:
                try:
                    return float(nums[0].replace(',', '.'))
                except ValueError:
                    pass
            return default

        # ── Autonomous Parameterized Navigation ───────────────────────────
        # Goto Specific Depth (e.g. "lặn xuống 5m", "lặn đến 8 mét")
        if any(k in text_lower for k in ["lặn xuống", "lặn sâu", "lặn đến", "đến độ sâu"]) and any(c.isdigit() for c in text_lower):
            target_d = _extract_num(text_lower, default=5.0)
            action = "goto_depth"
            speech = f"Target depth set to {target_d:.1f}m. Autonomous depth controller activated." if lang == "en" else f"Đang điều khiển ROV tự động lặn đến độ sâu mục tiêu {target_d:.1f} mét."
            out = AgentOutputSchema(intent="control", tool_call=AgentToolCall(action=action, params={"target_depth": target_d}), speech_response=speech)
            return self._evaluate_safety_and_build(out)

        # Relative Move: Left (e.g. "di chuyển sang trái 2m")
        elif any(k in text_lower for k in ["sang trái", "dạt trái", "qua trái"]) and any(c.isdigit() for c in text_lower):
            dist_m = _extract_num(text_lower, default=2.0)
            action = "relative_move"
            speech = f"Strafing left by {dist_m:.1f} meters." if lang == "en" else f"Đang điều khiển ROV di chuyển dạt sang trái {dist_m:.1f} mét."
            out = AgentOutputSchema(intent="control", tool_call=AgentToolCall(action=action, params={"surge_m": 0.0, "sway_m": -dist_m, "heave_m": 0.0}), speech_response=speech)
            return self._evaluate_safety_and_build(out)

        # Relative Move: Right (e.g. "sang phải 2m")
        elif any(k in text_lower for k in ["sang phải", "dạt phải", "qua phải"]) and any(c.isdigit() for c in text_lower):
            dist_m = _extract_num(text_lower, default=2.0)
            action = "relative_move"
            speech = f"Strafing right by {dist_m:.1f} meters." if lang == "en" else f"Đang điều khiển ROV di chuyển dạt sang phải {dist_m:.1f} mét."
            out = AgentOutputSchema(intent="control", tool_call=AgentToolCall(action=action, params={"surge_m": 0.0, "sway_m": dist_m, "heave_m": 0.0}), speech_response=speech)
            return self._evaluate_safety_and_build(out)

        # Relative Move: Forward (e.g. "tiến lên 3m")
        elif any(k in text_lower for k in ["tiến lên", "tiến tới", "chạy tới"]) and any(c.isdigit() for c in text_lower):
            dist_m = _extract_num(text_lower, default=2.0)
            action = "relative_move"
            speech = f"Moving forward by {dist_m:.1f} meters." if lang == "en" else f"Đang điều khiển ROV tiến lên phía trước {dist_m:.1f} mét."
            out = AgentOutputSchema(intent="control", tool_call=AgentToolCall(action=action, params={"surge_m": dist_m, "sway_m": 0.0, "heave_m": 0.0}), speech_response=speech)
            return self._evaluate_safety_and_build(out)

        # Relative Move: Backward (e.g. "lùi lại 2m")
        elif any(k in text_lower for k in ["lùi lại", "đi lùi", "chạy lùi"]) and any(c.isdigit() for c in text_lower):
            dist_m = _extract_num(text_lower, default=2.0)
            action = "relative_move"
            speech = f"Moving backward by {dist_m:.1f} meters." if lang == "en" else f"Đang điều khiển ROV lùi lại {dist_m:.1f} mét."
            out = AgentOutputSchema(intent="control", tool_call=AgentToolCall(action=action, params={"surge_m": -dist_m, "sway_m": 0.0, "heave_m": 0.0}), speech_response=speech)
            return self._evaluate_safety_and_build(out)

        # ── Complex Autonomous Trajectory Patterns ────────────────────────
        # Circle Orbit (e.g. "bay vòng tròn", "lượn vòng tròn bán kính 4m")
        elif any(k in text_lower for k in ["vòng tròn", "bay vòng", "lượn vòng", "circle"]):
            radius_m = _extract_num(text_lower, default=3.0)
            action = "execute_pattern"
            speech = f"Executing circular orbit pattern with radius {radius_m:.1f}m." if lang == "en" else f"Bắt đầu bài bay lượn vòng tròn tự động bán kính {radius_m:.1f} mét."
            out = AgentOutputSchema(intent="control", tool_call=AgentToolCall(action=action, params={"pattern_type": "circle", "radius_m": radius_m}), speech_response=speech)
            return self._evaluate_safety_and_build(out)

        # 360 Degree Yaw Scan (e.g. "xoay 360 độ", "quét 360")
        elif any(k in text_lower for k in ["360", "xoay tròn", "quét xung quanh", "scan 360"]):
            action = "execute_pattern"
            speech = "Initiating 360-degree panoramic inspection scan." if lang == "en" else "Bắt đầu bài xoay quét 360 độ khảo sát toàn cảnh xung quanh."
            out = AgentOutputSchema(intent="control", tool_call=AgentToolCall(action=action, params={"pattern_type": "yaw_scan_360"}), speech_response=speech)
            return self._evaluate_safety_and_build(out)

        # Return to Home (RTH)
        elif any(k in text_lower for k in ["về điểm xuất phát", "quay về gốc", "trở về home", "rth", "return to home"]):
            action = "return_to_home"
            speech = "Returning to Home origin coordinates." if lang == "en" else "Bắt đầu quy trình tự động quay về toạ độ xuất phát (RTH)."
            out = AgentOutputSchema(intent="control", tool_call=AgentToolCall(action=action), speech_response=speech)
            return self._evaluate_safety_and_build(out)

        # ── GCS Software & UI Automation ──────────────────────────────────
        # Screen / Camera Recording
        elif any(k in text_lower for k in ["quay video", "ghi hình", "record video", "screen record"]):
            is_start = not any(k in text_lower for k in ["dừng", "ngừng", "tắt", "stop", "end"])
            action = "toggle_recording"
            speech = f"Camera and screen recording {'started' if is_start else 'stopped and saved'}." if lang == "en" else f"Đã {'bắt đầu' if is_start else 'dừng'} ghi video camera và màn hình điều khiển."
            out = AgentOutputSchema(intent="control", tool_call=AgentToolCall(action=action, params={"start": is_start}), speech_response=speech)
            return self._evaluate_safety_and_build(out)

        # 3D Map Environment Switching
        elif any(k in text_lower for k in ["hồ chứa", "reservoir"]):
            action = "switch_3d_map"
            speech = "3D Environment switched to Reservoir." if lang == "en" else "Đã chuyển bản đồ 3D sang môi trường Hồ chứa (Reservoir)."
            out = AgentOutputSchema(intent="control", tool_call=AgentToolCall(action=action, params={"map_name": "RESERVOIR"}), speech_response=speech)
            return self._evaluate_safety_and_build(out)

        elif any(k in text_lower for k in ["offshore", "biển sâu", "ngoài khơi", "seabed", "đáy biển"]):
            action = "switch_3d_map"
            speech = "3D Environment switched to Offshore." if lang == "en" else "Đã chuyển bản đồ 3D sang môi trường Biển sâu ngoài khơi (Offshore)."
            out = AgentOutputSchema(intent="control", tool_call=AgentToolCall(action=action, params={"map_name": "SEABED" if ("seabed" in text_lower or "đáy biển" in text_lower) else "OFFSHORE"}), speech_response=speech)
            return self._evaluate_safety_and_build(out)

        # 3D Camera View Switching
        elif any(k in text_lower for k in ["chase", "bám đuôi", "camera sau", "theo sau"]):
            action = "switch_3d_camera"
            speech = "3D Camera mode set to Chase Cam." if lang == "en" else "Đã chuyển camera 3D sang chế độ bám đuôi (Chase Cam)."
            out = AgentOutputSchema(intent="control", tool_call=AgentToolCall(action=action, params={"mode": "chase"}), speech_response=speech)
            return self._evaluate_safety_and_build(out)

        elif any(k in text_lower for k in ["isometric", "phối cảnh", "góc nhìn 3d", "iso"]):
            action = "switch_3d_camera"
            speech = "3D Camera mode set to Isometric View." if lang == "en" else "Đã chuyển camera 3D sang góc nhìn Isometric."
            out = AgentOutputSchema(intent="control", tool_call=AgentToolCall(action=action, params={"mode": "isometric"}), speech_response=speech)
            return self._evaluate_safety_and_build(out)

        elif any(k in text_lower for k in ["nhìn từ trên", "top-down", "topdown", "map view", "camera từ trên"]):
            action = "switch_3d_camera"
            speech = "3D Camera mode set to Top-Down Map View." if lang == "en" else "Đã chuyển camera sang góc nhìn bản đồ từ trên xuống."
            out = AgentOutputSchema(intent="control", tool_call=AgentToolCall(action=action, params={"mode": "map"}), speech_response=speech)
            return self._evaluate_safety_and_build(out)

        # Open Google Maps
        elif any(k in text_lower for k in ["google maps", "bản đồ", "mở map", "định vị gps"]):
            action = "open_gps_map"
            speech = "Opening live Google Maps location." if lang == "en" else "Đang mở Google Maps hiển thị vị trí thực tế của ROV."
            out = AgentOutputSchema(intent="control", tool_call=AgentToolCall(action=action), speech_response=speech)
            return self._evaluate_safety_and_build(out)

        # Switch Telemetry View
        elif any(k in text_lower for k in ["bảng raw", "raw table", "bảng số liệu", "bảng viễn trắc", "viễn trắc chi tiết", "xem bảng"]):
            action = "switch_telemetry_view"
            speech = "Switched to Raw Table view." if lang == "en" else "Đã chuyển sang Bảng số liệu chi tiết (Raw Table)."
            out = AgentOutputSchema(intent="control", tool_call=AgentToolCall(action=action, params={"view": "TABLE"}), speech_response=speech)
            return self._evaluate_safety_and_build(out)

        elif any(k in text_lower for k in ["cockpit", "phi công", "thẻ trực quan"]):
            action = "switch_telemetry_view"
            speech = "Switched to Pilot Cockpit view." if lang == "en" else "Đã chuyển sang Thẻ điều khiển phi công (Pilot Cockpit)."
            out = AgentOutputSchema(intent="control", tool_call=AgentToolCall(action=action, params={"view": "COCKPIT"}), speech_response=speech)
            return self._evaluate_safety_and_build(out)

        # Export Report
        elif any(k in text_lower for k in ["xuất báo cáo", "lưu báo cáo", "export report"]):
            action = "export_report"
            speech = "Exporting dive inspection report." if lang == "en" else "Đang xuất báo cáo kiểm tra lặn sang tệp tin."
            out = AgentOutputSchema(intent="control", tool_call=AgentToolCall(action=action), speech_response=speech)
            return self._evaluate_safety_and_build(out)

        # ── Movement & Maneuver Controls ──────────────────────────────────
        # Forward
        elif any(k in text_lower for k in ["tiến lên", "tiến tới", "chạy tới", "đi tới", "tiến", "forward", "go ahead"]):
            action = "move_forward"
            speech = "Moving forward." if lang == "en" else "Đang điều khiển ROV tiến lên phía trước."
            out = AgentOutputSchema(intent="control", tool_call=AgentToolCall(action=action, params={"speed": 0.6, "duration": 1.5}), speech_response=speech)
            return self._evaluate_safety_and_build(out)

        # Backward
        elif any(k in text_lower for k in ["lùi lại", "đi lùi", "chạy lùi", "lùi", "backward", "reverse", "back"]):
            action = "move_backward"
            speech = "Moving backward." if lang == "en" else "Đang điều khiển ROV lùi lại."
            out = AgentOutputSchema(intent="control", tool_call=AgentToolCall(action=action, params={"speed": 0.6, "duration": 1.5}), speech_response=speech)
            return self._evaluate_safety_and_build(out)

        # Strafe Left
        elif any(k in text_lower for k in ["sang trái", "dạt trái", "qua trái", "dạt sang trái", "strafe left", "port"]):
            action = "move_left"
            speech = "Strafing left." if lang == "en" else "Đang dạt tàu sang mạn trái."
            out = AgentOutputSchema(intent="control", tool_call=AgentToolCall(action=action, params={"speed": 0.5, "duration": 1.5}), speech_response=speech)
            return self._evaluate_safety_and_build(out)

        # Strafe Right
        elif any(k in text_lower for k in ["sang phải", "dạt phải", "qua phải", "dạt sang phải", "strafe right", "starboard"]):
            action = "move_right"
            speech = "Strafing right." if lang == "en" else "Đang dạt tàu sang mạn phải."
            out = AgentOutputSchema(intent="control", tool_call=AgentToolCall(action=action, params={"speed": 0.5, "duration": 1.5}), speech_response=speech)
            return self._evaluate_safety_and_build(out)

        # Dive Down
        elif any(k in text_lower for k in ["lặn xuống", "chìm xuống", "đi xuống", "lặn sâu", "dive down", "descend", "dive"]):
            action = "dive_down"
            speech = "Diving down." if lang == "en" else "Đang điều khiển ROV lặn xuống."
            out = AgentOutputSchema(intent="control", tool_call=AgentToolCall(action=action, params={"speed": 0.5, "duration": 1.5}), speech_response=speech)
            return self._evaluate_safety_and_build(out)

        # Surface Up
        elif any(k in text_lower for k in ["nổi lên", "lên mặt nước", "trồi lên", "đi lên", "surface", "ascend"]):
            action = "surface_up"
            speech = "Surfacing up." if lang == "en" else "Đang điều khiển ROV nổi lên."
            out = AgentOutputSchema(intent="control", tool_call=AgentToolCall(action=action, params={"speed": 0.5, "duration": 1.5}), speech_response=speech)
            return self._evaluate_safety_and_build(out)

        # Turn Left / Yaw -
        elif any(k in text_lower for k in ["quay trái", "rẽ trái", "ngoặt trái", "xoay trái", "turn left", "yaw left"]):
            action = "turn_left"
            speech = "Turning left." if lang == "en" else "Đang quay mũi tàu sang trái."
            out = AgentOutputSchema(intent="control", tool_call=AgentToolCall(action=action, params={"speed": 0.5, "duration": 1.2}), speech_response=speech)
            return self._evaluate_safety_and_build(out)

        # Turn Right / Yaw +
        elif any(k in text_lower for k in ["quay phải", "rẽ phải", "ngoặt phải", "xoay phải", "turn right", "yaw right"]):
            action = "turn_right"
            speech = "Turning right." if lang == "en" else "Đang quay mũi tàu sang phải."
            out = AgentOutputSchema(intent="control", tool_call=AgentToolCall(action=action, params={"speed": 0.5, "duration": 1.2}), speech_response=speech)
            return self._evaluate_safety_and_build(out)

        # Stop Motion
        elif any(k in text_lower for k in ["dừng lại", "đứng yên", "giữ yên", "hãm lại", "thôi", "stop motion", "hold position", "halt"]):
            action = "stop_motion"
            speech = "Stopping all thrusters." if lang == "en" else "Đã dừng chuyển động và hãm chân vịt."
            out = AgentOutputSchema(intent="control", tool_call=AgentToolCall(action=action), speech_response=speech)
            return self._evaluate_safety_and_build(out)

        # ── Flight Modes ──────────────────────────────────────────────────
        elif any(k in text_lower for k in ["giữ độ sâu", "tự giữ độ sâu", "chế độ giữ độ sâu", "alt hold", "depth hold"]):
            action = "set_mode"
            speech = "Flight mode set to ALT_HOLD." if lang == "en" else "Đã chuyển sang chế độ tự động Giữ độ sâu (ALT_HOLD)."
            out = AgentOutputSchema(intent="control", tool_call=AgentToolCall(action=action, params={"mode": "ALT_HOLD"}), speech_response=speech)
            return self._evaluate_safety_and_build(out)

        elif any(k in text_lower for k in ["chế độ thủ công", "lái thủ công", "manual mode"]):
            action = "set_mode"
            speech = "Flight mode set to MANUAL." if lang == "en" else "Đã chuyển sang chế độ Lái thủ công (MANUAL)."
            out = AgentOutputSchema(intent="control", tool_call=AgentToolCall(action=action, params={"mode": "MANUAL"}), speech_response=speech)
            return self._evaluate_safety_and_build(out)

        elif any(k in text_lower for k in ["chế độ ổn định", "tự cân bằng", "stabilize"]):
            action = "set_mode"
            speech = "Flight mode set to STABILIZE." if lang == "en" else "Đã chuyển sang chế độ Tự cân bằng (STABILIZE)."
            out = AgentOutputSchema(intent="control", tool_call=AgentToolCall(action=action, params={"mode": "STABILIZE"}), speech_response=speech)
            return self._evaluate_safety_and_build(out)

        # Reset Origin / Home
        elif any(k in text_lower for k in ["đặt lại gốc", "reset toạ độ", "gốc toạ độ", "set origin", "reset home", "gốc 0"]):
            action = "reset_origin"
            speech = "Resetting Home Origin to current position." if lang == "en" else "Đã đặt lại gốc toạ độ Home tại vị trí hiện tại."
            out = AgentOutputSchema(intent="control", tool_call=AgentToolCall(action=action), speech_response=speech)
            return self._evaluate_safety_and_build(out)

        # Speed adjustment
        elif any(k in text_lower for k in ["tăng tốc", "nhanh hơn", "tăng lực đẩy", "speed up"]):
            action = "speed_up"
            speech = "Increasing speed scale." if lang == "en" else "Đã tăng độ nhạy vận tốc điều khiển."
            out = AgentOutputSchema(intent="control", tool_call=AgentToolCall(action=action), speech_response=speech)
            return self._evaluate_safety_and_build(out)

        elif any(k in text_lower for k in ["giảm tốc", "chậm lại", "giảm lực đẩy", "speed down", "slow down"]):
            action = "speed_down"
            speech = "Decreasing speed scale." if lang == "en" else "Đã giảm độ nhạy vận tốc điều khiển."
            out = AgentOutputSchema(intent="control", tool_call=AgentToolCall(action=action), speech_response=speech)
            return self._evaluate_safety_and_build(out)

        # ── Hardware & Actuators ──────────────────────────────────────────
        # Dark room / Spotlight 100%
        elif any(k in text_lower for k in ["tối quá", "tối thui", "không nhìn thấy", "chẳng nhìn rõ", "too dark", "cannot see", "darkness"]):
            action = "set_lights"
            speech = "Subsea spotlight intensity set to 100%." if lang == "en" else "Đã tăng đèn rọi Subsea lên 100% độ sáng."
            out = AgentOutputSchema(intent="control", tool_call=AgentToolCall(action=action, params={"value": 100}), speech_response=speech)
            return self._evaluate_safety_and_build(out)

        # Snapshot
        elif any(k in text_lower for k in ["chụp ảnh", "chụp hình", "lưu ảnh", "snapshot", "take photo", "capture frame", "bấm máy"]):
            action = "take_snapshot"
            speech = "Snapshot captured and saved to media folder." if lang == "en" else "Đã chụp và lưu ảnh vào thư mục media thành công."
            out = AgentOutputSchema(intent="control", tool_call=AgentToolCall(action=action), speech_response=speech)
            return self._evaluate_safety_and_build(out)

        # 2. SOP RAG Search
        elif any(k in text_lower for k in ["quy trình", "hướng dẫn", "sop", "cách dùng", "procedure", "manual", "instruction"]):
            sop_text = self._search_sop(text_lower)
            out = AgentOutputSchema(intent="query_sop", tool_call=AgentToolCall(action="read_sop"), speech_response=sop_text)
            return out, None

        # 3. Critical ARM / DISARM / Emergency Command
        elif any(k in text_lower for k in ["khởi động động cơ", "arm động cơ", "arm thrusters", "start motors"]):
            action = "arm_thrusters"
            speech = "Arming thrusters." if lang == "en" else "Đang khởi động động cơ."
            out = AgentOutputSchema(intent="control", tool_call=AgentToolCall(action=action), speech_response=speech)
            return self._evaluate_safety_and_build(out)

        elif any(k in text_lower for k in ["ngắt động cơ", "tắt động cơ", "khẩn cấp", "emergency stop", "disarm", "stop thrusters"]):
            action = "emergency_stop"
            speech = "EMERGENCY STOP requested." if lang == "en" else "Yêu cầu DỪNG KHẨN CẤP."
            out = AgentOutputSchema(intent="control", tool_call=AgentToolCall(action=action), speech_response=speech)
            return self._evaluate_safety_and_build(out)

        # Spotlight Controls
        elif any(k in text_lower for k in ["bật đèn", "tắt đèn", "đèn rọi", "đèn", "light", "lights", "spotlight"]):
            action = "set_lights"
            val = 0 if any(k in text_lower for k in ["tắt", "off", "turn off", "disable"]) else 100
            import re
            nums = re.findall(r"\d+", text_lower)
            if nums and not any(k in text_lower for k in ["tắt", "off"]):
                try:
                    val = max(0, min(100, int(nums[0])))
                except Exception:
                    val = 100
            if lang == "en":
                speech = f"Subsea spotlight {'turned off' if val==0 else f'adjusted to {val}%'}."
            else:
                speech = f"Đã {'tắt' if val==0 else 'điều chỉnh'} đèn rọi Subsea {'về 0%' if val==0 else f'lên {val}%'}."
            out = AgentOutputSchema(intent="control", tool_call=AgentToolCall(action=action, params={"value": val}), speech_response=speech)
            return self._evaluate_safety_and_build(out)

        # 4. Telemetry Inquiry
        elif any(k in text_lower for k in ["pin", "dung lượng", "battery", "voltage", "power"]):
            battery_pct = telemetry.get("battery_pct", 85)
            voltage = telemetry.get("voltage", 16.8)
            if lang == "en":
                speech = f"Current battery level is {battery_pct}% at {voltage:.1f} volts."
            else:
                speech = f"Dung lượng pin ROV hiện tại còn {battery_pct}%, điện áp {voltage:.1f}V."
            out = AgentOutputSchema(intent="telemetry_query", speech_response=speech)
            return out, None

        elif any(k in text_lower for k in ["độ sâu", "sâu bao nhiêu", "depth", "deep"]):
            speech = f"ROV is currently operating at depth {depth:.1f} meters." if lang == "en" else f"Độ sâu làm việc hiện tại của ROV là {depth:.1f} mét."
            out = AgentOutputSchema(intent="telemetry_query", speech_response=speech)
            return out, None

        elif any(k in text_lower for k in ["nhiệt độ", "nhiệt", "temp", "temperature"]):
            temp_c = telemetry.get("temp", 28.5)
            speech = f"Internal electronics temperature is {temp_c:.1f} degrees Celsius." if lang == "en" else f"Nhiệt độ khoang máy hiện tại là {temp_c:.1f} độ C."
            out = AgentOutputSchema(intent="telemetry_query", speech_response=speech)
            return out, None

        # Generic Fallback Response
        if len(text.strip()) > 30 or any(text.count(w) >= 3 for w in text.split()):
            if lang == "en":
                speech = "I didn't quite catch that. Could you please repeat your command?"
            else:
                speech = "Tớ chưa nghe rõ yêu cầu. Bạn có thể nói lại ngắn gọn hơn không?"
        else:
            if lang == "en":
                speech = f"Received command: '{text}'. Processing pilot request."
            else:
                speech = f"Đã nhận lệnh: '{text}'. Đang xử lý yêu cầu của bạn."
        out = AgentOutputSchema(intent="general", speech_response=speech)
        return out, None

    def _search_sop(self, query: str) -> str:
        """Simple RAG over local sop_rules.json."""
        for sop in self.sop_rules:
            title = sop.get("title", "").lower()
            sop_id = sop.get("id", "").lower()
            if "ống" in query or "pipeline" in query:
                if "pipeline" in sop_id or "ống" in title:
                    steps = sop.get("steps", [])
                    return f"Quy trình kiểm tra đường ống: {steps[0]} {steps[1]}"
            elif "thợ lặn" in query or "diver" in query:
                if "diver" in sop_id:
                    steps = sop.get("steps", [])
                    return f"Quy trình an toàn thợ lặn: {steps[0]} {steps[1]}"

        # Default fallback SOP
        if self.sop_rules:
            first = self.sop_rules[0]
            return f"Quy trình chuẩn {first.get('title')}: {first.get('steps')[0]}"
        return "Hiện chưa tìm thấy tài liệu quy trình thao tác chuẩn phù hợp."
